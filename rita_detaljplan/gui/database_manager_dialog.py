"""Databashanteraren: en översikt över alla planer i en PostGIS-databas, med uppgifter i kolumner, sortering och filter.
Härifrån öppnar man planer (utcheckade för redigering eller skrivskyddade, se ``core.checkout``), visar dem som en
planmosaik och flyttar planer mellan databasen och filer: importerar en GeoPackage eller en leverans (JSON) till
databasen och exporterar valda planer som GeoPackage eller leverans, kopierar planer, tar bort dem och bryter lås på
utcheckade planer (se ``core.transfer`` och ``json_transfer``). Planer som inte får ändras, till exempel detaljplaner med
laga kraft, skrivskyddas här, och skyddet bryts här (se ``core.protection``)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from qgis.PyQt.QtCore import QModelIndex, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QIcon, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                 QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                                 QMessageBox, QTableView, QToolButton, QVBoxLayout)

from .. import json_transfer
from ..core import checkout, plan_overview, storage, transfer
from ..core.plan_overview import PlanRow
from .copy_plan_dialog import CopyPlanDialog
from .import_plan_dialog import JSON, ImportPlanDialog

ICONS = Path(__file__).resolve().parent.parent / "icons"
ALL = ""  # filtervärde för "alla"
LOCK_FREE, LOCK_TAKEN = "free", "taken"
PROTECTED, EDITABLE = "protected", "editable"

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
    ("Skrivskydd", "skrivskydd"),
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


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / name))


class Banner(QLabel):
    """En rad med ett meddelande, markerad med en färgad kant. Syns bara när den har text."""

    def __init__(self, colour: str):
        super().__init__()
        shade = QColor(colour)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setStyleSheet(f"border-left: 4px solid {colour}; padding: 6px 10px; "
                           f"background: rgba({shade.red()}, {shade.green()}, {shade.blue()}, 36);")
        self.setVisible(False)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self) -> None:
        self.setText("")


def lock_text(row: PlanRow) -> str:
    if row.lock is None:
        return ""
    return f"Du ({row.lock.since.replace('T', ' ')})" if row.locked_by_me else row.lock.describe().replace(" på ", " · ", 1)


def protection_text(row: PlanRow) -> str:
    return "Skrivskyddad" if row.protected else ""


class PlanFilter(QSortFilterProxyModel):
    """Filtrerar planraderna på fritext (alla kolumner) och på planstatus, plantyp, schema, utcheckning och skrivskydd.
    Sorterar med tal som tal (se ``natural_key``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.values = {"status": ALL, "typ": ALL, "schema": ALL}
        self.lock_mode = ALL
        self.protect_mode = ALL
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

    def set_protect_mode(self, mode: str) -> None:
        self.protect_mode = mode
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
        if self.protect_mode == PROTECTED and not row.protected:
            return False
        if self.protect_mode == EDITABLE and row.protected:
            return False
        if self.text:
            haystack = " ".join(model.item(source_row, column).text() for column in range(model.columnCount()))
            return all(word in haystack.casefold() for word in self.text.split())
        return True


class DatabaseManagerDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None, catalog_provider: Optional[Callable] = None):
        """``catalog_provider`` ger planbestämmelsekatalogen, som behövs för att importera en leverans (JSON)."""
        super().__init__(parent)
        self._catalog_provider = catalog_provider
        self.setWindowTitle("Databashanteraren")
        self.setWindowIcon(icon("database.svg"))
        self.resize(1180, 620)
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
        self.filter_protect = QComboBox()
        self.filter_protect.addItem("Alla, med och utan skrivskydd", ALL)
        self.filter_protect.addItem("Bara skrivskyddade", PROTECTED)
        self.filter_protect.addItem("Bara redigerbara", EDITABLE)

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

        self.error = Banner("#b3261e")  # vad som gick fel, eller hoppades över
        self.notice = Banner("#1b7f3b")  # vad som just gjordes (import, export, kopiering …)
        self.count = QLabel()
        self.hint = QLabel()
        self.hint.setWordWrap(True)

        # öppna: knapparna längst ned, med utcheckning som det vanliga valet
        self.buttons = QDialogButtonBox()
        self.open_checkout = self.buttons.addButton("Checka ut och öppna", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_checkout.setIcon(icon("checkout.svg"))
        self.open_checkout.setDefault(True)
        self.open_checkout.setToolTip("Låser planen för andra och skapar en lokal kopia som du redigerar. "
                                      "Du checkar in planen igen när du är klar.")
        self.open_readonly = self.buttons.addButton("Öppna skrivskyddad", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_readonly.setIcon(icon("view.svg"))
        self.open_readonly.setToolTip("Visar planen direkt från databasen utan att låsa den. Den går inte att redigera "
                                      "förrän du checkar ut den.")
        self.open_mosaic = self.buttons.addButton("Planmosaik…", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_mosaic.setIcon(icon("mosaic.svg"))
        self.open_mosaic.setToolTip("Visar alla planer i schemat tillsammans som en enda skrivskyddad karta, i stället för "
                                    "att öppna planerna var för sig.")
        self.buttons.addButton("Avbryt", QDialogButtonBox.ButtonRole.RejectRole)

        # hantera: flata knappar med ikon på en rad under listan, grupperade efter vad de gör
        self.import_plan = self._tool("Importera plan…", "import_plan.svg",
                                      "Lägger en plan ur en GeoPackage eller en leverans (JSON) i databasen som en ny plan.")
        self.export_plans = self._tool("Exportera valda", "export_plan.svg",
                                       "Sparar de valda planerna som filer i en mapp: GeoPackage eller leverans (JSON). Filerna "
                                       "visar planerna som de ligger i databasen, utan ändringar som någon har utcheckade.")
        export_menu = QMenu(self.export_plans)
        self.export_geopackage = export_menu.addAction("Som GeoPackage (.gpkg)…")
        self.export_json = export_menu.addAction("Som leverans, JSON (.json)…")
        self.export_plans.setMenu(export_menu)
        self.export_plans.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.copy_plans = self._tool("Kopiera plan…", "duplicate.svg",
                                     "Gör en ny plan av de valda planerna, i samma eller en annan databas eller ett annat "
                                     "schema.")
        self.protect_plans = self._tool("Skrivskydda…", "protect.svg",
                                        "Skrivskyddar de valda planerna, till exempel detaljplaner som har vunnit laga kraft. "
                                        "En skrivskyddad plan kan öppnas, exporteras och kopieras, men inte checkas ut eller "
                                        "tas bort förrän skyddet bryts.")
        self.unprotect_plans = self._tool("Bryt skrivskydd…", "unprotect.svg",
                                          "Tar bort skrivskyddet på de valda planerna, så att de kan checkas ut, ändras och "
                                          "tas bort igen.")
        self.delete_plans = self._tool("Ta bort plan…", "delete.svg",
                                       "Tar bort de valda planerna ur databasen. Det går inte att ångra, men du kan spara en "
                                       "säkerhetskopia först. Planer som är utcheckade eller skrivskyddade kan inte tas bort.")
        self.delete_plans.setStyleSheet("QToolButton:enabled { color: #b3261e; }")
        self.break_locks = self._tool("Bryt lås…", "unlock.svg",
                                      "Tar bort utcheckningen av de valda planerna. Den som hade planen utcheckad kan då inte "
                                      "längre checka in sina ändringar.")
        self.refresh = self._tool("", "refresh.svg", "Läser om listan över planer.")
        self.open_checkout.clicked.connect(lambda: self._accept_with(True))
        self.open_mosaic.clicked.connect(self._request_mosaic)
        self.import_plan.clicked.connect(self._import_plan)
        self.copy_plans.clicked.connect(self._copy_plans)
        self.protect_plans.clicked.connect(self._protect_plans)
        self.unprotect_plans.clicked.connect(self._unprotect_plans)
        self.delete_plans.clicked.connect(self._delete_plans)
        self.break_locks.clicked.connect(self._break_locks)
        self.refresh.clicked.connect(lambda _checked=False: self.reload())
        self.export_geopackage.triggered.connect(lambda _checked=False: self._export_plans(transfer.export_plan, ".gpkg"))
        self.export_json.triggered.connect(lambda _checked=False: self._export_plans(json_transfer.export_delivery, ".json"))
        self.open_readonly.clicked.connect(lambda: self._accept_with(False))
        self.buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(QLabel("Databas"))
        top.addWidget(self.connection)
        top.addWidget(self.filter_schema)
        top.addWidget(self.filter_text, 1)
        top.addWidget(self.refresh)
        filters = QHBoxLayout()
        for combo in (self.filter_status, self.filter_typ, self.filter_lock, self.filter_protect):
            filters.addWidget(combo)
        filters.addStretch(1)
        manage = QHBoxLayout()  # hantera planerna i databasen: till och från filer | på plats | skydd och lås
        manage.addWidget(self.import_plan)
        manage.addWidget(self.export_plans)
        manage.addWidget(self._separator())
        manage.addWidget(self.copy_plans)
        manage.addWidget(self.delete_plans)
        manage.addWidget(self._separator())
        for button in (self.protect_plans, self.unprotect_plans, self.break_locks):
            manage.addWidget(button)
        manage.addStretch(1)
        manage.addWidget(self.count)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addLayout(manage)
        layout.addWidget(self.hint)
        layout.addWidget(self.notice)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)

        self.connection.currentIndexChanged.connect(self.reload)
        self.filter_text.textChanged.connect(self.proxy.set_text)
        for field, combo in (("status", self.filter_status), ("typ", self.filter_typ), ("schema", self.filter_schema)):
            combo.currentIndexChanged.connect(lambda _i, f=field, c=combo: self.proxy.set_value(f, c.currentData()))
        self.filter_lock.currentIndexChanged.connect(lambda _i: self.proxy.set_lock_mode(self.filter_lock.currentData()))
        self.filter_protect.currentIndexChanged.connect(
            lambda _i: self.proxy.set_protect_mode(self.filter_protect.currentData()))
        self.proxy.layoutChanged.connect(self._update_state)
        self.proxy.rowsInserted.connect(self._update_state)
        self.proxy.rowsRemoved.connect(self._update_state)
        self.proxy.modelReset.connect(self._update_state)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_state())
        self.table.doubleClicked.connect(lambda *_: self._accept_with(False))
        self.table.sortByColumn(COLUMN_FIELDS.index("beteckning"), Qt.SortOrder.AscendingOrder)
        self.reload()

    @staticmethod
    def _tool(text: str, icon_name: str, tooltip: str) -> QToolButton:
        """En flat knapp med ikon (och text bredvid) för att hantera planerna."""
        button = QToolButton()
        button.setText(text)
        button.setIcon(icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly)
        return button

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

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
        self.notice.clear()
        self._fill()

    def _fill(self) -> None:
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        grey = QBrush(QColor("#7a7a7a"))
        padlock = icon("lock.svg")
        shield = icon("shield.svg")
        for row in self._rows:
            items = []
            for _title, field in COLUMNS:
                text = lock_text(row) if field == "utcheckad" else protection_text(row) if field == "skrivskydd" \
                    else getattr(row, field)
                item = QStandardItem(text)
                item.setEditable(False)
                if field == "genomforandetid":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if field == "syfte" and text:
                    item.setToolTip(text)
                if field == "utcheckad" and row.locked:
                    item.setIcon(padlock)
                if field == "skrivskydd" and row.protected:
                    item.setIcon(shield)
                if row.locked_by_other:
                    item.setForeground(grey)
                items.append(item)
            items[0].setData(row, ROW_ROLE)
            if row.lock is not None:
                items[COLUMN_FIELDS.index("utcheckad")].setToolTip(f"Utcheckad av {row.lock.describe()}")
            if row.protection is not None:
                items[COLUMN_FIELDS.index("skrivskydd")].setToolTip(f"Skrivskyddad av {row.protection.describe()}")
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

    # -- flytta planer mellan databasen och filer ---------------------------------------------------------
    def _plan_storage(self, row: PlanRow) -> storage.PostgisStorage:
        return storage.PostgisStorage(row.connection, row.schema, row.plan_id, self._connections.get(row.connection))

    def _import_plan(self) -> None:
        dialog = ImportPlanDialog(self, self._connections, self.connection.currentData(),
                                  self.filter_schema.currentData() or None)
        if not dialog.exec():
            return
        values = dialog.values()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            summary, warnings = self._run_import(values)
        except (transfer.TransferError, storage.PostgisError) as exc:
            self.error.setText(f"Kunde inte importera {values.path.name}: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.connection.setCurrentIndex(self.connection.findData(values.connection))
        self.reload()
        self._select(values.schema, values.plan_id)
        self.notice.setText(f"Importerade {values.path.name} som {values.plan_id} i schemat {values.schema}: {summary}.")
        self.error.setText("\n".join(warnings))  # det som hoppades över (listans omläsning tömde fältet)

    def _run_import(self, values) -> tuple[str, tuple]:
        """Importerar planen. Returnerar en beskrivning av vad som lades in och varningar (det som hoppades över). Kastar
        ``TransferError`` eller ``PostgisError``."""
        connection = self._connections.get(values.connection)
        if values.kind != JSON:
            imported = transfer.import_plan(values.path, values.connection, values.schema, values.plan_id, connection)
            return f"{imported.total} objekt", ()
        if self._catalog_provider is None:
            raise transfer.TransferError("Planbestämmelsekatalogen saknas, och den behövs för att läsa en leverans.")
        result = json_transfer.import_delivery(values.path, values.connection, values.schema, values.plan_id, values.kommun,
                                               values.kommunkod, values.epsg, self._catalog_provider(), connection)
        return f"{result.summary.provisions} bestämmelser på {result.summary.areas} ytor", result.summary.warnings

    def _select(self, schema: str, plan_id: str) -> None:
        """Markerar planen i listan (schemafiltret släpps om det döljer den)."""
        self.filter_schema.setCurrentIndex(max(self.filter_schema.findData(schema), 0))
        for row in range(self.proxy.rowCount()):
            found = self.model.item(self.proxy.mapToSource(self.proxy.index(row, 0)).row(), 0).data(ROW_ROLE)
            if (found.schema, found.plan_id) == (schema, plan_id):
                self.table.selectRow(row)
                self.table.scrollTo(self.proxy.index(row, 0))
                return

    def _export_plans(self, export, suffix: str) -> None:
        """Exporterar de valda planerna med ``export(plan, sökväg)`` till en mapp, en fil per plan."""
        rows = self.selected_rows()
        folder = QFileDialog.getExistingDirectory(self, "Exportera planerna till mapp") if rows else ""
        if not folder:
            return
        done, problems = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for plan, path in transfer.unique_export_paths(Path(folder), [self._plan_storage(r) for r in rows], suffix):
                try:
                    export(plan, path)
                except (transfer.TransferError, storage.PostgisError) as exc:
                    problems.append(f"{path.name}: {exc}")
                else:
                    done.append(path.name)
        finally:
            QApplication.restoreOverrideCursor()
        self.notice.setText(f"Exporterade {len(done)} av {len(rows)} planer till {folder}." if done else "")
        self.error.setText("\n".join(problems))

    def _copy_plans(self) -> None:
        rows = self.selected_rows()
        dialog = CopyPlanDialog(self, self._connections, rows)
        if not rows or not dialog.exec():
            return
        values = dialog.values()
        connection = self._connections.get(values.connection)
        done, problems = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for row, plan_id in zip(rows, values.plan_ids):
                try:
                    transfer.copy_plan(self._plan_storage(row), values.connection, values.schema, plan_id, connection)
                except (transfer.TransferError, storage.PostgisError) as exc:
                    problems.append(f"{row.plan_id}: {exc}")
                else:
                    done.append(plan_id)
        finally:
            QApplication.restoreOverrideCursor()
        self.connection.setCurrentIndex(self.connection.findData(values.connection))
        self.reload()
        if done:
            self._select(values.schema, done[-1])
            self.notice.setText(f"Kopierade {len(done)} av {len(rows)} planer till schemat {values.schema}.")
        self.error.setText("\n".join(problems))

    def _confirm_delete(self, rows: list[PlanRow]) -> Optional[bool]:
        """Frågar om planerna ska tas bort. None om man ångrar sig, annars om en säkerhetskopia ska sparas först."""
        names = "\n".join(f"  {row.beteckning or row.plan_id}  ({row.schema}: {row.plan_id})" for row in rows[:12])
        more = f"\n  … och {len(rows) - 12} till" if len(rows) > 12 else ""
        box = QMessageBox(QMessageBox.Icon.Warning, "Ta bort plan",
                          f"Ta bort {'planen' if len(rows) == 1 else f'{len(rows)} planer'} ur databasen?\n\n{names}{more}\n\n"
                          "Det går inte att ångra.", parent=self)
        backup = QCheckBox("Spara en säkerhetskopia (GeoPackage) först")
        backup.setChecked(True)
        box.setCheckBox(backup)
        remove = box.addButton("Ta bort", QMessageBox.ButtonRole.DestructiveRole)
        remove.setIcon(icon("delete.svg"))
        cancel = box.addButton("Avbryt", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)  # Retur ska inte ta bort något
        box.exec()
        return backup.isChecked() if box.clickedButton() is remove else None

    def _delete_plans(self) -> None:
        rows = [row for row in self.selected_rows()]
        if not rows or any(row.locked or row.protected for row in rows):
            return
        backup = self._confirm_delete(rows)
        if backup is None:
            return
        folder = ""
        if backup:
            folder = QFileDialog.getExistingDirectory(self, "Spara säkerhetskopiorna i mapp")
            if not folder:
                return  # ingen mapp, ingen borttagning
        removed, problems = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for row in rows:
                plan = self._plan_storage(row)
                try:
                    if backup:  # en plan vars säkerhetskopia misslyckades tas inte bort
                        transfer.export_plan(plan, transfer.unique_export_paths(Path(folder), [plan])[0][1])
                    transfer.delete_plan(plan)
                except (transfer.TransferError, storage.PostgisError) as exc:
                    problems.append(f"{row.plan_id}: {exc}")
                else:
                    removed.append(row.plan_id)
        finally:
            QApplication.restoreOverrideCursor()
        self.reload()
        if removed:
            saved = f" Säkerhetskopiorna ligger i {folder}." if backup else ""
            self.notice.setText(f"Tog bort {len(removed)} av {len(rows)} planer.{saved}")
        self.error.setText("\n".join(problems))

    def _ask_protect(self, rows: list[PlanRow]) -> Optional[str]:
        """Frågar efter ett skäl till skyddet (valfritt). None om man ångrar sig."""
        names = ", ".join(row.beteckning or row.plan_id for row in rows[:6]) + (f" och {len(rows) - 6} till" if len(rows) > 6 else "")
        reason, accepted = QInputDialog.getText(
            self, "Skrivskydda", f"Skrivskydda {'planen' if len(rows) == 1 else f'{len(rows)} planer'} ({names})?\n\n"
            "Planerna kan sedan öppnas, exporteras och kopieras, men inte checkas ut, ändras eller tas bort förrän "
            "skyddet bryts.\n\nSkäl (valfritt, visas för den som försöker redigera planen):")
        return reason.strip() if accepted else None

    def _protect_plans(self) -> None:
        rows = [row for row in self.selected_rows() if not row.protected]
        if not rows:
            return
        reason = self._ask_protect(rows)
        if reason is None:
            return
        done, problems = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for row in rows:
                try:
                    checkout.protect(self._plan_storage(row), reason)
                except (checkout.CheckoutError, storage.PostgisError) as exc:
                    problems.append(f"{row.beteckning or row.plan_id}: {exc}")
                else:
                    done.append(row)
        finally:
            QApplication.restoreOverrideCursor()
        self.reload()
        if done:
            self.notice.setText(f"Skrivskyddade {len(done)} av {len(rows)} planer.")
        self.error.setText("\n".join(problems))

    def _confirm_unprotect(self, rows: list[PlanRow]) -> bool:
        who = "\n".join(f"  {row.beteckning or row.plan_id}: {row.protection.describe()}" for row in rows[:12])
        more = f"\n  … och {len(rows) - 12} till" if len(rows) > 12 else ""
        answer = QMessageBox.question(
            self, "Bryt skrivskydd", f"Bryta skrivskyddet på:\n\n{who}{more}\n\nPlanerna kan då checkas ut, ändras och tas "
            "bort igen. Gör det bara om planerna verkligen ska ändras.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _unprotect_plans(self) -> None:
        rows = [row for row in self.selected_rows() if row.protected]
        if not rows or not self._confirm_unprotect(rows):
            return
        done, problems = [], []
        for row in rows:
            try:
                checkout.unprotect(self._plan_storage(row))
            except (checkout.CheckoutError, storage.PostgisError) as exc:
                problems.append(f"{row.beteckning or row.plan_id}: {exc}")
            else:
                done.append(row)
        self.reload()
        if done:
            self.notice.setText(f"Bröt skrivskyddet på {len(done)} av {len(rows)} planer.")
        self.error.setText("\n".join(problems))

    def _confirm_break_locks(self, rows: list[PlanRow]) -> bool:
        who = "\n".join(f"  {row.beteckning or row.plan_id}: {row.lock.describe()}" for row in rows)
        answer = QMessageBox.question(
            self, "Bryt lås", f"Bryta utcheckningen av:\n\n{who}\n\nDen som har planen utcheckad kan då inte längre checka "
            "in sina ändringar. Gör det bara om utcheckningen är övergiven.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _break_locks(self) -> None:
        rows = [row for row in self.selected_rows() if row.locked]
        if not rows or not self._confirm_break_locks(rows):
            return
        broken, problems = [], []
        for row in rows:
            try:
                checkout.break_lock(self._plan_storage(row))
            except storage.PostgisError as exc:
                problems.append(f"{row.plan_id}: {exc}")
            else:
                broken.append(row.plan_id)
        self.reload()
        if broken:
            self.notice.setText(f"Bröt låset på {len(broken)} av {len(rows)} planer.")
        self.error.setText("\n".join(problems))

    def _accept_with(self, check_out: bool) -> None:
        rows = self.selected_rows()
        if not rows or (check_out and any(row.locked_by_other or row.protected for row in rows)):
            return
        self.checkout_requested = check_out
        self.accept()

    def _update_state(self, *_) -> None:
        total, shown = self.model.rowCount(), self.proxy.rowCount()
        rows = self.selected_rows()
        self.count.setText(f"Synliga: {shown} av {total}   ·   Valda: {len(rows)}")
        taken = [row for row in rows if row.locked_by_other]
        protected = [row for row in rows if row.protected]
        self.open_readonly.setEnabled(bool(rows))
        self.open_mosaic.setEnabled(bool(self.connection.count()))
        self.import_plan.setEnabled(bool(self.connection.count()))
        self.export_plans.setEnabled(bool(rows))
        self.copy_plans.setEnabled(bool(rows))
        self.delete_plans.setEnabled(bool(rows) and not any(row.locked or row.protected for row in rows))
        self.protect_plans.setEnabled(any(not row.protected for row in rows))
        self.unprotect_plans.setEnabled(bool(protected))
        self.break_locks.setEnabled(any(row.locked for row in rows))
        self.open_checkout.setEnabled(bool(rows) and not taken and not protected)
        if not rows:
            self.hint.setText("Välj en eller flera planer i listan (Ctrl eller Skift för flera).")
        elif protected:
            names = ", ".join(row.beteckning or row.plan_id for row in protected)
            self.hint.setText(
                f"Planen är skrivskyddad ({protected[0].protection.describe()}). Den kan öppnas skrivskyddad men inte "
                "checkas ut eller tas bort förrän skyddet bryts." if len(rows) == 1 else
                f"{len(protected)} av de valda planerna är skrivskyddade ({names}). De kan öppnas skrivskyddade men inte "
                "checkas ut eller tas bort. Bryt skyddet eller välj bort dem.")
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
