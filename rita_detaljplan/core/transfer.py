"""Flytta, kopiera och ta bort planer i en PostGIS-databas, och flytta dem till och från GeoPackage-filer.

* **Importera** lägger en plan ur en GeoPackage som en ny plan i ett schema i databasen. Allt läses ur filen först, så att
  ett fel i filen inte lämnar något i databasen. Raderna skrivs sedan med samma SQL som en incheckning (en transaktion:
  allt eller inget), och antalet rader i varje tabell kontrolleras efteråt. Går något fel tas den nya planen bort igen.
* **Exportera** sparar en plan ur databasen som en ny GeoPackage, utan att checka ut den eller låsa den för andra. Filen
  är planen som den ligger i databasen, inte någons utcheckade arbetskopia.
* **Kopiera** gör en ny plan av en plan i databasen, i samma eller en annan databas eller ett annat schema (exporterar
  till en tillfällig fil och importerar den).
* **Ta bort** tar bort en plan ur databasen, i en transaktion och bara om ingen har den utcheckad.

En befintlig plan skrivs aldrig över: importen och kopieringen avbryts om planidentifieraren redan finns i schemat (se
``storage.create_postgis_plan``), och exporten om filen redan finns.
"""
from __future__ import annotations

import gc
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import checkout, geopackage, model, storage
from .storage import PostgisError, PostgisStorage, literal, quote

# uppgifter i filens metadata som inte hör till planen i databasen: schemats (versionen och koordinatsystemet ligger i
# schemat) och utcheckningens
_NOT_PLAN_META = ("schema_version", "spec_version", "epsg", checkout.LOCK_KEY, *checkout.LOCAL_KEYS)
LOCKED_ADVICE = "Kasta utcheckningen eller bryt låset först."
LOCKED_MESSAGE = "Planen är utcheckad och kan inte tas bort. " + LOCKED_ADVICE


class TransferError(RuntimeError):
    """Planen gick inte att flytta. Meddelandet är avsett för användaren."""


@dataclass(frozen=True)
class Imported:
    plan: PostgisStorage
    counts: dict[str, int]  # tabell -> antal rader som lagts in

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def read_plan_file(path: Path) -> dict[str, str]:
    """Planens metadata ur en GeoPackage (schemaversion, koordinatsystem, kommun …). Kastar ``TransferError`` om filen inte
    är en plan från Rita Detaljplan eller är gjord med en nyare version än den här."""
    try:
        meta = geopackage.read_meta(path) if Path(path).is_file() else {}
    except Exception as exc:  # noqa: BLE001 - sqlite3.Error, men också filsystemsfel
        raise TransferError(f"Kunde inte läsa {Path(path).name}: {exc}") from exc
    version, epsg = meta.get("schema_version", ""), meta.get("epsg", "")
    if not (version.isdigit() and epsg.isdigit()):
        raise TransferError(f"{Path(path).name} är ingen detaljplan från Rita Detaljplan.")
    if int(version) > model.SCHEMA_VERSION:
        raise TransferError(f"{Path(path).name} är gjord med en nyare version av Rita Detaljplan. Uppdatera pluginet "
                            "först.")
    if int(epsg) not in geopackage.epsg_codes():
        raise TransferError(f"{Path(path).name} har koordinatsystemet EPSG:{epsg}, som inte är en SWEREF 99-projektion "
                            "för detaljplaner (EPSG:3006–3018).")
    return meta


def _read_tables(path: Path, meta: dict[str, str]) -> list[tuple[model.LayerDef, list[dict]]]:
    """Alla tabellers rader ur filen. En tabell som saknas är tom om filen är från en äldre version (tabellen kom senare),
    annars ett fel."""
    older = int(meta["schema_version"]) < model.SCHEMA_VERSION
    local = storage.GeoPackageStorage(path)
    tables = []
    for layer_def in model.LAYERS:
        layer = local.make_layer(layer_def)
        if layer.isValid():
            tables.append((layer_def, checkout.read_rows(layer, layer_def)))
        elif older:
            tables.append((layer_def, []))
        else:
            raise TransferError(f"Tabellen {layer_def.name} saknas i {path.name}.")
    return tables


def _count(plan: PostgisStorage, table: str) -> int:
    rows = plan._sql(f'SELECT count(*) FROM {quote(plan.schema)}.{quote(table)} WHERE "plan" = {literal(plan.plan_id)}')
    return int(rows[0][0]) if rows else 0


def _discard(plan: PostgisStorage) -> None:
    """Tar bort allt som hör till planen (för att städa efter en misslyckad import). Fel här döljer inte det första felet."""
    statements = [f'DELETE FROM {quote(plan.schema)}.{quote(layer_def.name)} WHERE "plan" = {literal(plan.plan_id)}'
                  for layer_def in model.LAYERS]
    statements.append(f'DELETE FROM {quote(plan.schema)}.{quote(model.META_TABLE)} WHERE "plan" = {literal(plan.plan_id)}')
    for statement in statements:
        try:
            plan._sql(statement)
        except PostgisError:
            pass


