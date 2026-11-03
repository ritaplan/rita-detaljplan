-- Publiceringsvyer för planmosaiken: det enda som webbtjänsterna (GeoServer och QGIS Server) får läsa.
--
-- Pluginets egna tabeller ligger kvar orörda i planschemat. Vyerna väljer vilka planer som är offentliga och vilka
-- uppgifter som visas, och förbereder det en plankarta behöver (färg per användning, mönster och gränslinjer).
-- Alla planer i planschemat ligger i samma tabeller och skiljs åt med kolumnen "plan".
--
-- Körs som databasens ägare, med planschemats namn och koordinatsystem (EPSG-kod):
--
--   psql -v ON_ERROR_STOP=1 -v plan_schema=detaljplaner -v srid=3006 -f publicering.sql
--
-- Läsrollen skapas separat (publicering_roll.sh), eftersom lösenordet inte ska stå här.
--
-- Vyerna räknas om vid varje anrop. För många planer: gör om dem till materialiserade vyer med index och uppdatera dem
-- efter varje incheckning (REFRESH MATERIALIZED VIEW).

CREATE SCHEMA IF NOT EXISTS publicering;

-- 1. Planområdena (och det enda ställe som bestämmer vilka planer som är offentliga) ------------------------------
CREATE OR REPLACE VIEW publicering.planmosaik AS
SELECT d.fid,
       d.plan,
       d.geom,
       d.kommun,
       d.beteckning,
       d.namn,
       d.syfte,
       d.status,
       b."diarienummerKommun" AS diarienummer,
       b."datumAntagande" AS datum_antagande,
       -- datum laga kraft kan vara flera datum, separerade med semikolon: det första gäller för genomförandetiden
       NULLIF(split_part(b."datumLagakraft", ';', 1), '')::date AS datum_laga_kraft,
       b.genomforandetid AS genomforandetid_manader,
       -- när genomförandetiden går ut (tom om planen inte har vunnit laga kraft eller saknar genomförandetid)
       (NULLIF(split_part(b."datumLagakraft", ';', 1), '')::date
            + make_interval(months => b.genomforandetid))::date AS genomforandetid_utgar,
       CASE
           WHEN d.status = 'antagen' THEN 'antagen'
           WHEN b.genomforandetid IS NULL OR NULLIF(split_part(b."datumLagakraft", ';', 1), '') IS NULL
               THEN 'gällande'
           WHEN NULLIF(split_part(b."datumLagakraft", ';', 1), '')::date
                    + make_interval(months => b.genomforandetid) < current_date
               THEN 'gällande, genomförandetiden har gått ut'
           ELSE 'gällande, genomförandetiden pågår'
       END AS visningsstatus,
       -- bifogade handlingar som JSON: plankartan först, sedan planbeskrivningen, sedan övriga (bara dem som har en länk)
       (SELECT COALESCE(jsonb_agg(jsonb_build_object('roll', k.roll, 'innehall', k.innehall, 'namn', k.namn,
                                                     'datum', k.datum, 'lank', k.lank)
                                  ORDER BY CASE WHEN k.innehall = 'plankarta' THEN 0 WHEN k.roll = 'planbeskrivning' THEN 1
                                                WHEN k.roll = 'beslutshandling' THEN 2 ELSE 3 END, k.datum DESC NULLS LAST,
                                           k.namn), '[]'::jsonb)::text
        FROM :"plan_schema".dokument k
        WHERE k.plan = d.plan AND k.detaljplan = d.objektidentitet AND NULLIF(k.lank, '') IS NOT NULL) AS handlingar
FROM :"plan_schema".detaljplan d
LEFT JOIN LATERAL (
    -- en plan kan ha flera beslut: ta det senaste antagandet
    SELECT * FROM :"plan_schema".beslutsinformation b
    WHERE b.plan = d.plan AND b.detaljplan = d.objektidentitet
    ORDER BY b."datumAntagande" DESC NULLS LAST
    LIMIT 1
) b ON true
-- Bara antagna planer och planer som vunnit laga kraft är offentliga. Pågående planer och upphävda planer visas inte.
WHERE d.status IN ('antagen', 'laga kraft');

