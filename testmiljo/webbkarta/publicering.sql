-- Publiceringsvy för planmosaiken: det enda som webbtjänsterna (GeoServer, QGIS Server, Martin) får läsa.
--
-- Pluginets egna tabeller ligger kvar orörda i planschemat. Vyn väljer vilka planer som är offentliga och vilka
-- uppgifter som visas. Byt schemanamnet nedan (detaljplaner_test) mot ert plan-schema. Alla planer i schemat ligger
-- i samma tabeller och skiljs åt med kolumnen "plan".
--
-- Körs som databasens ägare. Läsrollen skapas separat (publicering_roll.sh), eftersom lösenordet inte ska stå här.

CREATE SCHEMA IF NOT EXISTS publicering;

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
       END AS visningsstatus
FROM detaljplaner_test.detaljplan d
LEFT JOIN LATERAL (
    -- en plan kan ha flera beslut: ta det senaste antagandet
    SELECT * FROM detaljplaner_test.beslutsinformation b
    WHERE b.plan = d.plan AND b.detaljplan = d.objektidentitet
    ORDER BY b."datumAntagande" DESC NULLS LAST
    LIMIT 1
) b ON true
-- Bara antagna planer och planer som vunnit laga kraft är offentliga. Pågående planer och upphävda planer visas inte.
WHERE d.status IN ('antagen', 'laga kraft');

COMMENT ON VIEW publicering.planmosaik IS 'Planmosaik: planområdena för antagna planer och planer med laga kraft';