def import_plan(path: Path, connection_name: str, schema: str, plan_id: str, connection=None) -> Imported:
    """Lägger planen i GeoPackage-filen ``path`` som planen ``plan_id`` i ``schema`` i databasen. Schemat skapas om det
    inte finns, och måste annars ha planens koordinatsystem. Kastar ``TransferError`` eller ``PostgisError`` (båda med
    ett meddelande för användaren); då är databasen som förut."""
    path = Path(path)
    meta = read_plan_file(path)
    tables = _read_tables(path, meta)
    plan_meta = {k: v for k, v in meta.items() if k not in _NOT_PLAN_META}
    plan = storage.create_postgis_plan(connection_name, schema, plan_id, int(meta["epsg"]), plan_meta, connection)
    try:
        lock = checkout.acquire_lock(plan)  # incheckningens SQL kräver ett lås, och det släpps av samma SQL
        plan._sql(checkout.checkin_sql(schema, plan_id, int(meta["epsg"]), lock.token, tables))
        counts = {layer_def.name: len(rows) for layer_def, rows in tables}
        for name, expected in counts.items():
            found = _count(plan, name)
            if found != expected:
                raise TransferError(f"Importen blev inte komplett: tabellen {name} fick {found} av {expected} rader.")
    except Exception:
        _discard(plan)
        raise
    return Imported(plan, counts)


def export_plan(plan: PostgisStorage, path: Path) -> Path:
    """Sparar planen som en ny GeoPackage på ``path``. Kastar ``TransferError`` om filen redan finns eller något går fel
    (då lämnas ingen halv fil kvar). Är schemat i databasen från en äldre version uppgraderas det först, som när en plan
    öppnas."""
    path = Path(path)
    if path.exists():
        raise TransferError(f"{path.name} finns redan.")
    message = ""
    try:
        plan.upgrade()
        checkout.copy_to_geopackage(plan, path)
    except (checkout.CheckoutError, PostgisError) as exc:
        message = str(exc)
    except Exception as exc:  # noqa: BLE001 - användaren ska få ett meddelande, och ingen halv fil
        message = f"Kunde inte exportera planen: {exc}"
    if message:
        # Bara texten sparas: felet och de lager som hölls öppna mot filen släpps först, annars går filen inte att ta bort
        # på Windows.
        gc.collect()
        checkout.remove_copy(path)
        raise TransferError(message)
    geopackage.checkpoint(path)  # filen ska vara komplett även om bara .gpkg-filen kopieras vidare
    return path


def unique_export_paths(folder: Path, plans: list[PostgisStorage], suffix: str = ".gpkg") -> list[tuple[PostgisStorage, Path]]:
    """Filnamn i ``folder`` för planerna: planens id och ``suffix``. Heter två planer i olika scheman lika får de schemat
    som prefix."""
    plan_ids = [plan.plan_id for plan in plans]
    return [(plan, Path(folder) / ((plan.plan_id if plan_ids.count(plan.plan_id) == 1
                                    else f"{plan.schema}_{plan.plan_id}") + suffix)) for plan in plans]


def copy_plan(source: PostgisStorage, connection_name: str, schema: str, plan_id: str, connection=None) -> Imported:
    """Kopierar planen ``source`` till planen ``plan_id`` i ``schema`` i databasen ``connection_name`` (samma eller en annan
    databas, samma eller ett annat schema). Kopian görs via en tillfällig GeoPackage, så den visar planen som den ligger i
    databasen (inte ändringar som någon har utcheckade) och följer reglerna för ``import_plan``: en plan som redan finns
    skrivs aldrig över, och går något fel tas kopian bort igen."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        path = export_plan(source, Path(folder) / "kopia.gpkg")
        return import_plan(path, connection_name, schema, plan_id, connection)


def delete_sql(schema: str, plan_id: str) -> str:
    """Ett enda SQL-block som i en transaktion tar bort planens rader i alla tabeller och dess uppgifter, om ingen har den
    utcheckad. Metadatatabellen låses medan det görs, så att ingen hinner checka ut planen mitt i (se
    ``checkout.acquire_lock``). Andra planers rader i samma tabeller rörs inte."""
    meta = f"{quote(schema)}.{quote(model.META_TABLE)}"
    plan = literal(plan_id)
    parts = [f"LOCK TABLE {meta} IN EXCLUSIVE MODE;",
             f"IF EXISTS (SELECT 1 FROM {meta} WHERE \"plan\" = {plan} AND \"key\" = {literal(checkout.LOCK_KEY)}) THEN "
             f"RAISE EXCEPTION '{LOCKED_MESSAGE}'; END IF;"]
    parts += [f'DELETE FROM {quote(schema)}.{quote(layer_def.name)} WHERE "plan" = {plan};' for layer_def in model.LAYERS]
    parts.append(f'DELETE FROM {meta} WHERE "plan" = {plan};')
    return "DO $dp$ BEGIN " + " ".join(parts) + " END $dp$"


def delete_plan(plan: PostgisStorage) -> None:
    """Tar bort planen ur databasen. Kastar ``TransferError`` om planen inte finns eller är utcheckad (av någon, även dig:
    kasta utcheckningen eller bryt låset först). Det går inte att ångra: spara en kopia först om planen kan behövas."""
    if "epsg" not in plan.read_meta():
        raise TransferError(f"Planen {plan.plan_id} finns inte i schemat {plan.schema}.")
    lock = checkout.read_lock(plan)
    if lock is not None:
        raise TransferError(f"Planen {plan.plan_id} är utcheckad av {lock.describe()}. {LOCKED_ADVICE}")
    try:
        plan._sql(delete_sql(plan.schema, plan.plan_id))
    except PostgisError as exc:
        raise TransferError(str(exc)) from exc
    if storage.plan_exists(plan.connection, plan.schema, plan.plan_id):
        raise TransferError(f"Planen {plan.plan_id} finns kvar i databasen.")
