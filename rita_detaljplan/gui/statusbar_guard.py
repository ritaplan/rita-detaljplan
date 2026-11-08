"""Håller QGIS statusrad på samma höjd när laddningsstapeln visas.

Är laddningsstapeln högre än resten av statusraden (t.ex. med en anpassad QGIS-profil där delar av raden är dolda) växlar
raden en pixel i höjd medan kartan ritas. Kartfönstret ändrar då storlek, utsnittet ändras något och en ny ritning startar,
om och om igen så länge ritningen är långsam nog att stapeln hinner visas. Spärren mäter radens höjd när stapeln visas och
låter den inte bli lägre än så. Den gör ingenting om stapeln aldrig gör raden högre, och ändrar bara minimihöjden (som
återställs när pluginet laddas ur).
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QEvent, QObject, QTimer
from qgis.PyQt.QtWidgets import QProgressBar, QStatusBar

SETTLE_MS = 50  # låt raden hinna läggas om efter att stapeln visats innan höjden mäts


class StatusBarHeightGuard(QObject):
    def __init__(self, status_bar: QStatusBar):
        super().__init__(status_bar)
        self._bar = status_bar
        self._original_minimum = status_bar.minimumHeight()
        self._watched: list[QProgressBar] = list(status_bar.findChildren(QProgressBar))
        self._idle_height = status_bar.height()  # höjden när ingen stapel visas, uppdateras när stapeln döljs
        for progress in self._watched:
            progress.installEventFilter(self)
        if any(progress.isVisible() for progress in self._watched):
            self._lock()

    @classmethod
    def install(cls, main_window) -> "StatusBarHeightGuard | None":
        """Spärr för huvudfönstrets statusrad, eller None om det inte finns någon (t.ex. i tester)."""
        bar = main_window.statusBar() if main_window is not None and hasattr(main_window, "statusBar") else None
        return cls(bar) if isinstance(bar, QStatusBar) else None

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - namnet krävs av Qt
        # Raden hinner ändra höjd innan Show-händelsen levereras, så vilohöjden mäts i stället när stapeln döljs.
        if event.type() == QEvent.Type.Show:
            QTimer.singleShot(SETTLE_MS, self._after_show)
        elif event.type() == QEvent.Type.Hide:
            QTimer.singleShot(SETTLE_MS, self._after_hide)
        return False  # lyssnar bara

    def _after_show(self) -> None:
        self._lock(grew_from=self._idle_height)

    def _after_hide(self) -> None:
        try:
            if not any(progress.isVisible() for progress in self._watched):
                self._idle_height = self._bar.height()
        except RuntimeError:  # statusraden är redan borttagen
            pass

    def _lock(self, grew_from: int | None = None) -> None:
        """Låser höjden om raden är högre än ``grew_from`` (eller, utan ``grew_from``, till dess nuvarande höjd)."""
        try:
            height = self._bar.height()
            if (grew_from is None or height > grew_from) and height > self._bar.minimumHeight():
                self._bar.setMinimumHeight(height)
        except RuntimeError:  # statusraden är redan borttagen
            pass

    def release(self) -> None:
        for progress in self._watched:
            try:
                progress.removeEventFilter(self)
            except RuntimeError:  # stapeln är redan borttagen
                pass
        self._watched.clear()
        try:
            self._bar.setMinimumHeight(self._original_minimum)
        except RuntimeError:  # statusraden är redan borttagen
            pass
