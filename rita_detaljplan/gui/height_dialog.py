"""Bestämmelsens höjd (underkant och överkant i meter, RH2000): knappen Höjd… i tilldelningsdialogen (``AssignDialog``).

Ingen höjd: bestämmelsen gäller obegränsat i höjdled (som en vanlig yta). En höjd: den gäller inte under (underkant)
eller över (överkant) höjden. Båda: en kropp. Det som levereras till NGP följer av det, se ``core.vertical``."""
from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from ..controller import PlanController
from ..core import assignments, vertical

_MAX = 9000.0  # m: ryms med marginal av allt i Sverige, uppåt och nedåt


class _Height(QDoubleSpinBox):
    """Ett höjdfält i meter. Obegränsat (tomt) är inte ikryssat i rutan bredvid, och då är fältet avstängt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(-_MAX, _MAX)
        self.setDecimals(2)
        self.setSuffix(" m")
        self.setSingleStep(0.5)


class HeightDialog(QDialog):
    def __init__(self, row_fid: int, controller: PlanController, parent=None):
        super().__init__(parent)
        self.row_fid = row_fid
        self.controller = controller
        self.setWindowTitle("Höjd för bestämmelsen")
        self.setMinimumWidth(460)

        hint = QLabel("Höjd i meter i höjdsystemet RH2000. Lämna båda av för en bestämmelse som gäller på alla höjder. "
                      "Med bara överkant gäller den inte ovanför höjden, med bara underkant inte under. Med båda blir "
                      "den en kropp i leveransen.")
        hint.setWordWrap(True)
        hint.setEnabled(False)

        self.use_lower = QCheckBox("Underkant")
        self.lower = _Height()
        self.use_upper = QCheckBox("Överkant")
        self.upper = _Height()
        current = controller.bestammelse_height(row_fid)
        for check, field, key in ((self.use_lower, self.lower, "hojdUnderkant"), (self.use_upper, self.upper, "hojdOverkant")):
            value = current.get(key)
            check.setChecked(value is not None)
            field.setValue(value if value is not None else 0.0)
            field.setEnabled(value is not None)
            check.toggled.connect(field.setEnabled)
            check.toggled.connect(self._update)
        self.lower.valueChanged.connect(self._update)
        self.upper.valueChanged.connect(self._update)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.error = QLabel()
        self.error.setStyleSheet("color: #b00020;")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.use_upper, self.upper)
        form.addRow(self.use_lower, self.lower)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self._update()

    def extent(self) -> vertical.Extent:
        return vertical.Extent(self.lower.value() if self.use_lower.isChecked() else None,
                               self.upper.value() if self.use_upper.isChecked() else None)

    def _update(self, *_) -> None:
        extent = self.extent()
        self.summary.setText({
            vertical.FLAT: "Gäller på alla höjder.",
            vertical.HEIGHT: f"Gäller bara {extent.text()} (levereras som yta med höjdvärde och vertikal avgränsning "
                             f"{extent.limit}).",
            vertical.SOLID: f"Gäller bara mellan {extent.text()} (levereras som kropp, utan vertikal avgränsning).",
        }[extent.kind])
        self.error.setText("" if extent.consistent else "Underkanten måste ligga under överkanten.")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(extent.consistent)

    def accept(self) -> None:
        extent = self.extent()
        try:
            self.controller.set_bestammelse_height(self.row_fid, extent.lower, extent.upper)
        except assignments.AssignmentError as exc:
            self.error.setText(str(exc))
            return
        super().accept()
