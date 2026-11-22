"""Local checks for the Page 2 analytical bindings and exact Page 1 upgrade."""
import hashlib
import os
import re
import shutil
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import channel_page as channel
import executive_page as executive
import project as p
import sync

PAGES = Path(p.REPORT) / "definition/pages"
PAGE_ONE = PAGES / executive.PAGE
PAGE_TWO = PAGES / channel.PAGE
PRIOR_VISUAL = PAGE_ONE / "visuals" / executive.identity("prior-rate") / "visual.json"
EXTENSION = Path(p.REPORT) / "definition/reportExtensions.json"


def visual(label):
    return p.load(p.ROOT / PAGE_TWO / "visuals" / executive.identity(f"channel-performance-{label}") / "visual.json")


def projections(doc, role):
    return [row["field"] for row in doc["visual"]["query"]["queryState"][role]["projections"]]


def fixed_values(doc):
    return {item["field"]["Column"]["Property"]: [
        row[0]["Literal"]["Value"] for row in item["filter"]["Where"][0]["Condition"]["In"]["Values"]
    ] for item in doc["filterConfig"]["filters"]}


class ChannelPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = p.validate_bundle(p.SOURCE_BUNDLE)
        cls.report_measures = {entity["name"]: {m["name"]: m for m in entity["measures"]}
                               for entity in p.load(p.ROOT / EXTENSION)["entities"]}

    def rows(self, table):
        name = f"{table}.csv"
        return p.csv_rows(p.SOURCE_BUNDLE / name, self.manifest["tables"][name])

    def test_schemas_identifiers_and_inventory(self):
        self.assertEqual(p.validate(), 29)
        pages = p.load(p.ROOT / PAGES / "pages.json")
        self.assertEqual(pages["pageOrder"], [executive.PAGE, channel.PAGE])
        self.assertEqual(pages["activePageName"], executive.PAGE)
        self.assertEqual(p.load(p.ROOT / PAGE_TWO / "page.json")["displayName"], channel.TITLE)
        files = p.definition_files(self.manifest)
        self.assertEqual(len(files), 45)
        self.assertTrue(all((p.ROOT / relative).stat().st_size > 0 for relative in files))
        self.assertEqual(len(self.manifest["tables"]), 12)
        self.assertEqual(sum(spec["rows"] for spec in self.manifest["tables"].values()), 383)
        p.validate_bundle(p.ROOT / p.DATA)

    def test_only_previous_outcome_bar_color_changed_on_page_one(self):
        original = next(doc for doc in executive.visuals(prior_color=executive.TEAL)
                        if doc["name"] == PRIOR_VISUAL.parent.name)
        self.assertEqual(hashlib.sha256(p.dump(original).encode()).hexdigest(),
                         "2a88725f94bd4973a81bbff42a0c737f1e145f2645cfbe33b7be412a4d69812e")
        original["visual"]["objects"]["dataPoint"][0]["properties"]["defaultColor"] = executive.color("#D5A34A")
        self.assertEqual((p.ROOT / PRIOR_VISUAL).read_bytes(), p.dump(original).encode())
        page = p.ROOT / PAGE_ONE
        inventory = b"".join(f"{path.relative_to(page)} {p.digest(path)}\n".encode()
                             for path in p.files_under(page) if path != p.ROOT / PRIOR_VISUAL)
        self.assertEqual(hashlib.sha256(inventory).hexdigest(),
                         "5889a775b99472bca3bcfe0bb0aa01ab491efe624d1fd532eeebd4e27f16ffa6")
        for entity in executive.report_extension()["entities"]:
            for measure in entity["measures"]:
                self.assertEqual(self.report_measures[entity["name"]][measure["name"]], measure)

    def test_gap_cards_bind_unique_pinned_rows_and_correct_units(self):
        baseline, = self.rows(executive.BASE)
        self.assertEqual((baseline["numerator"], baseline["denominator"]), (4640, 41188))
        self.assertEqual((baseline["rate"] * 100).quantize(D("0.0001")), D("11.2654"))
        comparisons = self.rows(channel.COMPARISON)
        for label, method, name, estimate, expected, support in (
            ("observed", "crude", executive.GAP, "observed", "9.51", None),
            ("prior", "prior_outcome", channel.PRIOR_GAP, "standardized", "6.43", 3),
            ("month", "contact_month", channel.MONTH_GAP, "standardized", "8.04", 9),
        ):
            with self.subTest(method=method):
                self.assertEqual(projections(visual(label), "Data"), [channel.extension(channel.COMPARISON, name)])
                measure = self.report_measures[channel.COMPARISON][name]
                filters = dict(re.findall(r'KEEPFILTERS\(\'comparison_estimates\'\[(\w+)\] = "([^"]+)"\)',
                                          measure["expression"]))
                self.assertEqual(filters, {"family": "channel", "method": method, "estimate_type": estimate})
                self.assertIn("SELECTEDVALUE('comparison_estimates'[gap_pp])", measure["expression"])
                self.assertEqual(measure["formatString"], channel.GAP_FORMAT)
                row, = [r for r in comparisons if all(r[k] == v for k, v in filters.items())]
                self.assertEqual(row["included_strata"], support)
                self.assertEqual(p.rounded(row["gap_pp"]), D(expected))
                self.assertLess(abs(row["gap_pp"] - (row["a_rate"] - row["b_rate"]) * 100), D("1e-15"))
                if support:
                    self.assertEqual(row["weighted_denominator"], row["a_n"] + row["b_n"])
                    self.assertEqual(row["weighted_denominator"], 41188 if support == 3 else 41006)

    def test_observed_charts_respect_grains_counts_and_support(self):
        observed = visual("rates")
        self.assertEqual(fixed_values(observed), {"dimension": ["'contact'"]})
        self.assertEqual(projections(observed, "Y"),
                         [executive.field(executive.SEGMENTS, "observed_segments observed rate", measure=True)])
        source = {r["level"]: r for r in self.rows(executive.SEGMENTS) if r["dimension"] == "contact"}
        self.assertEqual({k: (r["numerator"], r["denominator"], p.rounded(r["rate"] * 100))
                          for k, r in source.items()},
                         {"cellular": (3853, 26144, D("14.74")), "telephone": (787, 15044, D("5.23"))})

        prior = visual("outcomes")
        self.assertEqual(fixed_values(prior), {"dimension": ["'contact'"], "stratum_type": ["'prior_outcome'"]})
        self.assertEqual(projections(prior, "Series"), [executive.field(channel.CROSS, "level")])
        cells = [r for r in self.rows(channel.CROSS)
                 if (r["dimension"], r["stratum_type"]) == ("contact", "prior_outcome")]
        self.assertEqual({(r["level"], r["stratum"]) for r in cells},
                         {(k, outcome) for k in source for outcome in ("success", "failure", "nonexistent")})
        for k, row in source.items():
            self.assertEqual(sum(r["denominator"] for r in cells if r["level"] == k), row["denominator"])

        monthly = visual("months")
        self.assertEqual(fixed_values(monthly),
                         {"family": ["'channel'"], "method": ["'contact_month'"], "included": ["true"]})
        self.assertEqual(projections(monthly, "Category"), [executive.field(channel.WEIGHTS, "calendar_month_label")])
        weights = [r for r in self.rows(channel.WEIGHTS)
                   if (r["family"], r["method"]) == ("channel", "contact_month")]
        self.assertIn("chronological order", p.dump(visual("months")))
        self.assertIn("hover for both sample sizes", p.dump(visual("months")))
        included = [r for r in weights if r["included"]]
        self.assertEqual({r["stratum"] for r in included},
                         {"mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov"})
        self.assertEqual(sum(r["a_n"] + r["b_n"] for r in included), 41006)
        for role, bindings in (
            ("Y", ((channel.CELLULAR_RATE, "a_rate"), (channel.TELEPHONE_RATE, "b_rate"))),
            ("Tooltips", ((channel.CELLULAR_N, "a_n"), (channel.TELEPHONE_N, "b_n"))),
        ):
            self.assertEqual(projections(monthly, role),
                             [channel.extension(channel.WEIGHTS, name) for name, _ in bindings])
            for name, column in bindings:
                expression = self.report_measures[channel.WEIGHTS][name]["expression"]
                self.assertIn(f"SELECTEDVALUE('comparison_weights'[{column}])", expression)
                self.assertIn("KEEPFILTERS('comparison_weights'[included] = TRUE())", expression)
        december, = [r for r in weights if not r["included"]]
        self.assertEqual((december["stratum"], december["a_n"], december["b_n"],
                          december["a_n"] + december["b_n"], december["b_sparse"]),
                         ("dec", 149, 33, 182, True))
        explanation = [d for d in channel.visuals()
                       if d["name"] == executive.identity("channel-performance-interpretation")][0]
        text = str(explanation["visual"]["objects"]["general"][0]["properties"]["paragraphs"])
        self.assertIn("both channels: 149 cellular + 33 telephone = 182 observations", text)
        total_measure = self.report_measures[channel.WEIGHTS][channel.DECEMBER_N]["expression"]
        self.assertIn("SUM('comparison_weights'[a_n]) + SUM('comparison_weights'[b_n])", total_measure)
        self.assertIn("KEEPFILTERS('comparison_weights'[included] = FALSE())", total_measure)
        self.assertIn("KEEPFILTERS('comparison_weights'[stratum] = \"dec\")", total_measure)
        self.assertEqual(projections(visual("december"), "Data"),
                         [channel.extension(channel.WEIGHTS, channel.DECEMBER_N)])
        self.assertEqual([r["a_n"] + r["b_n"] for r in weights if not r["included"]], [182])
        self.assertIn("December excluded (both channels)", p.dump(visual("december")))

        frequency = visual("frequency")
        self.assertEqual(projections(frequency, "Y"),
                         [executive.field(channel.FREQUENCY, "campaign_frequency observed rate", measure=True)])
        shown = {int(text.removesuffix("L")) for text in fixed_values(frequency)["campaign"]}
        self.assertEqual(shown, set(range(1, 16)))
        rows = self.rows(channel.FREQUENCY)
        self.assertEqual(sum(r["denominator"] for r in rows), 41188)
        self.assertEqual(len(rows), 42)
        self.assertEqual(sum(r["denominator"] for r in rows if r["campaign"] in shown), 40833)

    def test_calendar_display_labels_and_sort_key_are_imported_without_dax_dependency(self):
        model = (p.ROOT / p.MODEL / "definition/tables/comparison_weights.tmdl").read_text(encoding="utf-8")
        self.assertEqual([line for line in model.splitlines() if line and not line.startswith("\t")],
                         ["table comparison_weights"])
        self.assertRegex(model, r"(?m)^\tcolumn calendar_month_label\n(?:\t{2}[^\n]+\n)*"
                                r"\t{2}sortByColumn: calendar_month_order$")
        self.assertRegex(model, r"(?m)^\tcolumn stratum\n(?:\t{2}[^\n]+\n)*"
                                  r"\t{2}sortByColumn: calendar_month_order$")
        self.assertEqual(re.findall(r"(?m)^\tcolumn (?:calendar_month_label|calendar_month_order)[^\n]*$", model),
                         ["\tcolumn calendar_month_label", "\tcolumn calendar_month_order"])
        self.assertRegex(model, r"(?m)^\tcolumn calendar_month_order\n"
                                r"\t{2}dataType: int64\n\t{2}lineageTag: [0-9a-f-]+\n"
                                r"\t{2}summarizeBy: none\n\t{2}sourceColumn: calendar_month_order\n"
                                r"\t{2}formatString: 0\n\t{2}isHidden$")
        self.assertIn('WithMonthOrder = Table.AddColumn(Verified, "calendar_month_order", each Record.FieldOrDefault(MonthOrder, [stratum], null), Int64.Type),', model)
        self.assertIn('MonthLabels = [mar = "Mar", apr = "Apr", may = "May", jun = "Jun", jul = "Jul", aug = "Aug", sep = "Sep", oct = "Oct", nov = "Nov"],', model)
        self.assertIn('WithMonthLabel = Table.AddColumn(WithMonthOrder, "calendar_month_label", each Record.FieldOrDefault(MonthLabels, [stratum], [stratum]), type text)', model)
        self.assertIn("WithMonthLabel\n", model)
        rows = self.rows(channel.WEIGHTS)
        month_order = dict(zip(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                "oct", "nov", "dec"), range(1, 13)))
        month_labels = dict(zip(("mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov"),
                                ("Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov")))
        by_stratum = {}
        for row in rows:
            stratum = row["stratum"]
            label = month_labels.get(stratum, stratum)
            order = month_order.get(stratum)
            by_stratum.setdefault(stratum, set()).add((label, order))
        self.assertTrue(all(len(values) == 1 for values in by_stratum.values()))
        self.assertEqual({stratum: next(iter(values))[0] for stratum, values in by_stratum.items()
                          if stratum in month_labels}, month_labels)
        self.assertEqual({stratum: next(iter(values))[1] for stratum, values in by_stratum.items()
                          if stratum in month_labels}, {month: month_order[month] for month in month_labels})
        self.assertEqual({stratum for stratum in by_stratum if stratum in month_labels},
                         set(month_labels))
        self.assertEqual({r["stratum"] for r in rows if r["family"] == "channel" and
                          r["method"] == "contact_month" and r["included"]}, set(month_labels))
        self.assertEqual(projections(visual("months"), "Category"),
                         [executive.field(channel.WEIGHTS, "calendar_month_label")])

    def test_exact_baseline_upgrade_is_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sync.managed_source(p.ROOT, root)
            shutil.rmtree(root / PAGE_TWO)
            metadata = PAGES / "pages.json"
            for relative, doc in (
                (PRIOR_VISUAL, next(d for d in executive.visuals(prior_color=executive.TEAL)
                                    if d["name"] == PRIOR_VISUAL.parent.name)),
                (EXTENSION, executive.report_extension()),
                (metadata, p.report_files()[metadata.as_posix()]),
            ):
                (root / relative).write_bytes(p.dump(doc).encode())
            old = (root / PRIOR_VISUAL).read_bytes()
            replace = os.replace

            def fail_before_color(src, dst):
                if dst == root / PRIOR_VISUAL:
                    raise OSError("interrupted before color replacement")
                replace(src, dst)

            with patch.object(os, "replace", side_effect=fail_before_color):
                with self.assertRaisesRegex(OSError, "interrupted before color replacement"):
                    p.build(root)
            self.assertEqual((root / PRIOR_VISUAL).read_bytes(), old)
            self.assertTrue(all(file.stat().st_size for file in p.files_under(root)))
            p.build(root)
            self.assertEqual(p.validate(root), 29)
            before = sync.inventory(root)
            self.assertEqual(before, {name: p.digest(p.ROOT / name) for name in before})
            with patch.object(p, "atomic_write", side_effect=AssertionError("unexpected rewrite")):
                p.build(root)
            self.assertEqual(sync.inventory(root), before)

    def test_unapproved_edits_are_refused_before_any_upgrade(self):
        for relative in (PRIOR_VISUAL, EXTENSION, PAGES / "pages.json", PAGE_TWO / "page.json"):
            with self.subTest(file=relative), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                sync.managed_source(p.ROOT, root)
                (root / relative).write_bytes((root / relative).read_bytes() + b"\n")
                before = sync.inventory(root)
                with self.assertRaisesRegex(ValueError, "Existing definition differs"):
                    p.build(root)
                self.assertEqual(sync.inventory(root), before)
