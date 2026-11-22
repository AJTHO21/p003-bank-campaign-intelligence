"""Reconcile exploratory SQL JSON against the source CSV and Task 004B evidence."""
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

from load_postgresql import SNAPSHOT_SHA
from profile_data import SCHEMA, read_rows, verify_snapshot
from source import CSV, RAW, ROOT


def require(condition, label):
    if not condition:
        raise ValueError(f"Exploratory reconciliation failed: {label}")


def close(actual, expected, label):
    if expected is None:
        require(actual is None, label)
    else:
        exact = Decimal(expected.numerator) / Decimal(expected.denominator)
        require(actual is not None and abs(Decimal(actual) - exact) < Decimal("1e-14"), label)


def rate(counts):
    yes, total = counts
    return Fraction(100 * yes, total) if total else None


def verify(result):
    manifest = verify_snapshot(RAW)
    require(result["source_sha256"] == manifest["files"][CSV]["sha256"] == SNAPSHOT_SHA,
            "snapshot fingerprint")
    eligible = [dict(zip(SCHEMA, row)) for row in read_rows(RAW / CSV)]
    counts = defaultdict(Counter)
    strata = defaultdict(Counter)
    for row in eligible:
        contact, outcome, days = (row[field] for field in ("contact", "poutcome", "pdays"))
        prior = int(row["previous"]) > 0
        sentinel = days == "999"
        yes = row["y"] == "yes"
        counts["baseline"][(), yes] += 1
        if contact in ("cellular", "telephone"):
            counts["channels"][(contact,), yes] += 1
        counts["outcomes"][(outcome,), yes] += 1
        counts["history"][(prior, outcome, sentinel, prior and sentinel), yes] += 1
        if not sentinel:
            for key in ((outcome, int(days)), (outcome, None), (None, int(days)), (None, None)):
                counts["elapsed_days"][key, yes] += 1
        if outcome == "failure":
            campaign = int(row["campaign"])
            dimensions = {"month": row["month"], "frequency": str(campaign) if campaign <= 3 else "4+"}
            if contact in ("cellular", "telephone"):
                dimensions["channel"] = contact
            for dimension, level in dimensions.items():
                strata[dimension, level][sentinel, yes] += 1

    keys = {"baseline": (), "channels": ("contact",), "outcomes": ("poutcome",),
            "history": ("recorded_prior_contacts", "poutcome", "pdays_sentinel", "history_disagreement"),
            "elapsed_days": ("poutcome", "pdays")}
    for section, fields in keys.items():
        rows = [result[section]] if section == "baseline" else result[section]
        expected = counts[section]
        require(len(rows) == len({key for key, _ in expected}), f"{section} row count")
        seen = set()
        for row in rows:
            key = tuple(row[field] for field in fields)
            require(key not in seen, f"{section} duplicate stratum {key}")
            seen.add(key)
            n_yes, n_no = (expected[key, yes] for yes in (True, False))
            pair = n_yes, n_yes + n_no
            require(pair == (row["numerator"], row["denominator"]) and pair[1] > 0,
                    f"{section} counts {key}")
            close(row["rate_pct"], rate(pair), f"{section} rate {key}")

    actual_strata = indexed(result["strata"], ("dimension", "stratum"))
    require(actual_strata.keys() == strata.keys(), "complete stratum coverage")
    pairs = {}
    for key, counter in strata.items():
        elapsed, sentinel = (group_counts(counter, group) for group in (False, True))
        pairs[key] = elapsed, sentinel
        verify_stratum(actual_strata[key], elapsed, sentinel, key)
        close(actual_strata[key]["gap_pp"], rate(elapsed) - rate(sentinel), key)

    definitions = {"month_standardized": ("month", 1), "seven_month_sensitivity": ("month", 10),
                   "frequency_standardized": ("frequency", 1)}
    summaries = indexed(result["standardized"], ("analysis",))
    require(set(summaries) == {(name,) for name in definitions}, "summary coverage")
    all_weights = indexed(result["weights"], ("analysis", "stratum"))
    require(set(all_weights) == {(name, level) for name, (dim, _) in definitions.items()
                                for d, level in pairs if d == dim}, "weight-row coverage")
    for name, (dimension, minimum) in definitions.items():
        applicable = {level: groups for (dim, level), groups in pairs.items() if dim == dimension}
        included = {level: groups for level, groups in applicable.items()
                    if min(groups[0][1], groups[1][1]) >= minimum}
        total = sum(e[1] + s[1] for e, s in included.values())
        summary = summaries[name,]
        require(summary["included_strata"] == len(included), f"{name} included stratum count")
        standardized = [Fraction(0), Fraction(0)]
        for level, (elapsed, sentinel) in applicable.items():
            row = all_weights[name, level]
            verify_stratum(row, elapsed, sentinel, (name, level))
            used = level in included
            weight_n = elapsed[1] + sentinel[1] if used else 0
            require((row["minimum_per_group"], row["included"], row["weight_numerator"],
                     row["weight_denominator"]) == (minimum, used, weight_n, total),
                    f"{name} eligibility and weights for {level}")
            weight = Fraction(weight_n, total)
            close(row["weight"], weight, f"{name} weight for {level}")
            if used:
                standardized[0] += weight * rate(elapsed)
                standardized[1] += weight * rate(sentinel)
        for i, prefix in enumerate(("elapsed", "sentinel")):
            require((summary[prefix + "_yes"], summary[prefix + "_n"]) ==
                    tuple(sum(group[i][j] for group in included.values()) for j in (0, 1)),
                    f"{name} {prefix} totals")
            close(summary[prefix + "_pct"], standardized[i], f"{name} {prefix} rate")
        close(summary["gap_pp"], standardized[0] - standardized[1], f"{name} gap")

    channels = indexed(result["channels"], ("contact",))
    channel_pairs = [(channels[key,]["numerator"], channels[key,]["denominator"])
                     for key in ("cellular", "telephone")]
    close(result["channel_gap_pp"], rate(channel_pairs[0]) - rate(channel_pairs[1]), "channel gap")
    check_evidence(result)


