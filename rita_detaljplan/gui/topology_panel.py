"""Panelen "Topologikontroll": resultatet som en lista i tre avsnitt, på samma sätt som Kontrollera planen. Den ligger som
en panel i nederkant av QGIS (se ``PlanToolBar.check_topology``) och kan vara öppen medan man redigerar, så att ytorna syns
i kartan ovanför den.

  * **Rättas automatiskt:** ändringar på högst en centimeter, en rad per yta, ikryssade (se ``Change.tier``).
  * **Förslag att granska:** större ändringar, upp till toleransen, en rad per yta, inte ikryssade. Markerar man en rad visas
    ändringarna som en förhandsvisning i kartan (röd ring där brytpunkten ligger nu, grön där den hamnar).
  * **Kräver ditt beslut:** täckning och överlapp (planområde utan användning, användning utanför planområdet, överlapp,
    glapp, ogiltiga gränser) och ytor utan utbredning som kan tas bort. Inget av det rättas automatiskt.

Allt som gäller bestämmelser hör till Kontrollera planen."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                                 QPushButton, QVBoxLayout, QWidget)

from ..controller import PlanController
from ..core import topology, validation
from ..core.topology import Change
from ..core.validation import EMPTY_AREA_KIND, ERROR, WARNING, Issue
from .plan_switcher import build_plan_switcher
from .validation_dialog import COLORS, MARKS

CHANGE_KIND, FINDING_KIND, HEADER_KIND = "change", "finding", "header"
SECTION_TITLES = {topology.TIER_AUTO: "Rättas automatiskt (högst 1 cm, säkert)",
                  topology.TIER_REVIEW: "Förslag att granska (större än 1 cm)",
                  "beslut": "Kräver ditt beslut (görs inte automatiskt)"}
BUTTON_COLUMN_WIDTH = 250  # bildpunkter: knapparna ligger i en smal kolumn till höger så att listan får plats att läsas
STALE_TEXT = "Kontrollera igen (planen har ändrats)"


class TopologyPanel(QWidget):
    """``analyze(tolerance)`` ger förslagen, ``apply(changes)`` genomför de valda och returnerar (gjorda, hoppade över),
    ``show(item)`` visar en yta i kartan (item är en ``Change`` eller en ``Issue``). ``findings()`` (avvikelser som
    inte kan åtgärdas automatiskt, som ``Issue``), ``fill_use()`` (fyller det som saknar användning med en ny
    användningsyta, se ``controller.fill_use``), ``remove_empty()`` (tar bort ytor utan utbredning och returnerar
    antalet), ``describe(tabell, fid)`` (hur en yta pekas ut i listan) och ``preview(ändringar)`` (ritar förhandsvisningen av
    en rads ändringar i kartan, och rensar den med en tom lista) är valfria.

    Med ``controller`` får panelen en rad för att byta aktiv plan, och märker när planen ändrats efter kontrollen (knappen
    "Kontrollera igen" säger det): den läser inte om själv medan man ritar, så att raden man markerat inte försvinner."""

    def __init__(self, analyze: Callable[[float], list[Change]], apply: Callable[[list[Change]], tuple[int, int]],
                 show: Optional[Callable[[object], None]] = None, parent=None, *,
                 findings: Optional[Callable[[], list[Issue]]] = None, fill_use: Optional[Callable[[], object]] = None,
                 controller: Optional[PlanController] = None, remove_empty: Optional[Callable[[], int]] = None,
                 describe: Optional[Callable[[str, int], str]] = None,
                 preview: Optional[Callable[[list[Change]], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Topologikontroll")
        self.setMinimumHeight(140)
        self._analyze, self._apply, self._show = analyze, apply, show
        self._findings, self._fill_use = findings, fill_use
        self._remove_empty, self._describe, self._preview = remove_empty, describe, preview
        self._controller = controller
        self._busy = False  # något vi gör själva pågår: ändringarna det ger räknas inte som att planen ändrats
        self.changes: list[Change] = []
        self.groups: list[list[Change]] = []  # förslagen, en grupp per yta och nivå: en rad i listan
        self.findings: list[Issue] = []
        self._switcher: Optional[QWidget] = None

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        self.filters = {}
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(2)
        self.tolerance.setRange(0.01, 5.0)
        self.tolerance.setSingleStep(0.05)
        self.tolerance.setSuffix(" m")
        self.tolerance.setValue(topology.DEFAULT_TOLERANCE)
        self.tolerance.setToolTip("Största avstånd som räknas som ett glapp eller en avvikelse. Större avstånd ses "
                                  "som avsiktliga och lämnas orörda.")
        self.btn_again = QPushButton("Kontrollera igen")
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.btn_all = QPushButton("Markera alla")
        self.btn_none = QPushButton("Avmarkera alla")
        self.btn_show = QPushButton("Visa i kartan")
        self.btn_fill = QPushButton("Fyll återstoden med en användningsyta")
        self.btn_fill.setVisible(fill_use is not None)
        self.btn_remove = QPushButton("Ta bort tomma ytor")
        self.btn_remove.setToolTip("Tar bort ytor som saknar utbredning (area 0), till exempel spetsar längs en gräns som "
                                   "en ritning lämnat efter sig. De innehåller ingen information.")
        self.btn_remove.setVisible(remove_empty is not None)
        self.btn_apply = QPushButton("Gör valda ändringar")
        self.btn_apply.setDefault(True)

        # överst en rad: resultatet, toleransen och filtren; under den listan till vänster och knapparna i en kolumn
        # till höger, så att panelen kan vara låg och kartan ovanför den syns
        top_row = QHBoxLayout()
        top_row.addWidget(self.summary, 1)
        top_row.addWidget(QLabel("Tolerans:"))
        top_row.addWidget(self.tolerance)
        top_row.addWidget(self.btn_again)
        top_row.addSpacing(12)
        for severity, label in ((ERROR, "Fel"), (WARNING, "Varningar")):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._fill)
            self.filters[severity] = box
            top_row.addWidget(box)

        marks = QHBoxLayout()
        marks.addWidget(self.btn_all)
        marks.addWidget(self.btn_none)
        column = QVBoxLayout()
        column.addWidget(self.btn_apply)
        column.addLayout(marks)
        column.addWidget(self.btn_show)
        column.addWidget(self.btn_fill)
        column.addWidget(self.btn_remove)
        column.addStretch(1)
        self._column = QWidget()
        self._column.setFixedWidth(BUTTON_COLUMN_WIDTH)
        self._column.setLayout(column)
        column.setContentsMargins(0, 0, 0, 0)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addWidget(self._column)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.addLayout(top_row)
        self._layout.addLayout(body, 1)
        self._layout.addWidget(self.result)
        self.rebuild_switcher()

        self.btn_again.clicked.connect(self.reload)
        self.tolerance.editingFinished.connect(self.reload)
        self.btn_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.btn_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.btn_show.clicked.connect(self.show_selected)
        self.btn_fill.clicked.connect(self._fill_clicked)
        self.btn_remove.clicked.connect(self._remove_clicked)
        self.btn_apply.clicked.connect(self.apply_checked)
        self.list.itemChanged.connect(self._update_buttons)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.list.itemDoubleClicked.connect(lambda *_: self.show_selected())
        self.list.currentItemChanged.connect(lambda *_: self._preview_selected())
        if controller is not None:
            controller.changed.connect(self._mark_stale)
        self.reload()

    def rebuild_switcher(self) -> None:
        """Raden för att byta aktiv plan (bara när fler än en plan är laddad). Byggs om varje gång panelen öppnas, eftersom
        planer kan ha lagts till eller tagits bort sedan sist."""
        if self._switcher is not None:
            self._layout.removeWidget(self._switcher)
            self._switcher.deleteLater()
            self._switcher = None
        if self._controller is not None:
            self._switcher = build_plan_switcher(self._controller, self.reload, self)
            if self._switcher is not None:
                self._layout.insertWidget(0, self._switcher)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt-namn
        """En förhandsvisning hör till en öppen panel: den rensas när panelen stängs eller döljs."""
        self._clear_preview()
        super().hideEvent(event)

    def _mark_stale(self) -> None:
        """Planen har ändrats efter kontrollen (man ritar eller redigerar medan panelen är öppen)."""
        if not self._busy and self.isVisible():
            self.btn_again.setText(STALE_TEXT)
            self.btn_again.setStyleSheet("font-weight: bold; color: #8a5a00;")

    # -- listan ---------------------------------------------------------------------------
    def reload(self) -> None:
        self.btn_again.setText("Kontrollera igen")
        self.btn_again.setStyleSheet("")
        self.changes = self._analyze(self.tolerance.value())
        self.findings = self._findings() if self._findings is not None else []
        by_area: dict[tuple, list[Change]] = {}
        for change in self.changes:
            by_area.setdefault((change.tier, change.table, change.fid), []).append(change)
        self.groups = list(by_area.values())
        self._clear_preview()
        self._fill()

    def _issues(self) -> list[Issue]:
        """Allt som listan visar som avvikelser (förslagen räknas som varningar, ett per yta)."""
        return [*self.findings, *(Issue(WARNING, "", topology.summarize(group), group[0].table, group[0].fid)
                                  for group in self.groups)]

    def _name(self, table: str, fid: int) -> str:
        """Ytans läsbara beteckning i listan, till exempel "Kvartersmark, 3 803 m², nr 35"."""
        return (self._describe(table, fid) if self._describe is not None and fid is not None else "") or ""

    def _fill(self, *_) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        if self.filters[WARNING].isChecked():
            for tier in (topology.TIER_AUTO, topology.TIER_REVIEW):
                indexes = [i for i, group in enumerate(self.groups) if group[0].tier == tier]
                if indexes:
                    self._add_header(tier, SECTION_TITLES[tier], len(indexes))
                for index in indexes:
                    self._add_change(index, tier)
        deciding = [issue for severity in (ERROR, WARNING) for issue in self.findings
                    if issue.severity == severity and self.filters[severity].isChecked()]
        if deciding:
            self._add_header("beslut", SECTION_TITLES["beslut"], len(deciding))
            for issue in deciding:
                self._add_finding(issue)
        self.list.blockSignals(False)
        issues = self._issues()
        self.summary.setText(validation.summary(issues).replace("Inga avvikelser: planen klarar kontrollen.",
                                                                "Inga avvikelser: topologin stämmer."))
        self._update_buttons()

    def _add_header(self, key: str, title: str, count: int) -> None:
        item = QListWidgetItem(f"{title}: {count}")
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # en rubrik går inte att välja eller kryssa
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setBackground(QBrush(QColor(0, 0, 0, 18)))
        item.setData(Qt.ItemDataRole.UserRole, (HEADER_KIND, key))
        self.list.addItem(item)

    def _add_change(self, index: int, tier: str) -> None:
        group = self.groups[index]
        first = group[0]
        name = self._name(first.table, first.fid)
        item = QListWidgetItem(f"{MARKS[WARNING]}  {first.where}{f' ({name})' if name else ''}: "
                               f"{topology.summarize(group)}")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        # det säkra rättas utan vidare; det större ska granskas först och är därför inte ikryssat från början
        item.setCheckState(Qt.CheckState.Checked if tier == topology.TIER_AUTO else Qt.CheckState.Unchecked)
        item.setForeground(QBrush(COLORS[WARNING]))
        item.setData(Qt.ItemDataRole.UserRole, (CHANGE_KIND, index))
        item.setToolTip("\n".join(self._detail(c) for c in group))
        self.list.addItem(item)

    @staticmethod
    def _detail(change: Change) -> str:
        length = topology.length_text(change.distance)
        if change.new is None:
            return f"{change.title}: vid {change.old} ({length})"
        if change.old is None:
            return f"{change.title}: ny brytpunkt vid {change.new} ({length})"
        return f"{change.title}: från {change.old} till {change.new} ({length})"

    def _add_finding(self, issue: Issue) -> None:
        code = f"[{issue.code}] " if issue.code else ""
        name = self._name(issue.table, issue.fid) if issue.locatable and issue.table != "detaljplan" else ""
        item = QListWidgetItem(f"{MARKS[issue.severity]}  {issue.where}{f' ({name})' if name else ''}: {code}{issue.text}")
        item.setForeground(QBrush(COLORS[issue.severity]))
        item.setData(Qt.ItemDataRole.UserRole, (FINDING_KIND, issue))
        self.list.addItem(item)

    def rows(self) -> list[QListWidgetItem]:
        """Raderna i listan utan rubrikerna."""
        return [self.list.item(i) for i in range(self.list.count())
                if self.list.item(i).data(Qt.ItemDataRole.UserRole)[0] != HEADER_KIND]

    def checked(self) -> list[Change]:
        """De valda (ikryssade) förslagen."""
        chosen = []
        for item in self._change_items():
            if item.checkState() == Qt.CheckState.Checked:
                chosen.extend(self.groups[item.data(Qt.ItemDataRole.UserRole)[1]])
        return chosen

    def _change_items(self) -> list[QListWidgetItem]:
        return [item for item in self.rows() if item.data(Qt.ItemDataRole.UserRole)[0] == CHANGE_KIND]

    def _set_all(self, state) -> None:
        self.list.blockSignals(True)
        for item in self._change_items():
            item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_buttons()

    def _selected(self):
        item = self.list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return None if data is None or data[0] == HEADER_KIND else data

    def _update_buttons(self, *_) -> None:
        chosen = len(self.checked())
        self.btn_apply.setEnabled(chosen > 0)
        self.btn_apply.setText(f"Gör valda ändringar ({chosen})" if chosen else "Gör valda ändringar")
        has_changes = bool(self._change_items())
        self.btn_all.setEnabled(has_changes)
        self.btn_none.setEnabled(has_changes)
        selected = self._selected()
        locatable = selected is not None and (selected[0] == CHANGE_KIND or selected[1].locatable)
        self.btn_show.setEnabled(locatable and self._show is not None)
        self.btn_fill.setEnabled(any(issue.code == "DP-0002" and issue.severity == ERROR for issue in self.findings))
        self.btn_remove.setEnabled(any(issue.kind == EMPTY_AREA_KIND for issue in self.findings))

    # -- åtgärder ---------------------------------------------------------------------------
    def _preview_selected(self) -> None:
        """Ritar den markerade radens ändringar i kartan (och rensar när raden inte är ett förslag)."""
        selected = self._selected()
        if self._preview is not None:
            self._preview(list(self.groups[selected[1]]) if selected is not None and selected[0] == CHANGE_KIND else [])

    def _clear_preview(self) -> None:
        if self._preview is not None:
            self._preview([])

    def show_selected(self) -> None:
        selected = self._selected()
        if selected is None or self._show is None:
            return
        kind, value = selected
        if kind == CHANGE_KIND:
            self._show(self.groups[value][0])  # alla förslag i gruppen gäller samma yta
        elif value.locatable:
            self._show(value)

    def _fill_clicked(self) -> None:
        if self._fill_use is None:
            return
        self._busy = True
        try:
            result = self._fill_use()
        finally:
            self._busy = False
        self.result.setText(result.message)
        self.reload()

    def _remove_clicked(self) -> None:
        if self._remove_empty is None:
            return
        self._busy = True
        try:
            removed = self._remove_empty()
        finally:
            self._busy = False
        self.reload()
        self.result.setText(f"Tog bort {removed} {'tom yta' if removed == 1 else 'tomma ytor'}. "
                            "Spara genom att avsluta redigeringen.")

    def apply_checked(self) -> tuple[int, int]:
        """Genomför de ikryssade förslagen och kontrollerar om. Returnerar (gjorda, hoppade över)."""
        chosen = self.checked()
        if not chosen:
            return 0, 0
        self._busy = True
        try:
            done, skipped = self._apply(chosen)
        finally:
            self._busy = False
        self.reload()
        text = f"{done} ändringar gjordes."
        if skipped:
            text += f" {skipped} hoppades över eftersom de hade gett en ogiltig gräns."
        self.result.setText(text + " Spara genom att avsluta redigeringen.")
        return done, skipped
