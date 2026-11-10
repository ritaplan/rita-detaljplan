"""Dialogruta för att kopiera planer i databasen till en annan plats (se ``core.transfer.copy_plan``)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from ..core import storage
from ..core.plan_overview import PlanRow
from .database_target import DatabaseTarget

ICONS = Path(__file__).resolve().parent.parent / "icons"


@dataclass(frozen=True)
class CopyValues:
    connection: str
    schema: str
    plan_ids: list  # en per vald plan, i samma ordning


class CopyPlanDialog(QDialog):
    """En vald plan kan få ett nytt plan-id. Flera valda planer behåller sina plan-id och måste därför kopieras till en annan
    databas eller ett annat schema."""

    def __init__(self, parent, connections: dict, rows: list[PlanRow]):
        super().__init__(parent)
        self._rows = rows
        self._plan_edited = False  # användaren har valt plan-id själv: föreslå inte över det
        self.setWindowTitle("Kopiera plan" if len(rows) == 1 else f"Kopiera {len(rows)} planer")
        self.setMinimumWidth(480)
        first = rows[0] if rows else None
        self.target = DatabaseTarget(connections, first.connection if first else None, first.schema if first else None)
        self.plan_id = QLineEdit()
        self.plan_id.setToolTip("Den nya planens identifierare inom schemat (måste vara unik där). Gemener a–z, siffror och "
                                "understreck.")
        self.info = QLabel()
        self.info.setWordWrap(True)

        form = QFormLayout()
        names = ", ".join(row.beteckning or row.plan_id for row in rows[:6]) + (" …" if len(rows) > 6 else "")
        form.addRow("Kopierar", QLabel(names))
        self.target.add_rows(form)
        if len(rows) == 1:
            form.addRow("Nytt plan-id", self.plan_id)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.setWindowIcon(QIcon(str(ICONS / "duplicate.svg")))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kopiera")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setIcon(QIcon(str(ICONS / "duplicate.svg")))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(self.buttons)

        self.target.connection.currentIndexChanged.connect(self._target_changed)
        self.target.schema.currentTextChanged.connect(self._target_changed)
        self.plan_id.textEdited.connect(self._plan_id_edited)
        self.plan_id.textChanged.connect(self._update)
        self._target_changed()

    def _same_place(self) -> bool:
        """Kopian hamnar i samma databas och schema som någon av de valda planerna."""
        return any((row.connection, row.schema) == (self.target.connection_name(), self.target.schema_name())
                   for row in self._rows)

    def _plan_id_edited(self, *_) -> None:
        self._plan_edited = True

    def _target_changed(self, *_) -> None:
        if len(self._rows) == 1 and not self._plan_edited:  # samma plats: ett annat id, annars samma id
            source = self._rows[0].plan_id
            self.plan_id.setText(f"{source}_kopia" if self._same_place() else source)
        self._update()

    def _problem(self) -> str:
        if not self.target.is_valid():
            return ""
        if len(self._rows) == 1:
            plan_id = self.plan_id.text().strip()
            if not storage.is_valid_plan_id(plan_id):
                return ""
            if self._same_place() and plan_id == self._rows[0].plan_id:
                return "Välj ett annat plan-id, ett annat schema eller en annan databas: planen finns redan där."
        elif self._same_place():
            return "Planerna behåller sina plan-id: välj ett annat schema eller en annan databas."
        return ""

    def is_valid(self) -> bool:
        if not self.target.is_valid() or self._problem():
            return False
        return len(self._rows) != 1 or storage.is_valid_plan_id(self.plan_id.text().strip())

    def _update(self, *_) -> None:
        problem = self._problem()
        self.info.setText(problem or "En kopia får planens uppgifter och alla objekt. Ett nytt schema skapas om det behövs.")
        self.info.setStyleSheet("color: #b3261e;" if problem else "")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.is_valid())

    def values(self) -> CopyValues:
        ids = [self.plan_id.text().strip()] if len(self._rows) == 1 else [row.plan_id for row in self._rows]
        return CopyValues(self.target.connection_name(), self.target.schema_name(), ids)
