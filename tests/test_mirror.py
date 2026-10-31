"""Kontrollen av speglade filer mellan Rita Detaljplan och Rita Översiktsplan (``tools/check_mirror.py``)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_mirror", ROOT / "tools" / "check_mirror.py")
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.a, self.b = Path(self.tmp.name) / "a", Path(self.tmp.name) / "b"
        for folder in (self.a, self.b):
            (folder / "core").mkdir(parents=True)

    def write(self, folder, text, name="core/archive.py"):
        (folder / name).write_text(text, encoding="utf-8")

    def test_the_plugins_own_names_are_not_a_difference(self):
        self.write(self.a, "from rita_detaljplan.core import x\nprint('Rita Detaljplan')\n")
        self.write(self.b, "from rita_oversiktsplan.core import x\nprint('Rita Översiktsplan')\n")
        self.assertEqual(mirror.difference(self.a / "core/archive.py", self.b / "core/archive.py"), [])

    def test_a_changed_line_is_a_difference(self):
        self.write(self.a, "a = 1\nb = 2\n")
        self.write(self.b, "a = 1\nb = 3\n")
        self.assertEqual(mirror.difference(self.a / "core/archive.py", self.b / "core/archive.py"), ["-b = 2", "+b = 3"])

    def test_a_new_difference_is_found_against_the_baseline(self):
        self.write(self.a, "a = 1\n")
        self.write(self.b, "a = 1\n")
        before = mirror.compare(self.a, self.b)["core/archive.py"]
        self.assertEqual(before["lines"], 0)
        baseline = {"core/archive.py": {"fingerprint": before["fingerprint"]}}
        self.write(self.a, "a = 2\n")  # bara den ena ändras
        result = mirror.compare(self.a, self.b)
        self.assertIn("core/archive.py", mirror.changed_since_baseline(result, baseline))
        self.write(self.b, "a = 2\n")  # den andra följer med: som sist
        result = mirror.compare(self.a, self.b)
        self.assertNotIn("core/archive.py", mirror.changed_since_baseline(result, baseline))

    def test_a_missing_file_is_reported_and_not_a_crash(self):
        result = mirror.compare(self.a, self.b)
        self.assertTrue(result["core/archive.py"]["missing"])


if __name__ == "__main__":
    unittest.main()