def indexed(rows, fields):
    mapped = {tuple(row[field] for field in fields): row for row in rows}
    require(len(mapped) == len(rows), f"duplicate keys for {fields}")
    return mapped


def group_counts(counter, sentinel):
    return counter[sentinel, True], counter[sentinel, True] + counter[sentinel, False]


def verify_stratum(row, elapsed, sentinel, label):
    require((row["elapsed_yes"], row["elapsed_n"]) == elapsed, f"{label} elapsed counts")
    require((row["sentinel_yes"], row["sentinel_n"]) == sentinel, f"{label} sentinel counts")
    require(row["sparse"] == (min(elapsed[1], sentinel[1]) < 10), f"{label} sparse flag")
    close(row["elapsed_pct"], rate(elapsed), f"{label} elapsed rate")
    close(row["sentinel_pct"], rate(sentinel), f"{label} sentinel rate")


def check_evidence(result):
    evidence = json.loads((ROOT / "tests/fixtures/task004b-evidence.json").read_text())

    def rounded(value):
        return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    actual = {
        "baseline_pct": rounded(result["baseline"]["rate_pct"]),
        "channel_pct": {row["contact"]: rounded(row["rate_pct"]) for row in result["channels"]},
        "prior_outcome_pct": {row["poutcome"]: rounded(row["rate_pct"]) for row in result["outcomes"]},
        "prior_failure": {"sentinel" if row["pdays_sentinel"] else "non_sentinel":
                          [row["numerator"], row["denominator"]]
                          for row in result["history"] if row["poutcome"] == "failure"},
        "gap_pp": {row["analysis"]: rounded(row["gap_pp"]) for row in result["standardized"]},
    }
    for section, supplied in evidence.items():
        require(actual[section] == supplied,
                f"supplied {section}: SQL returned {actual[section]}, expected {supplied}")


if __name__ == "__main__":
    try:
        verify(json.loads(Path(sys.argv[1]).read_text(), parse_float=Decimal))
    except (IndexError, KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit(str(error))
    print("Exploratory SQL matches the source CSV and supplied Task 004B evidence.")
