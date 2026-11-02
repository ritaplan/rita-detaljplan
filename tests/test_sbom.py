import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_sbom  # noqa: E402
import build_zip  # noqa: E402


class SbomTest(unittest.TestCase):
    def test_the_code_only_depends_on_what_the_sbom_lists(self):
        self.assertLessEqual(build_sbom.third_party_imports(), build_sbom.KNOWN_THIRD_PARTY)

    def test_an_unlisted_package_stops_the_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "rita_detaljplan").mkdir()
            (root / "rita_detaljplan" / "mod.py").write_text("import requests\nimport json\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as stopped:
                build_sbom.check_dependencies(root)
            self.assertIn("requests", str(stopped.exception))

    def test_the_sbom_describes_the_plugin_its_data_and_its_platform(self):
        sbom = build_sbom.build_sbom()
        self.assertEqual((sbom["bomFormat"], sbom["specVersion"]), ("CycloneDX", "1.5"))
        app = sbom["metadata"]["component"]
        self.assertEqual(app["version"], build_zip.version())
        self.assertEqual(app["licenses"][0]["license"]["id"], "GPL-2.0-or-later")
        names = {component["name"] for component in sbom["components"]}
        self.assertTrue({"Planbestämmelsekatalogen", "QGIS", "PySide6"} <= names)
        listed = {ref for entry in sbom["dependencies"] for ref in entry["dependsOn"]}
        self.assertEqual(listed, {component["bom-ref"] for component in sbom["components"]})
        json.dumps(sbom)  # går att skriva som JSON

    def test_every_bundled_file_exists_and_has_a_checksum(self):
        for component in build_sbom.build_sbom()["components"]:
            if component["type"] == "data":
                self.assertEqual(len(component["hashes"][0]["content"]), 64)


if __name__ == "__main__":
    unittest.main()
