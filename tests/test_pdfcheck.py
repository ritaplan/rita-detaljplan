"""Kontrollen av en färdig plankarta som PDF (``core/pdfcheck``): strecksatser, bild eller vektor, PDF/A och georeferens."""
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_case import HAVE_QGIS  # noqa: E402

if HAVE_QGIS:
    from rita_detaljplan.core import pdfcheck


def make_pdf(content: bytes = b"0 0 m 10 10 l S", extra: bytes = b"", media: bytes = b"[0 0 1684 1191]") -> bytes:
    """En minimal PDF: en sida, en komprimerad innehållsström och det som skickas med i ``extra``."""
    body = zlib.compress(content)
    return (b"%PDF-1.7\n1 0 obj\n<< /Type /Page /MediaBox " + media + b" >>\nendobj\n"
            b"2 0 obj\n<< /Length " + str(len(body)).encode() + b" /Filter /FlateDecode >>\nstream\n" + body +
            b"\nendstream\nendobj\n" + extra + b"%%EOF\n")


@unittest.skipUnless(HAVE_QGIS, "QGIS Python behövs")
class PdfCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)

    def check(self, data: bytes):
        path = Path(self.tmp.name) / "karta.pdf"
        path.write_bytes(data)
        return pdfcheck.check_pdf(path)

    def levels(self, report):
        return [f.level for f in report.findings]

    def test_a_pdf_with_short_dash_arrays_is_fine(self):
        report = self.check(make_pdf(b"[49.99 33.33 33.33 33.33 ]0 d S [66.6 16.6 33.3 16.6 ]33.3 d S []0 d S"))
        self.assertTrue(report.ok)
        self.assertEqual((report.dash_arrays, report.longest_dash), (2, 4), "den tomma satsen (heldragen) räknas inte")
        self.assertNotIn("fel", self.levels(report))

    def test_a_long_dash_array_is_an_error_because_acrobat_refuses_it(self):
        long = b"[" + b" ".join([b"40.5 8.1"] * 8) + b" ]0 d S"
        report = self.check(make_pdf(long))
        self.assertFalse(report.ok)
        self.assertEqual(report.longest_dash, 16)
        self.assertIn("Streckargument", report.text())

    def test_a_dash_gap_near_zero_is_an_error(self):
        report = self.check(make_pdf(b"[33.2 16.6 33.2 0.000100000 ]0 d S"))
        self.assertFalse(report.ok)

    def test_exactly_six_numbers_are_accepted(self):
        report = self.check(make_pdf(b"[83.3 33.3 16.6 33.3 16.6 33.3 ]0 d S"))
        self.assertTrue(report.ok)

    def test_a_big_image_means_the_map_is_a_picture_and_not_vector(self):
        extra = b"3 0 obj\n<< /Type /XObject /Subtype /Image /Width 4000 /Height 3000 >>\nendobj\n"
        report = self.check(make_pdf(extra=extra))
        self.assertFalse(report.vector)
        self.assertIn("varning", self.levels(report))
        self.assertIn("kartan är en bild", report.summary())

    def test_a_small_image_such_as_a_logo_does_not_make_the_map_a_picture(self):
        extra = b"3 0 obj\n<< /Type /XObject /Subtype /Image /Width 300 /Height 200 >>\nendobj\n"
        report = self.check(make_pdf(extra=extra))
        self.assertTrue(report.vector)
        self.assertEqual(report.images, 1)

    def test_the_size_in_millimetres_and_the_page_count_are_read(self):
        report = self.check(make_pdf())
        self.assertEqual(report.size_mm, (594, 420), "A2")
        self.assertEqual(report.pages, 1)
        self.assertIn("594 × 420 mm", report.summary())

    def test_a_georeferenced_pdf_is_noted(self):
        report = self.check(make_pdf(extra=b"4 0 obj\n<< /VP [ << /Measure << /Subtype /GEO >> >> ] >>\nendobj\n"))
        self.assertTrue(report.georeferenced)
        self.assertIn("georefererad", report.text())

    def test_transparency_is_noted_for_the_pdf_a_conversion(self):
        report = self.check(make_pdf(extra=b"5 0 obj\n<< /Type /ExtGState /ca 0.5 /CA 0.5 >>\nendobj\n"))
        self.assertIn("genomskinlighet", report.text())

    def test_a_pdf_that_is_not_pdf_a_says_what_to_do(self):
        report = self.check(make_pdf())
        self.assertIsNone(report.pdfa)
        self.assertIn("inte PDF/A", report.text())

    def test_a_pdf_that_claims_to_be_pdf_a_is_recognised(self):
        report = self.check(make_pdf(extra=b'<pdfaid:part>2</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>'))
        self.assertEqual(report.pdfa, "2B")


if __name__ == "__main__":
    unittest.main()