COMMENT ON VIEW publicering.planmosaik IS 'Planområdena för antagna planer och planer med laga kraft';

-- 2. Användningsytor med färg ------------------------------------------------------------------------------------
-- Färgerna är Boverkets färgnamn som i pluginet (core/symbology.py, FARGER). Namnet står kvar i "farg".
DROP VIEW IF EXISTS publicering.plan_anvandning;
CREATE VIEW publicering.plan_anvandning AS
SELECT a.fid,
       a.plan,
       p.namn AS plan_namn,
       p.beteckning AS plan_beteckning,
       p.visningsstatus,
       p.status AS plan_status,
       p.datum_laga_kraft::text AS datum_laga_kraft,  -- text: GeoServer lägger annars ett Z efter datum
       p.genomforandetid_utgar::text AS genomforandetid_utgar,
       p.syfte AS plan_syfte,
       a.beteckning,
       a.anvandningsform,
       a.farg,
       CASE a.farg
           WHEN 'Gul' THEN '#ffffce'     WHEN 'Brun' THEN '#dabf8c'     WHEN 'Beige' THEN '#ffcb83'
           WHEN 'Orange' THEN '#ff8040'  WHEN 'Röd' THEN '#fa4b3c'      WHEN 'Rosa' THEN '#ffbce1'
           WHEN 'Lila' THEN '#d1b6e1'    WHEN 'Blå' THEN '#a5dafb'      WHEN 'Blågrå' THEN '#b6cce1'
           WHEN 'Grön' THEN '#b2ec40'    WHEN 'Ljusgrön' THEN '#deffce' WHEN 'Grå' THEN '#d9d9d9'
           WHEN 'Ljusgrå' THEN '#e9e9e9'
           ELSE '#f5f5f5'
       END AS fyllfarg,
       a.geom
FROM :"plan_schema".anvandning_yta a
JOIN publicering.planmosaik p ON p.plan = a.plan;

-- 3. Egenskapsytor med mönster (prickmark, korsmark, ...) ---------------------------------------------------------
CREATE OR REPLACE VIEW publicering.plan_egenskap AS
SELECT e.fid,
       e.plan,
       e.symbol,
       CASE e.symbol
           WHEN 'Marken får inte förses med byggnad/byggnadsverk' THEN 'prickmark'
           WHEN 'Marken får inte förses med byggnadsverk eller viss typ av byggnadsverk' THEN 'prickmark'
           WHEN 'Marken får endast förses med viss typ av byggnadsverk' THEN 'korsmark'
           WHEN 'Marken får endast förses med byggnadsverk under mark' THEN 'ringprickad'
       END AS monster,
       e.geom
FROM :"plan_schema".egenskap_yta e
JOIN publicering.planmosaik p ON p.plan = e.plan
WHERE e.symbol IN ('Marken får inte förses med byggnad/byggnadsverk',
                   'Marken får inte förses med byggnadsverk eller viss typ av byggnadsverk',
                   'Marken får endast förses med viss typ av byggnadsverk',
                   'Marken får endast förses med byggnadsverk under mark');

-- 4. Bestämmelser med motiv, per användningsyta -----------------------------------------------------------------
-- Formuleringen med värdena ifyllda ("[annat skydd:text]" blir den text som angetts), som i pluginet (core/rows.py).
CREATE OR REPLACE FUNCTION publicering.bestammelsetext(formulering text, varde text) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    result text := formulering;
    vals jsonb;
    found record;
    filled text;
BEGIN
    IF formulering IS NULL OR varde IS NULL OR varde = '' THEN
        RETURN formulering;
    END IF;
    BEGIN
        vals := varde::jsonb;
    EXCEPTION WHEN others THEN
        RETURN formulering;
    END;
    FOR found IN SELECT m[1] AS token, m[2] AS name FROM regexp_matches(formulering, '(\[([^\]:]+):[^\]]*\])', 'g') AS m LOOP
        SELECT v->>'variabelvarde' INTO filled FROM jsonb_array_elements(vals) v WHERE v->>'beskrivning' = found.name LIMIT 1;
        IF filled IS NOT NULL THEN
            result := replace(result, found.token, filled);
        END IF;
    END LOOP;
    RETURN result;
