"""Regression checks for the acquired UCI snapshot and ingestion assumptions."""
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from profile_data import CSV, RAW, ROOT, SCHEMA, profile, read_rows, verify_snapshot


class AnalyticalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = verify_snapshot(RAW)
        cls.rows = read_rows(RAW / CSV)
        cls.fields = dict(zip(SCHEMA, zip(*cls.rows)))

    def test_snapshot_and_profile(self):
        self.assertEqual(self.manifest["files"][CSV]["sha256"],
                         "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8")
        self.assertEqual((len(self.rows), len(SCHEMA)), (41188, 21))
        saved = json.loads((ROOT / "reports/profile.json").read_text())
        self.assertEqual(saved, profile(self.rows, self.manifest))

    def test_outcome_and_duplicate_denominators(self):
        self.assertEqual(Counter(self.fields["y"]), {"yes": 4640, "no": 36548})
        counts = Counter(self.rows)
        self.assertEqual(Counter(counts.values()), {1: 41164, 2: 12})
        self.assertEqual(Counter(row[-1] for row in counts if counts[row] > 1),
                         {"yes": 1, "no": 11})

    def test_blank_and_unknown_handling(self):
        self.assertTrue(all(value.strip() for row in self.rows for value in row))
        self.assertEqual(sum("unknown" in row for row in self.rows), 10700)
        self.assertEqual({name: values.count("unknown") for name, values in self.fields.items()
                          if "unknown" in values},
                         {"job": 330, "marital": 80, "education": 1731,
                          "default": 8597, "housing": 990, "loan": 990})

    def test_semantic_numeric_checks(self):
        minimums = {"age": 1, "duration": 0, "campaign": 1, "pdays": 0, "previous": 0}
        for field, minimum in minimums.items():
            with self.subTest(field=field):
                self.assertGreaterEqual(min(map(int, self.fields[field])), minimum)
        for field in ("cons.price.idx", "nr.employed"):
            with self.subTest(field=field):
                self.assertGreater(min(map(float, self.fields[field])), 0)

    def test_prior_history_disagreement_is_preserved(self):
        history = zip(self.fields["pdays"], self.fields["previous"], self.fields["poutcome"])
        self.assertEqual(Counter((days == "999", contacts == "0", outcome)
                                 for days, contacts, outcome in history), {
            (True, True, "nonexistent"): 35563,
            (True, False, "failure"): 4110,
            (False, False, "failure"): 142,
            (False, False, "success"): 1373,
        })

    def test_realized_contact_and_duration(self):
        self.assertEqual(set(self.fields["contact"]), {"cellular", "telephone"})
        self.assertEqual(Counter(outcome for duration, outcome
                                 in zip(self.fields["duration"], self.fields["y"])
                                 if duration == "0"), {"no": 4})
