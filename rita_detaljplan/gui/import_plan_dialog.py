"""Dialogruta för att importera en plan till en PostGIS-databas: ur en GeoPackage-fil (se ``core.transfer``) eller ur en
leverans i Lantmäteriets JSON-format (se ``json_transfer``)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qgis.core import QgsCoordinateReferenceSystem
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
                                 QWidget)

from .. import json_transfer
from ..core import geopackage, storage, transfer
from .database_target import DatabaseTarget
from .kommun_combo import KommunCombo

ICONS = Path(__file__).resolve().parent.parent / "icons"
GEOPACKAGE, JSON = "geopackage", "json"  # vilken sorts fil som valts


@dataclass(frozen=True)
class ImportValues:
    path: Path
    connection: str
    schema: str
    plan_id: str
    kind: str = GEOPACKAGE
    kommun: str = ""  # bara för en leverans (JSON): kommun, kommunkod och koordinatsystem följer inte med filen
    kommunkod: str = ""
    epsg: int = 0


class ImportPlanDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None, connection: Optional[str] = None,
                 schema: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Importera plan till databasen")
        self.setMinimumWidth(520)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self._plan_edited = False  # användaren har valt plan-id själv: föreslå inte över det
        self._kind, self._description, self._problem = "", "", ""  # om filen: sorten, vad den innehåller, varför den inte duger

        self.file = QgsFileWidget()
        self.file.setFilter("Planer (*.gpkg *.json);;GeoPackage (*.gpkg);;Leverans, JSON (*.json)")
        self.file.setDialogTitle("Välj planens GeoPackage eller leverans")
        self.target = DatabaseTarget(self._connections, connection, schema)
        self.connection, self.schema = self.target.connection, self.target.schema
        self.plan_id = QLineEdit()
        self.plan_id.setPlaceholderText("plan-id, t.ex. kv_vaktaren_1_2")
        self.plan_id.setToolTip("Planens identifierare inom schemat (måste vara unik där). Gemener a–z, siffror och "
                                "understreck.")
        # en leverans (JSON) saknar kommunkod och koordinatsystem: de anges här, som för en ny plan
        self.kommun = KommunCombo()
        self.crs = QComboBox()
        for epsg in geopackage.epsg_codes():
            self.crs.addItem(f"EPSG:{epsg} – {QgsCoordinateReferenceSystem(f'EPSG:{epsg}').description()}", epsg)
        self.delivery_box = QWidget()
        delivery_form = QFormLayout(self.delivery_box)
        delivery_form.setContentsMargins(0, 0, 0, 0)
        delivery_form.addRow("Kommun", self.kommun)
        delivery_form.addRow("Koordinatsystem", self.crs)
        self.delivery_box.setVisible(False)
        self.info = QLabel()
        self.info.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Planfil", self.file)
        self.target.add_rows(form)
        form.addRow("Plan-id", self.plan_id)
        form.addRow("", self.delivery_box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.setWindowIcon(QIcon(str(ICONS / "import_plan.svg")))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Importera")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setIcon(QIcon(str(ICONS / "import_plan.svg")))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(self.buttons)

        self.file.fileChanged.connect(self._file_changed)
        self.connection.currentIndexChanged.connect(self._update)
        self.schema.currentTextChanged.connect(self._update)
        self.plan_id.textEdited.connect(self._plan_id_edited)
        self.plan_id.textChanged.connect(self._update)
        self.kommun.currentTextChanged.connect(self._update)
        self._update()

    def _plan_id_edited(self, *_) -> None:
        self._plan_edited = True

    def _file_changed(self, path: str) -> None:
        """Läser filen en gång (inte för varje tangent i de andra fälten) och föreslår plan-id och kommun."""
        self._kind, self._description, self._problem = self._inspect(path.strip())
        if not self._plan_edited:
            self.plan_id.setText(storage.schema_name(Path(path).stem))
        self.delivery_box.setVisible(self._kind == JSON)
        self._update()

    def _inspect(self, path: str) -> tuple[str, str, str]:
        """(sort, vad filen innehåller, varför den inte duger) för filen; tomt om ingen fil är vald."""
        if not path:
            return "", "", ""
        try:
            if path.lower().endswith(".json"):
                _collection, plan = json_transfer.read_delivery(Path(path))
                self.kommun.set_kommun(plan.attrs.get("kommun"))
                return JSON, (f"Leverans av en detaljplan med {len(plan.areas)} ytor. Kommunen och koordinatsystemet följer "
                              "inte med filen: ange dem nedan."), ""
            meta = transfer.read_plan_file(Path(path))
            return GEOPACKAGE, f"Koordinatsystem EPSG:{meta['epsg']}. Ett schema som redan finns måste ha samma.", ""
        except transfer.TransferError as exc:
            return "", "", str(exc)

    def is_valid(self) -> bool:
        return bool(self._kind) and self.target.is_valid() and storage.is_valid_plan_id(self.plan_id.text().strip()) \
            and (self._kind != JSON or self.kommun.selected() is not None)

    def _update(self, *_) -> None:
        self.info.setText(self._description or self._problem)
        self.info.setStyleSheet("color: #b3261e;" if self._problem else "")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.is_valid())

    def values(self) -> ImportValues:
        kommun = self.kommun.selected() if self._kind == JSON else None
        return ImportValues(Path(self.file.filePath().strip()), self.target.connection_name(), self.target.schema_name(),
                            self.plan_id.text().strip(), self._kind or GEOPACKAGE,
                            kommun.namn if kommun else "", kommun.kod if kommun else "",
                            int(self.crs.currentData(Qt.ItemDataRole.UserRole)) if kommun else 0)