END
$$;

-- En rad per bestämmelse som gäller inom en användningsyta: ytans egna (användning) och egenskaper (yta, linje, punkt) som
-- ligger i den. Geometrin är användningsytan, så ett klick i kartan ger alla bestämmelser i området. "egen_geojson" är
-- bestämmelsens egen geometri i Web Mercator: kartan använder den för att visa vilka som gäller exakt där man klickade
-- och för att markera dem. Bara planer som är offentliga (planmosaik) ingår.
CREATE OR REPLACE VIEW publicering.plan_bestammelser AS
WITH rader AS (
    SELECT a.plan, a.objektidentitet AS omrade_id, a.beteckning AS omrade_beteckning, a.anvandningsform, a.geom,
           'anvandning'::text AS kategori, b.objektidentitet AS bestammelse_id, b.beteckning, b.ordning,
           b.bestammelseformulering, b.bestammelsevarde, b.motiv, b.bestammelsekod, b.symbol, b.farg, a.geom AS egen
    FROM :"plan_schema".anvandning_yta a
    JOIN publicering.planmosaik p ON p.plan = a.plan
    JOIN :"plan_schema".bestammelse b ON b.plan = a.plan AND b.yta = a.objektidentitet AND b.tabell = 'anvandning_yta'
  UNION ALL
    SELECT a.plan, a.objektidentitet, a.beteckning, a.anvandningsform, a.geom,
           'egenskap', b.objektidentitet, b.beteckning, b.ordning,
           b.bestammelseformulering, b.bestammelsevarde, b.motiv, b.bestammelsekod, b.symbol, b.farg, e.geom
    FROM :"plan_schema".anvandning_yta a
    JOIN publicering.planmosaik p ON p.plan = a.plan
    JOIN :"plan_schema".egenskap_yta e ON e.plan = a.plan AND ST_Intersects(a.geom, e.geom)
         AND ST_Area(ST_Intersection(a.geom, e.geom)) > 0.5
    JOIN :"plan_schema".bestammelse b ON b.plan = a.plan AND b.yta = e.objektidentitet AND b.tabell = 'egenskap_yta'
  UNION ALL
    SELECT a.plan, a.objektidentitet, a.beteckning, a.anvandningsform, a.geom,
           'egenskap', b.objektidentitet, b.beteckning, b.ordning,
           b.bestammelseformulering, b.bestammelsevarde, b.motiv, b.bestammelsekod, b.symbol, b.farg, l.geom
    FROM :"plan_schema".anvandning_yta a
    JOIN publicering.planmosaik p ON p.plan = a.plan
    JOIN :"plan_schema".egenskap_linje l ON l.plan = a.plan AND ST_Intersects(a.geom, l.geom)
         AND ST_Length(ST_Intersection(a.geom, l.geom)) > 0.5
    JOIN :"plan_schema".bestammelse b ON b.plan = a.plan AND b.yta = l.objektidentitet AND b.tabell = 'egenskap_linje'
  UNION ALL
    SELECT a.plan, a.objektidentitet, a.beteckning, a.anvandningsform, a.geom,
           'egenskap', b.objektidentitet, b.beteckning, b.ordning,
           b.bestammelseformulering, b.bestammelsevarde, b.motiv, b.bestammelsekod, b.symbol, b.farg, pt.geom
    FROM :"plan_schema".anvandning_yta a
    JOIN publicering.planmosaik p ON p.plan = a.plan
    JOIN :"plan_schema".egenskap_punkt pt ON pt.plan = a.plan AND ST_Intersects(a.geom, pt.geom)
    JOIN :"plan_schema".bestammelse b ON b.plan = a.plan AND b.yta = pt.objektidentitet AND b.tabell = 'egenskap_punkt'
)
SELECT (row_number() OVER (ORDER BY plan, omrade_id, kategori, ordning, beteckning))::int AS fid,
       plan,
       omrade_id,
       omrade_beteckning,
       anvandningsform,
       kategori,
       bestammelse_id,
       beteckning,
       ordning,
       publicering.bestammelsetext(bestammelseformulering, bestammelsevarde) AS text,
       motiv,
       bestammelsekod,
       CASE symbol
           WHEN 'Marken får inte förses med byggnad/byggnadsverk' THEN 'prickmark'
           WHEN 'Marken får inte förses med byggnadsverk eller viss typ av byggnadsverk' THEN 'prickmark'
           WHEN 'Marken får endast förses med viss typ av byggnadsverk' THEN 'korsmark'
           WHEN 'Marken får endast förses med byggnadsverk under mark' THEN 'ringprickad'
       END AS monster,
       CASE farg
           WHEN 'Gul' THEN '#ffffce'     WHEN 'Brun' THEN '#dabf8c'     WHEN 'Beige' THEN '#ffcb83'
           WHEN 'Orange' THEN '#ff8040'  WHEN 'Röd' THEN '#fa4b3c'      WHEN 'Rosa' THEN '#ffbce1'
           WHEN 'Lila' THEN '#d1b6e1'    WHEN 'Blå' THEN '#a5dafb'      WHEN 'Blågrå' THEN '#b6cce1'
           WHEN 'Grön' THEN '#b2ec40'    WHEN 'Ljusgrön' THEN '#deffce' WHEN 'Grå' THEN '#d9d9d9'
           WHEN 'Ljusgrå' THEN '#e9e9e9'
       END AS fyllfarg,
       ST_AsGeoJSON(ST_Transform(egen, 3857), 1) AS egen_geojson,
       geom
