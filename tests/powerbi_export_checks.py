"""Checks for the CSV projection of independently reconciled SQL results."""
import csv
import hashlib
import io
import json
import tempfile
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from export_powerbi import bundle, write_private_bundle


def check_exports(test, datasets):
    files = bundle(datasets)
    test.assertEqual(bundle(datasets), files)
    manifest = json.loads(files["manifest.json"])
    tables = {}
    for name, info in manifest["tables"].items():
        reader = csv.DictReader(io.StringIO(files[name].decode()))
        test.assertEqual(reader.fieldnames, [column["name"] for column in info["columns"]])
        tables[name] = list(reader)
        test.assertEqual(len(tables[name]), info["rows"])
        test.assertEqual(hashlib.sha256(files[name]).hexdigest(), info["sha256"])
        keys = [tuple(row[field] for field in info["grain"]) for row in tables[name]]
        test.assertEqual(keys, sorted(set(keys)))
        test.assertNotIn("duration", reader.fieldnames)
        for row in tables[name]:
            for column in info["columns"]:
                value = row[column["name"]]
                kind = column["type"]
                if not value:
                    test.assertTrue(column["nullable"])
                elif kind == "int64":
                    int(value)
                elif kind == "decimal":
                    test.assertTrue(Decimal(value).is_finite())
                elif kind == "logical":
                    test.assertIn(value, ("true", "false"))

    baseline = tables["executive_baseline.csv"][0]
    test.assertEqual((baseline["numerator"], baseline["denominator"]), ("4640", "41188"))
    dimensions = defaultdict(lambda: [0, 0])
    for row in tables["observed_segments.csv"]:
        totals = dimensions[row["dimension"]]
        for i, field in enumerate(("numerator", "denominator")):
            totals[i] += int(row[field])
    test.assertEqual(len(dimensions), 8)
    test.assertTrue(all(pair == [4640, 41188] for pair in dimensions.values()))
    elapsed = tables["non_sentinel_days.csv"]
    test.assertTrue(all(row["pdays"] != "999" for row in elapsed))
    test.assertEqual(sum(int(row["denominator"]) for row in elapsed if row["scope"] == "day_total"), 1515)
    test.assertEqual(sum(int(row["denominator"]) for row in tables["campaign_frequency.csv"]), 41188)

    weights = defaultdict(list)
    for row in tables["comparison_weights.csv"]:
        weights[row["family"], row["method"]].append(row)
    expected_exclusions = {("prior_failure", "seven_month_sensitivity"): {"apr", "dec", "mar"},
                           ("channel", "contact_month"): {"dec"}}
    for row in tables["comparison_estimates.csv"]:
        key = (row["family"], row["method"])
        group = weights[key]
        for prefix in ("a", "b"):
            if row["estimate_type"] == "observed":
                ratio = Fraction(int(row[prefix + "_yes"]), int(row[prefix + "_n"]))
            else:
                included = [item for item in group if item["included"] == "true"]
                denominator = sum(int(item["weight_numerator"]) for item in included)
                test.assertEqual({item["stratum"] for item in group if item["included"] == "false"},
                                 expected_exclusions.get(key, set()))
                test.assertEqual(str(denominator), row["weighted_denominator"])
                test.assertEqual(sum(int(item[prefix + "_n"]) for item in included), int(row[prefix + "_n"]))
                equivalent = sum(Fraction(int(item["weight_numerator"]) * int(item[prefix + "_yes"]),
                                          int(item[prefix + "_n"])) for item in included)
                ratio = equivalent / denominator
                test.assertAlmostEqual(float(row["weighted_" + prefix + "_numerator"]), float(equivalent), places=8)
            test.assertAlmostEqual(float(row[prefix + "_rate"]), float(ratio), places=12)

    cross = {(row["dimension"], row["level"], row["stratum"]): row
             for row in tables["observed_cross_tabs.csv"] if row["stratum_type"] == "prior_outcome"}
    prior_weights = tables["segment_weights.csv"]
    for row in tables["segment_estimates.csv"]:
        cells = [(w, cross[row["dimension"], row["level"], w["prior_outcome"]]) for w in prior_weights]
        sparse = sum(c["sparse"] == "true" for _, c in cells)
        test.assertEqual(sparse, int(row["sparse_strata"]))
        if sparse:
            test.assertTrue(all(row[key] == "" for key in ("weighted_numerator", "weighted_denominator", "adjusted_rate")))
        else:
            equivalent = sum(Fraction(int(w["weight_numerator"]) * int(c["numerator"]),
                                      int(c["denominator"])) for w, c in cells)
            test.assertEqual(row["weighted_denominator"], "41188")
            test.assertAlmostEqual(float(row["weighted_numerator"]), float(equivalent), places=8)
            test.assertAlmostEqual(float(row["adjusted_rate"]), float(equivalent / 41188), places=12)

    with tempfile.TemporaryDirectory() as temp:
        first = write_private_bundle(files, Path(temp))
        test.assertEqual(first, write_private_bundle(files, Path(temp)))
        test.assertEqual(first.stat().st_mode & 0o777, 0o700)
        for name in files:
            test.assertEqual((first / name).stat().st_mode & 0o777, 0o600)
        (first / "executive_baseline.csv").write_text("changed")
        with test.assertRaisesRegex(ValueError, "byte-identical"):
            write_private_bundle(files, Path(temp))
