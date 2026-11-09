"""Dialogruta för att öppna en detaljplan som ligger i en PostGIS-databas: en översikt över alla planer i databasen,
med uppgifter i kolumner, sortering och filter. Man väljer om planen ska checkas ut för redigering eller öppnas
skrivskyddad (se ``core.checkout``)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QIcon, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                                 QLabel, QLineEdit, QTableView, QVBoxLayout)

from ..core import plan_overview, storage
from ..core.plan_overview import PlanRow

ICONS = Path(__file__).resolve().parent.parent / "icons"
ALL = ""  # filtervärde för "alla"
LOCK_FREE, LOCK_TAKEN = "free", "taken"

# (rubrik, fält i PlanRow) i den ordning kolumnerna visas
COLUMNS = (
    ("Beteckning", "beteckning"),
    ("Namn", "namn"),
    ("Syfte", "syfte"),
    ("Planstatus", "status"),
    ("Plantyp", "typ"),
    ("Diarienummer", "diarienummer"),
    ("Påbörjad", "paborjad"),
    ("Antagande", "antagande"),
    ("Laga kraft", "laga_kraft"),
    ("Genomförandetid (mån)", "genomforandetid"),
    ("Utcheckad av", "utcheckad"),
    ("Schema", "schema"),
    ("Plan-id", "plan_id"),
)
COLUMN_FIELDS = tuple(field for _title, field in COLUMNS)
SYFTE_COLUMN = COLUMN_FIELDS.index("syfte")
SYFTE_WIDTH = 260
ROW_ROLE = Qt.ItemDataRole.UserRole


def natural_key(text: str) -> tuple:
    """Sorteringsnyckel där tal i texten räknas som tal: 1, 2, 3, 10 och 1002 hamnar i den ordningen (inte 1, 10,
    1002, 2, 3), och 1-2 före 1-10. Tomt sorteras sist (vid stigande ordning)."""
    if not text:
        return (1, ())
    parts = re.split(r"(\d+)", text.casefold())
    return (0, tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts if part != ""))


def lock_text(row: PlanRow) -> str:
    if row.lock is None:
        return ""
    return f"Du ({row.lock.since.replace('T', ' ')})" if row.locked_by_me else row.lock.describe().replace(" på ", " · ", 1)


class PlanFilter(QSortFilterProxyModel):
    """Filtrerar planraderna på fritext (alla kolumner) och på planstatus, plantyp, schema och utcheckning. Sorterar
    med tal som tal (se ``natural_key``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.values = {"status": ALL, "typ": ALL, "schema": ALL}
        self.lock_mode = ALL
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.DisplayRole)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        return natural_key(str(left.data() or "")) < natural_key(str(right.data() or ""))

    def set_text(self, text: str) -> None:
        self.text = text.strip().casefold()
        self.invalidateFilter()

    def set_value(self, field: str, value: str) -> None:
        self.values[field] = value
        self.invalidateFilter()

    def set_lock_mode(self, mode: str) -> None:
        self.lock_mode = mode
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        row: Optional[PlanRow] = model.item(source_row, 0).data(ROW_ROLE)
        if row is None:
            return False
        for field, wanted in self.values.items():
            if wanted != ALL and getattr(row, field) != wanted:
                return False
        if self.lock_mode == LOCK_FREE and row.locked:
            return False
        if self.lock_mode == LOCK_TAKEN and not row.locked:
            return False
        if self.text:
            haystack = " ".join(model.item(source_row, column).text() for column in range(model.columnCount()))
            return all(word in haystack.casefold() for word in self.text.split())
        return True


class PostgisPlanDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Öppna detaljplan från databasen")
        self.resize(1100, 560)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self._rows: list[PlanRow] = []
        self.checkout_requested = False
        self.mosaic_requested = False  # användaren valde Planmosaik i stället för att öppna planer

        self.connection = QComboBox()
        for name in sorted(self._connections):
            self.connection.addItem(name, name)
        self.filter_text = QLineEdit()
        self.filter_text.setPlaceholderText("Filtrera: skriv delar av namn, beteckning, syfte, diarienummer …")
        self.filter_text.setClearButtonEnabled(True)
        self.filter_status = self._filter_combo("Alla planstatus")
        self.filter_typ = self._filter_combo("Alla plantyper")
        self.filter_schema = self._filter_combo("Alla scheman")
        self.filter_lock = QComboBox()
        self.filter_lock.addItem("Alla planer", ALL)
        self.filter_lock.addItem("Bara lediga", LOCK_FREE)
        self.filter_lock.addItem("Bara utcheckade", LOCK_TAKEN)

        self.model = QStandardItemModel(0, len(COLUMNS), self)
        self.model.setHorizontalHeaderLabels([title for title, _field in COLUMNS])
        self.proxy = PlanFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # flera planer med Ctrl/Skift
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #b3261e;")
        self.count = QLabel()
        self.hint = QLabel()
        self.hint.setWordWrap(True)

        self.buttons = QDialogButtonBox()
        self.open_checkout = self.buttons.addButton("Checka ut och öppna", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_checkout.setToolTip("Låser planen för andra och skapar en lokal kopia som du redigerar. "
                                      "Du checkar in planen igen när du är klar.")
        self.open_readonly = self.buttons.addButton("Öppna skrivskyddad", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_readonly.setToolTip("Visar planen direkt från databasen utan att låsa den. Den går inte att redigera "
                                      "förrän du checkar ut den.")
        self.open_mosaic = self.buttons.addButton("Planmosaik…", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_mosaic.setIcon(QIcon(str(ICONS / "mosaic.svg")))
        self.open_mosaic.setToolTip("Visar alla planer i schemat tillsammans som en enda skrivskyddad karta, i stället för "
                                    "att öppna planerna var för sig.")
        self.buttons.addButton("Avbryt", QDialogButtonBox.ButtonRole.RejectRole)
        self.open_checkout.clicked.connect(lambda: self._accept_with(True))
        self.open_mosaic.clicked.connect(self._request_mosaic)
        self.open_readonly.clicked.connect(lambda: self._accept_with(False))
        self.buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(QLabel("Databas"))
        top.addWidget(self.connection)
        top.addWidget(self.filter_schema)
        top.addWidget(self.filter_text, 1)
        filters = QHBoxLayout()
        for combo in (self.filter_status, self.filter_typ, self.filter_lock):
            filters.addWidget(combo)
        filters.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.count)
        bottom.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        layout.addWidget(self.hint)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)

        self.connection.currentIndexChanged.connect(self.reload)
        self.filter_text.textChanged.connect(self.proxy.set_text)
        for field, combo in (("status", self.filter_status), ("typ", self.filter_typ), ("schema", self.filter_schema)):
            combo.currentIndexChanged.connect(lambda _i, f=field, c=combo: self.proxy.set_value(f, c.currentData()))
        self.filter_lock.currentIndexChanged.connect(lambda _i: self.proxy.set_lock_mode(self.filter_lock.currentData()))
        self.proxy.layoutChanged.connect(self._update_state)
        self.proxy.rowsInserted.connect(self._update_state)
        self.proxy.rowsRemoved.connect(self._update_state)
        self.proxy.modelReset.connect(self._update_state)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_state())
        self.table.doubleClicked.connect(lambda *_: self._accept_with(False))
        self.table.sortByColumn(COLUMN_FIELDS.index("beteckning"), Qt.SortOrder.AscendingOrder)
        self.reload()

    @staticmethod
    def _filter_combo(everything: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(everything, ALL)
        return combo

    # -- innehåll -------------------------------------------------------------------------------------
    def reload(self, *_) -> None:
        """Läser om översikten över alla planer i alla scheman (skapade med pluginet) i den valda databasen."""
        self._rows = []
        problems = []
        connection = self._connections.get(self.connection.currentData() or "")
        if connection is not None:
            name = self.connection.currentData()
            try:
                schemas = storage.list_plugin_schemas(connection)
            except storage.PostgisError as exc:
                schemas = []
                problems.append(str(exc))
            else:
                if not schemas:
                    problems.append("Databasen innehåller inga scheman skapade med pluginet.")
            for schema in schemas:
                try:
                    self._rows.extend(plan_overview.list_plans(name, connection, schema))
                except storage.PostgisError as exc:
                    problems.append(f"Schemat {schema}: {exc}")
            if schemas and not self._rows and not problems:
                problems.append("Databasen innehåller inga planer.")
        self.error.setText("\n".join(problems))
        self._fill()

    def _fill(self) -> None:
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        grey = QBrush(QColor("#7a7a7a"))
        for row in self._rows:
            items = []
            for _title, field in COLUMNS:
                text = lock_text(row) if field == "utcheckad" else getattr(row, field)
                item = QStandardItem(text)
                item.setEditable(False)
                if field == "genomforandetid":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if field == "syfte" and text:
                    item.setToolTip(text)
                if row.locked_by_other:
                    item.setForeground(grey)
                items.append(item)
            items[0].setData(row, ROW_ROLE)
            if row.lock is not None:
                items[COLUMN_FIELDS.index("utcheckad")].setToolTip(f"Utcheckad av {row.lock.describe()}")
            self.model.appendRow(items)
        self._fill_filters()
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        if self.table.columnWidth(SYFTE_COLUMN) > SYFTE_WIDTH:
            self.table.setColumnWidth(SYFTE_COLUMN, SYFTE_WIDTH)
        self._update_state()

    def _fill_filters(self) -> None:
        """Fyller filterlistorna med de värden som finns i databasen (och behåller ett val som fortfarande finns)."""
        for field, combo in (("status", self.filter_status), ("typ", self.filter_typ), ("schema", self.filter_schema)):
            previous = combo.currentData()
            combo.blockSignals(True)
            while combo.count() > 1:
                combo.removeItem(1)
            for value in sorted({getattr(r, field) for r in self._rows if getattr(r, field)}, key=str.casefold):
                combo.addItem(value, value)
            index = combo.findData(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
            self.proxy.values[field] = combo.currentData()
        self.proxy.invalidateFilter()

    # -- val -------------------------------------------------------------------------------------------
    def selected_rows(self) -> list[PlanRow]:
        """De valda planerna, i den ordning de visas."""
        indexes = sorted(self.table.selectionModel().selectedRows(), key=lambda index: index.row())
        return [self.model.item(self.proxy.mapToSource(index).row(), 0).data(ROW_ROLE) for index in indexes]

    def selections(self) -> list[tuple[str, str, str]]:
        """(anslutning, schema, plan-id) för varje vald plan."""
        return [(row.connection, row.schema, row.plan_id) for row in self.selected_rows()]

    def _request_mosaic(self) -> None:
        self.mosaic_requested = True
        self.accept()

    def mosaic_target(self) -> tuple[Optional[str], Optional[str]]:
        """Databasen och schemat som är valda i dialogen (schemat är None när alla scheman visas), som utgångsläge för
        planmosaiken."""
        return self.connection.currentData() or None, self.filter_schema.currentData() or None

    def _accept_with(self, check_out: bool) -> None:
        rows = self.selected_rows()
        if not rows or (check_out and any(row.locked_by_other for row in rows)):
            return
        self.checkout_requested = check_out
        self.accept()

    def _update_state(self, *_) -> None:
        total, shown = self.model.rowCount(), self.proxy.rowCount()
        rows = self.selected_rows()
        self.count.setText(f"Synliga: {shown} av {total}   ·   Valda: {len(rows)}")
        taken = [row for row in rows if row.locked_by_other]
        self.open_readonly.setEnabled(bool(rows))
        self.open_mosaic.setEnabled(bool(self.connection.count()))
        self.open_checkout.setEnabled(bool(rows) and not taken)
        if not rows:
            self.hint.setText("Välj en eller flera planer i listan (Ctrl eller Skift för flera).")
        elif len(rows) == 1 and taken:
            self.hint.setText(f"Planen är utcheckad av {rows[0].lock.describe()}. Den kan öppnas skrivskyddad men inte "
                              "checkas ut förrän den har checkats in.")
        elif taken:
            names = ", ".join(row.beteckning or row.plan_id for row in taken)
            self.hint.setText(f"{len(taken)} av de valda planerna är utcheckade av någon annan ({names}). Du kan öppna "
                              "dem skrivskyddade, men inte checka ut dem. Välj bort dem för att checka ut resten.")
        elif len(rows) == 1 and rows[0].locked_by_me:
            self.hint.setText("Du har själv checkat ut planen. Checka ut igen för att fortsätta redigera din kopia.")
        elif len(rows) > 1:
            self.hint.setText(f"{len(rows)} planer valda. Checka ut och öppna låser och hämtar var och en av dem, "
                              "en i taget. Den sist öppnade planen blir den aktiva.")
        else:
            self.hint.setText("Checka ut för att redigera planen. Öppna skrivskyddad för att bara titta på den.")