FROM rader;

COMMENT ON VIEW publicering.plan_bestammelser IS 'Bestämmelser med motiv per användningsyta, för informationsrutan i webbkartan';

-- 5. Gränslinjer i planens hierarki: planområdesgräns > användningsgräns > egenskapsgräns -------------------------
-- Där gränser sammanfaller ritas bara den högsta, och en gräns som delas av två ytor ritas en gång (som i pluginet). Det
-- gäller också planområdesgränsen mellan två planer som ligger kant i kant: gränserna läggs ihop till en linje. Hörn som
-- ligger närmare än 5 cm räknas som samma, så att en gräns som två planer ritat var för sig (med små avvikelser) blir en.
CREATE OR REPLACE VIEW publicering.plan_gransar AS
WITH planer AS (
    SELECT ST_Union(ST_Boundary(p.geom), 0.05) AS g FROM publicering.planmosaik p
), anv AS (
    SELECT a.plan, ST_Union(ST_Boundary(a.geom), 0.05) AS g
    FROM :"plan_schema".anvandning_yta a JOIN publicering.planmosaik p ON p.plan = a.plan GROUP BY a.plan
), egen AS (
    SELECT e.plan, ST_Union(ST_Boundary(e.geom), 0.05) AS g
    FROM :"plan_schema".egenskap_yta e JOIN publicering.planmosaik p ON p.plan = e.plan GROUP BY e.plan
), linjer AS (
    -- planområdesgränsen gäller alla planer: den hör inte till en enskild plan
    SELECT NULL::text AS plan, 'planomradesgrans'::text AS typ, planer.g AS geom FROM planer
    UNION ALL
    SELECT anv.plan, 'anvandningsgrans', ST_Difference(anv.g, ST_Buffer(planer.g, 0.1))
    FROM anv CROSS JOIN planer
    UNION ALL
    SELECT egen.plan, 'egenskapsgrans',
           ST_Difference(egen.g, ST_Buffer(ST_Union(planer.g, COALESCE(anv.g, planer.g)), 0.1))
    FROM egen CROSS JOIN planer LEFT JOIN anv USING (plan)
)
SELECT (row_number() OVER (ORDER BY typ, plan))::int AS fid,
       plan,
       typ,
       ST_Multi(ST_CollectionExtract(geom, 2))::geometry(MultiLineString, :srid) AS geom
FROM linjer
WHERE geom IS NOT NULL AND NOT ST_IsEmpty(ST_CollectionExtract(geom, 2));

COMMENT ON VIEW publicering.plan_gransar IS 'Planområdesgräns, användningsgräns och egenskapsgräns';
