"""Val av databas och schema i dialogerna som lägger planer i en databas (importera, kopiera)."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtWidgets import QComboBox, QFormLayout

from ..core import storage

DEFAULT_SCHEMA = "detaljplaner"


class DatabaseTarget:
    """En lista med QGIS sparade databasanslutningar och en lista med databasens scheman (pluginets, men ett nytt schema
    kan skrivas in). Fälten, ``connection`` och ``schema``, läggs i dialogens formulär med ``add_rows``."""

    def __init__(self, connections: dict, connection: Optional[str] = None, schema: Optional[str] = None):
        self._connections = connections
        self.connection = QComboBox()
        for name in sorted(connections):
            self.connection.addItem(name, name)
        if connection and self.connection.findData(connection) >= 0:
            self.connection.setCurrentIndex(self.connection.findData(connection))
        self.schema = QComboBox()
        self.schema.setEditable(True)
        self.schema.setToolTip("Schemat i databasen som planen läggs i. Delas av alla planer där: finns det redan måste "
                               "det ha planens koordinatsystem, annars skapas det. Gemener a–z, siffror och understreck.")
        self._fill_schemas(schema)
        self.connection.currentIndexChanged.connect(lambda _i: self._fill_schemas(None))

    def add_rows(self, form: QFormLayout) -> None:
        form.addRow("Databas", self.connection)
        form.addRow("Schema", self.schema)

    def _fill_schemas(self, wanted: Optional[str]) -> None:
        previous = wanted or self.schema.currentText()
        self.schema.clear()
        connection = self._connections.get(self.connection.currentData() or "")
        if connection is not None:
            try:
                self.schema.addItems(storage.list_plugin_schemas(connection))
            except storage.PostgisError:
                pass  # ett nytt schema går ändå att skriva in; felet kommer när databasen används
        self.schema.setCurrentText(previous or (self.schema.itemText(0) if self.schema.count() else DEFAULT_SCHEMA))

    def connection_name(self) -> str:
        return self.connection.currentData() or ""

    def schema_name(self) -> str:
        return self.schema.currentText().strip()

    def is_valid(self) -> bool:
        return bool(self.connection_name()) and storage.is_valid_schema(self.schema_name())
