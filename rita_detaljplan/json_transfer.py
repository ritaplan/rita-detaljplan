"""JSON-leveranser (Lantmäteriets format, se ``core.export_ngp`` och ``core.import_ngp``) till och från planer i databasen,
för databashanteraren.

* **Exportera** sparar en plan ur databasen som en leverans, utan att öppna den i projektet: planen kopieras till en
  tillfällig GeoPackage (se ``core.transfer.export_plan``), läses in i ett eget, fristående projekt och exporteras som
  vid *Leverans och export*. Det ändrar inget i databasen eller i det öppna projektet.
* **Importera** bygger en ny plan av en leverans i en tillfällig GeoPackage, på samma sätt som *Importera leverans
  (JSON)* gör för en plan i en fil, och lägger sedan den planen i databasen (se ``core.transfer.import_plan``).

Modulen ligger bredvid ``controller`` och inte i ``core``, eftersom importen använder styrenheten (som skriver
ytorna och bestämmelserna till planens lager).
"""
from __future__ import annotations

import gc
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from qgis.core import QgsProject

from .controller import ImportSummary, PlanController
from .core import catalog as cat
from .core import export_ngp, geopackage, validation
from .core import import_ngp as import_ngp_module
from .core import transfer
from .core.project import load_plan
from .core.storage import PostgisStorage
from .core.transfer import TransferError


@dataclass(frozen=True)
class DeliveryImported:
    imported: transfer.Imported
    summary: ImportSummary


def read_delivery(path: Path) -> tuple[dict, import_ngp_module.ImportedPlan]:
    """Filen som JSON och tolkad som en leverans av en detaljplan. Kastar ``TransferError`` med en förklaring om den inte
    går att läsa eller inte är en leverans."""
    path = Path(path)
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise TransferError(f"Kunde inte läsa {path.name}: {exc}") from exc
    try:
        return collection, import_ngp_module.parse(collection)
    except import_ngp_module.ImportError_ as exc:
        raise TransferError(f"{path.name} är ingen leverans av en detaljplan: {exc}") from exc


def import_delivery(path: Path, connection_name: str, schema: str, plan_id: str, kommun: str, kommunkod: str, epsg: int,
                    catalog: cat.Catalog, connection=None) -> DeliveryImported:
    """Lägger leveransen i ``path`` som en ny plan i databasen. Kommun, kommunkod och koordinatsystem anges här eftersom
    de inte följer med leveransen. Bestämmelser som inte finns i ``catalog`` hoppas över (se ``summary.warnings``).
    Kastar ``TransferError`` eller ``PostgisError``; då är databasen som förut."""
    collection, _plan = read_delivery(path)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        gpkg = geopackage.create_geopackage(Path(folder) / "plan.gpkg", epsg, {"kommun": kommun, "kommunkod": kommunkod})
        project = QgsProject()  # fristående: rör inte användarens öppna projekt
        problems: list[str] = []
        controller = PlanController(problems.append, lambda _text: None, project=project)
        try:
            load_plan(gpkg, project)
            summary = controller.import_ngp(collection, catalog)
            problems += controller.stop_editing(save=True)
        except (RuntimeError, ValueError) as exc:
            raise TransferError(f"Kunde inte bygga planen av {Path(path).name}: {exc}") from exc
        finally:
            controller.detach()
            controller.deleteLater()
            project.clear()
            del controller, project
            gc.collect()  # lagren släpper filen, annars går den inte att ta bort på Windows
        if problems:
            raise TransferError(f"Kunde inte spara planen byggd av {Path(path).name}: {'; '.join(problems)}")
        imported = transfer.import_plan(gpkg, connection_name, schema, plan_id, connection)
    return DeliveryImported(imported, summary)


def export_delivery(plan: PostgisStorage, path: Path) -> Path:
    """Sparar planen som en leverans (JSON) på ``path``. Kastar ``TransferError`` om filen redan finns, planen saknar
    planområde eller något annat går fel."""
    path = Path(path)
    if path.exists():
        raise TransferError(f"{path.name} finns redan.")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        gpkg = transfer.export_plan(plan, Path(folder) / "plan.gpkg")
        project = QgsProject()
        message = ""
        try:
            load_plan(gpkg, project)
            text = export_ngp.dumps(export_ngp.export_plan(validation.collect(project)))
        except (ValueError, RuntimeError) as exc:
            message = f"Kunde inte exportera planen {plan.plan_id}: {exc}"
        finally:
            project.clear()
            del project
            gc.collect()
    if message:
        raise TransferError(message)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise TransferError(f"Kunde inte skriva {path.name}: {exc}") from exc
    return path
