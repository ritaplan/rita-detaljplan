"""Dialogruta för att öppna en planmosaik: alla planer i ett schema, för de planstatusar man väljer."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
                                 QWidget)

from ..core import codelists, mosaic, storage


class MosaicDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None, connection: Optional[str] = None,
                 schema: Optional[str] = None):
        """``connection`` och ``schema`` är det som redan är valt när dialogen öppnas (om de finns)."""
        super().__init__(parent)
        self.setWindowTitle("Öppna planmosaik")
        self.resize(460, 420)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self._checks: dict[str, QCheckBox] = {}
        self._counts: dict[str, int] = {}

        scale = f"{mosaic.DETAIL_SCALE:,}".replace(",", " ")
        self.intro = QLabel("En planmosaik visar alla planer i ett schema tillsammans, som en enda skrivskyddad karta. "
                       "Välj vilka planer som ska med efter deras planstatus. Användning och egenskaper ritas från "
                       f"skalan 1:{scale}.")
        self.intro.setWordWrap(True)
        self.connection = QComboBox()
        for name in sorted(self._connections):
            self.connection.addItem(name, name)
        self.schema = QComboBox()
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #b3261e;")
        self.status_box = QWidget()
        self.status_layout = QVBoxLayout(self.status_box)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()

        self.buttons = QDialogButtonBox()
        self.open_button = self.buttons.addButton("Öppna planmosaik", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton("Avbryt", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Databas", self.connection)
        form.addRow("Schema", self.schema)
        form.addRow("Planstatus", self.status_box)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(self.error)
        layout.addStretch(1)
        layout.addWidget(self.buttons)

        if connection is not None and self.connection.findData(connection) >= 0:
            self.connection.setCurrentIndex(self.connection.findData(connection))
        self.connection.currentIndexChanged.connect(self._load_schemas)
        self.schema.currentIndexChanged.connect(self._load_statuses)
        self._load_schemas()
        if schema is not None and self.schema.findData(schema) >= 0:
            self.schema.setCurrentIndex(self.schema.findData(schema))

    # -- innehåll -------------------------------------------------------------------------------------
    def _connection(self):
        return self._connections.get(self.connection.currentData() or "")

    def _load_schemas(self, *_) -> None:
        self.schema.blockSignals(True)
        self.schema.clear()
        problem = ""
        connection = self._connection()
        if connection is not None:
            try:
                for name in storage.list_plugin_schemas(connection):
                    self.schema.addItem(name, name)
            except storage.PostgisError as exc:
                problem = str(exc)
            if not self.schema.count() and not problem:
                problem = "Databasen innehåller inga scheman skapade med pluginet."
        self.schema.blockSignals(False)
        self._load_statuses()  # rensar felrutan
        if problem:
            self.error.setText(problem)

    def _load_statuses(self, *_) -> None:
        """En ruta per planstatus som finns i schemat, med antal planer. Förvalt: de som gäller (antagen, laga kraft)."""
        self.error.setText("")
        self.error.setToolTip("")
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._checks = {}
        connection, schema = self._connection(), self.schema.currentData()
        counts: dict[str, int] = {}
        if connection is not None and schema:
            try:
                counts = storage.count_plans_by_status(connection, schema)
            except storage.PostgisError as exc:
                self.error.setText(f"Planerna i schemat {schema} kan inte visas som mosaik: det saknar planernas tabeller "
                                   "eller är skapat med en äldre version av pluginet.")
                self.error.setToolTip(str(exc))
        order = {status: i for i, status in enumerate(codelists.PLANSTATUS)}
        for status in sorted(counts, key=lambda s: (order.get(s, len(order)), s)):
            check = QCheckBox(f"{mosaic.status_label(status)} ({counts[status]})")
            check.setChecked(status in mosaic.DEFAULT_STATUSES)
            check.toggled.connect(self._update_state)
            self.status_layout.addWidget(check)
            self._checks[status] = check
        self._counts = counts
        self._update_state()

    def _update_state(self, *_) -> None:
        chosen = self.statuses()
        plans = sum(self._counts.get(status, 0) for status in chosen)
        self.open_button.setEnabled(bool(chosen) and self.schema.currentData() is not None)
        self.summary.setText(f"{plans} planer ingår." if chosen else "Välj minst en planstatus.")

    # -- val -------------------------------------------------------------------------------------------
    def statuses(self) -> list[str]:
        """De valda planstatusarna (tom text = planer utan status), i samma ordning som i listan."""
        return [status for status, check in self._checks.items() if check.isChecked()]

    def selection(self) -> Optional[tuple[str, str, list[str]]]:
        """(anslutning, schema, planstatusar), eller None om något saknas."""
        schema, statuses = self.schema.currentData(), self.statuses()
        if not schema or not statuses:
            return None
        return self.connection.currentData(), schema, statuses

    def plan_count(self) -> int:
        return sum(self._counts.get(status, 0) for status in self.statuses())
