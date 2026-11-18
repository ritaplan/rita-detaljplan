"""Matchning av en plan mot NGP när objektidentiteten inte finns där (ren logik, utan QGIS)."""
import unittest

from rita_detaljplan.core import ngp_client as ngp
from rita_detaljplan.core import ngp_match as m


def hit(identity, namn="", beteckning="", lagakraft="", status="laga kraft"):
    return ngp.PlanHit(identity, namn, beteckning, status, lagakraft)


class CollectionTests(unittest.TestCase):
    COLLECTIONS = {"1494": "Lidköpings kommun", "0486": "Eskilstuna kommun", "1480": "Göteborgs kommun"}

    def test_the_municipality_is_found_by_name_with_or_without_the_word_kommun(self):
        for name in ("Lidköping", "Lidköpings kommun", "  lidköping "):
            self.assertEqual(m.collection_for(name, self.COLLECTIONS), "1494", name)
        self.assertEqual(m.collection_for("Göteborg", self.COLLECTIONS), "1480")

    def test_a_municipality_code_is_used_as_it_is(self):
        self.assertEqual(m.collection_for("0486", self.COLLECTIONS), "0486")

    def test_an_unknown_or_missing_municipality_gives_nothing(self):
        self.assertIsNone(m.collection_for("Atlantis", self.COLLECTIONS))
        self.assertIsNone(m.collection_for("", self.COLLECTIONS))


class MatchTests(unittest.TestCase):
    A, B, C = ("aaaaaaaa-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002",
               "cccccccc-0000-4000-8000-000000000003")

    def test_designation_and_date_are_enough_even_with_a_different_name(self):
        found, why = m.match_plan("Kv Norr", "1494-P95/12", "2026-06-01",
                                  [hit(self.A, "Helt annat", "1494-p95/12", "2026-06-01")])
        self.assertEqual(found.objektidentitet, self.A)
        self.assertIn("samma beteckning", why)
        self.assertIn("samma datum", why)

    def test_the_date_and_a_similar_name_match_when_the_designation_differs(self):
        found, why = m.match_plan("Detaljplan för kvarteret Norr", "gammal beteckning", "2026-06-01",
                                  [hit(self.A, "Detaljplan för kvarteret Norr", "ny beteckning", "2026-06-01")])
        self.assertEqual(found.objektidentitet, self.A)
        self.assertIn("samma namn", why)

    def test_a_fuzzy_name_counts_when_something_else_also_matches(self):
        found, _why = m.match_plan("Detaljplan för Kv. Norr", "", "2026-06-01",
                                   [hit(self.A, "Detaljplan för kv Norra", "", "2026-06-01")])
        self.assertEqual(found.objektidentitet, self.A)

    def test_the_date_alone_or_the_designation_alone_is_not_enough(self):
        self.assertIsNone(m.match_plan("X", "1-1", "2026-06-01", [hit(self.A, "Annat", "9-9", "2026-06-01")])[0])
        self.assertIsNone(m.match_plan("X", "1-1", "2026-06-01", [hit(self.A, "Annat", "1-1", "1999-01-01")])[0])

    def test_the_name_alone_is_not_enough(self):
        self.assertIsNone(m.match_plan("Kv Norr", "1-1", "2026-06-01", [hit(self.A, "Kv Norr", "2-2", "1999-01-01")])[0])

    def test_equally_good_candidates_are_not_guessed_between(self):
        candidates = [hit(self.A, "Kv Norr", "1-23", "2026-06-01"), hit(self.B, "Kv Norr", "1-23", "2026-06-01")]
        self.assertEqual(m.match_plan("Kv Norr", "1-23", "2026-06-01", candidates), (None, ""))

    def test_the_best_candidate_wins_over_a_worse_one(self):
        candidates = [hit(self.A, "Kv Söder", "1-23", "2026-06-01"), hit(self.B, "Kv Norr", "1-23", "2026-06-01")]
        found, _why = m.match_plan("Kv Norr", "1-23", "2026-06-01", candidates)
        self.assertEqual(found.objektidentitet, self.B)

    def test_empty_local_data_matches_nothing(self):
        self.assertIsNone(m.match_plan("", "", "", [hit(self.A, "Kv Norr", "1-23", "2026-06-01")])[0])


if __name__ == "__main__":
    unittest.main()
