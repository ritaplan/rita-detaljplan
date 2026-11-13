"""Dialogen "Topologikontroll": resultatet som en lista på samma sätt som Kontrollera planen. Föreslagna ändringar av
brytpunkter och små glapp (ikryssade, görs automatiskt) står en rad per yta, bland avvikelserna om täckning och överlapp
(planområde utan användning, användning utanför planområdet, överlapp, glapp, ogiltiga gränser) och ytor utan utbredning
som kan tas bort. Allt som gäller bestämmelser hör till Kontrollera planen."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                                 QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from ..controller import PlanController
from ..core import topology, validation
from ..core.topology import Change
from ..core.validation import EMPTY_AREA_KIND, ERROR, WARNING, Issue
from .plan_switcher import build_plan_switcher
from .validation_dialog import COLORS, MARKS

CHANGE_KIND, FINDING_KIND = "change", "finding"
BETA_TEXT = ("<b>Beta:</b> Topologikontrollen är en utvecklingsversion och har ännu inte full funktionalitet. Den kan missa "
             "avvikelser, och alla föreslagna ändringar går inte alltid att genomföra. Granska förslagen och spara en "
             "kopia av planen innan du gör ändringar.")


class TopologyDialog(QDialog):
    """``analyze(tolerance)`` ger förslagen, ``apply(changes)`` genomför de valda och returnerar (gjorda, hoppade över),
    ``show(item)`` visar en yta i kartan (item är en ``Change`` eller en ``Issue``). ``findings()`` (avvikelser som
    inte kan åtgärdas automatiskt, som ``Issue``), ``fill_use()`` (fyller det som saknar användning med en ny
    användningsyta, se ``controller.fill_use``), ``remove_empty()`` (tar bort ytor utan utbredning och returnerar
    antalet) och ``describe(tabell, fid)`` (hur en yta pekas ut i listan) är valfria."""

    def __init__(self, analyze: Callable[[float], list[Change]], apply: Callable[[list[Change]], tuple[int, int]],
                 show: Optional[Callable[[object], None]] = None, parent=None, *,
                 findings: Optional[Callable[[], list[Issue]]] = None, fill_use: Optional[Callable[[], object]] = None,
                 controller: Optional[PlanController] = None, remove_empty: Optional[Callable[[], int]] = None,
                 describe: Optional[Callable[[str, int], str]] = None):
        super().__init__(parent)
        self.setWindowTitle("Topologikontroll")
        self.setMinimumSize(620, 460)
        self._analyze, self._apply, self._show = analyze, apply, show
        self._findings, self._fill_use = findings, fill_use
        self._remove_empty, self._describe = remove_empty, describe
        self.changes: list[Change] = []
        self.groups: list[list[Change]] = []  # förslagen, en grupp per yta: en rad i listan
        self.findings: list[Issue] = []
        self._switcher = build_plan_switcher(controller, self.reload, self) if controller is not None else None

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold;")
        self.beta_note = QLabel(BETA_TEXT)  # inforuta: funktionen är under utveckling
        self.beta_note.setWordWrap(True)
        self.beta_note.setStyleSheet("background: #fff4d6; color: #5a4300; border: 1px solid #e0c36a; "
                                     "border-radius: 4px; padding: 6px;")
        self.filters = {}
        filter_row = QHBoxLayout()
        for severity, label in ((ERROR, "Fel"), (WARNING, "Varningar")):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._fill)
            self.filters[severity] = box
            filter_row.addWidget(box)
        filter_row.addStretch(1)
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
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        close.rejected.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Tolerans:"))
        top_row.addWidget(self.tolerance)
        top_row.addWidget(self.btn_again)
        top_row.addSpacing(16)
        top_row.addLayout(filter_row)
        select_row = QHBoxLayout()
        for button in (self.btn_all, self.btn_none, self.btn_show, self.btn_fill, self.btn_remove):
            select_row.addWidget(button)
        select_row.addStretch(1)
        select_row.addWidget(self.btn_apply)
        select_row.addWidget(close)
        layout = QVBoxLayout(self)
        if self._switcher is not None:
            layout.addWidget(self._switcher)
        layout.addWidget(self.summary)
        layout.addWidget(self.beta_note)
        layout.addLayout(top_row)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.result)
        layout.addLayout(select_row)

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
        self.reload()

    # -- listan ---------------------------------------------------------------------------
    def reload(self) -> None:
        self.changes = self._analyze(self.tolerance.value())
        self.findings = self._findings() if self._findings is not None else []
        by_area: dict[tuple, list[Change]] = {}
        for change in self.changes:
            by_area.setdefault((change.table, change.fid), []).append(change)
        self.groups = list(by_area.values())
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
        for issue in self.findings:
            if issue.severity == ERROR and self.filters[ERROR].isChecked():
                self._add_finding(issue)
        if self.filters[WARNING].isChecked():
            for index, group in enumerate(self.groups):
                first = group[0]
                name = self._name(first.table, first.fid)
                item = QListWidgetItem(f"{MARKS[WARNING]}  {first.where}{f' ({name})' if name else ''}: "
                                       f"{topology.summarize(group)}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setForeground(QBrush(COLORS[WARNING]))
                item.setData(Qt.ItemDataRole.UserRole, (CHANGE_KIND, index))
                item.setToolTip("\n".join(
                    f"{c.title}: från {c.old} till {c.new} ({topology.length_text(c.distance)})" if c.old
                    else f"{c.title}: ny brytpunkt vid {c.new}" for c in group))
                self.list.addItem(item)
            for issue in self.findings:
                if issue.severity == WARNING:
                    self._add_finding(issue)
        self.list.blockSignals(False)
        issues = self._issues()
        self.summary.setText(validation.summary(issues).replace("Inga avvikelser: planen klarar kontrollen.",
                                                                "Inga avvikelser: topologin stämmer."))
        self._update_buttons()

    def _add_finding(self, issue: Issue) -> None:
        code = f"[{issue.code}] " if issue.code else ""
        name = self._name(issue.table, issue.fid) if issue.locatable and issue.table != "detaljplan" else ""
        item = QListWidgetItem(f"{MARKS[issue.severity]}  {issue.where}{f' ({name})' if name else ''}: {code}{issue.text}")
        item.setForeground(QBrush(COLORS[issue.severity]))
        item.setData(Qt.ItemDataRole.UserRole, (FINDING_KIND, issue))
        self.list.addItem(item)

    def checked(self) -> list[Change]:
        """De valda (ikryssade) förslagen."""
        chosen = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            kind, value = item.data(Qt.ItemDataRole.UserRole)
            if kind == CHANGE_KIND and item.checkState() == Qt.CheckState.Checked:
                chosen.extend(self.groups[value])
        return chosen

    def _change_items(self) -> list[QListWidgetItem]:
        return [self.list.item(i) for i in range(self.list.count())
                if self.list.item(i).data(Qt.ItemDataRole.UserRole)[0] == CHANGE_KIND]

    def _set_all(self, state) -> None:
        self.list.blockSignals(True)
        for item in self._change_items():
            item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_buttons()

    def _selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

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
        result = self._fill_use()
        self.result.setText(result.message)
        self.reload()

    def _remove_clicked(self) -> None:
        if self._remove_empty is None:
            return
        removed = self._remove_empty()
        self.reload()
        self.result.setText(f"Tog bort {removed} {'tom yta' if removed == 1 else 'tomma ytor'}. "
                            "Spara genom att avsluta redigeringen.")

    def apply_checked(self) -> tuple[int, int]:
        """Genomför de ikryssade förslagen och kontrollerar om. Returnerar (gjorda, hoppade över)."""
        chosen = self.checked()
        if not chosen:
            return 0, 0
        done, skipped = self._apply(chosen)
        self.reload()
        text = f"{done} ändringar gjordes."
        if skipped:
            text += f" {skipped} hoppades över eftersom de hade gett en ogiltig gräns."
        self.result.setText(text + " Spara genom att avsluta redigeringen.")
        return done, skipped
