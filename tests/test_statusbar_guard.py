"""Spärren som håller QGIS statusrad på samma höjd när laddningsstapeln visas (se gui/statusbar_guard.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

if HAVE_QGIS:
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QProgressBar, QWidget
    from qgis_app import get_app
    from rita_detaljplan.gui.statusbar_guard import SETTLE_MS, StatusBarHeightGuard


def settle(ms=SETTLE_MS * 4):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class StatusBarGuardTests(unittest.TestCase):
    def window(self, progress_height):
        """Ett huvudfönster med en statusrad som QGIS: delarna ligger i en egen layout (en koordinatruta och en
        laddningsstapel som bara visas medan kartan ritas), och en dold del räknas inte med i höjden. Qts egen
        QStatusBar räknar däremot med dolda widgetar, så de läggs inte direkt i den."""
        get_app()
        window = QMainWindow()
        self.addCleanup(window.deleteLater)
        window.resize(400, 300)
        window.show()
        self.addCleanup(window.hide)
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel("koordinater")
        label.setFixedHeight(20)
        row.addWidget(label)
        progress = QProgressBar()
        progress.setFixedHeight(progress_height)
        row.addWidget(progress)
        window.statusBar().addPermanentWidget(container, 1)
        progress.hide()
        settle()
        return window, progress

    def test_a_progress_bar_that_makes_the_bar_taller_no_longer_makes_it_jump(self):
        window, progress = self.window(progress_height=34)
        bar = window.statusBar()
        idle = bar.height()
        guard = StatusBarHeightGuard.install(window)
        self.addCleanup(guard.release)
        progress.show()
        settle()
        busy = bar.height()
        self.assertGreater(busy, idle, "förutsättning: stapeln gör raden högre")
        progress.hide()
        settle()
        self.assertEqual(bar.height(), busy, "raden krymper inte när stapeln försvinner (det som startade om ritningen)")
        progress.show()
        settle()
        progress.hide()
        settle()
        self.assertEqual(bar.height(), busy, "och hoppar inte igen vid nästa ritning")

    def test_releasing_the_guard_restores_the_bar(self):
        window, progress = self.window(progress_height=34)
        bar = window.statusBar()
        idle, minimum = bar.height(), bar.minimumHeight()
        guard = StatusBarHeightGuard.install(window)
        progress.show()
        settle()
        progress.hide()
        settle()
        self.assertGreater(bar.minimumHeight(), minimum)
        guard.release()
        settle()
        self.assertEqual(bar.minimumHeight(), minimum)
        self.assertEqual(bar.height(), idle)
        progress.show()  # ingen spärr kvar: ingen låsning sker längre
        settle()
        progress.hide()
        settle()
        self.assertEqual(bar.height(), idle)

    def test_nothing_is_changed_when_the_progress_bar_never_makes_the_bar_taller(self):
        window, progress = self.window(progress_height=10)
        bar = window.statusBar()
        minimum = bar.minimumHeight()
        guard = StatusBarHeightGuard.install(window)
        self.addCleanup(guard.release)
        progress.show()
        settle()
        progress.hide()
        settle()
        self.assertEqual(bar.minimumHeight(), minimum, "ingen minimihöjd sätts i onödan")

    def test_a_window_without_a_status_bar_gives_no_guard(self):
        self.assertIsNone(StatusBarHeightGuard.install(None))
        self.assertIsNone(StatusBarHeightGuard.install(object()))


if __name__ == "__main__":
    unittest.main()
