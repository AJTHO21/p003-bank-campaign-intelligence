"""Independently verify Task 005 SQL and render its detailed tables."""
import argparse
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from profile_data import SCHEMA, read_rows, verify_snapshot
from source import CSV, RAW
from verify_exploratory_findings import close, indexed, require

CROSS_SEGMENTS = {"job", "education", "age_band", "housing", "loan"}
MINIMUM = 50
MINIMUM_PER_OUTCOME = 5


def supported(counts):
    yes, total = counts
    return total >= MINIMUM and min(yes, total - yes) >= MINIMUM_PER_OUTCOME


def proportion(counts):
    return Fraction(*counts) if counts[1] else None


def verify(result):
    manifest = verify_snapshot(RAW)
    require(result["source_sha256"] == manifest["files"][CSV]["sha256"], "source hash")
    require(result["minimums"] == {"observations": MINIMUM, "per_outcome": MINIMUM_PER_OUTCOME},
            "support thresholds")
    counts = defaultdict(Counter)
    prior = defaultdict(Counter)
    levels = defaultdict(set)
    for raw in read_rows(RAW / CSV):
        row = dict(zip(SCHEMA, raw))
        outcome, month, yes = row["poutcome"], row["month"], row["y"] == "yes"
        prior[outcome][yes] += 1
        labels = ("Under 30", "30–39", "40–49", "50–59", "60+")
        age_label = labels[sum(int(row["age"]) >= cut for cut in (30, 40, 50, 60))]
        dimensions = {name: row[name] for name in
                      ("job", "education", "housing", "loan", "month", "day_of_week")}
        dimensions["age_band"] = age_label
        if row["contact"] in {"cellular", "telephone"}:
            dimensions["contact"] = row["contact"]
        for dimension, level in dimensions.items():
            levels[dimension].add(level)
            counts[dimension, level, "overall", None][yes] += 1
            if dimension in CROSS_SEGMENTS or dimension == "contact":
                counts[dimension, level, "prior_outcome", outcome][yes] += 1
            if dimension == "contact":
                counts[dimension, level, "contact_month", month][yes] += 1
    for dimension in CROSS_SEGMENTS | {"contact"}:
        for level in levels[dimension]:
            for outcome in prior:
                counts[dimension, level, "prior_outcome", outcome]
    for channel in levels["contact"]:
        for month in levels["month"]:
            counts["contact", channel, "contact_month", month]

    def as_pair(counter):
        return counter[True], sum(counter.values())

    pairs = {key: as_pair(counter) for key, counter in counts.items()}
    overall = as_pair(sum(prior.values(), Counter()))
    baseline = result["baseline"]
    require((baseline["numerator"], baseline["denominator"]) == overall, "overall counts")
    overall_rate = proportion(overall)
    close(baseline["subscription_rate"], overall_rate, "overall rate")
    prior_pairs = {key: as_pair(counter) for key, counter in prior.items()}
    cells = indexed(result["cells"], ("dimension", "level", "stratum_type", "stratum"))
    require(cells.keys() == pairs.keys(), "complete segmentation and cross-cell coverage")
    for key, counts_pair in pairs.items():
        cell = cells[key]
        _, _, kind, stratum = key
        reference = (overall_rate if kind == "overall" else proportion(prior_pairs[stratum])
                     if kind == "prior_outcome" else proportion(pairs["month", stratum, "overall", None]))
        observed = proportion(counts_pair)
        require((cell["numerator"], cell["denominator"]) == counts_pair, f"counts {key}")
        require(cell["sparse"] == (not supported(counts_pair)), f"support {key}")
        close(cell["reference_pct"], 100 * reference, f"reference {key}")
        close(cell["rate_pct"], None if observed is None else 100 * observed, f"rate {key}")
        close(cell["gap_pp"], None if observed is None else 100 * (observed - reference), f"gap {key}")
        check_interval(cell, observed, counts_pair[1], key)

    verify_channel(result, pairs, {"prior_outcome": prior.keys(), "contact_month": levels["month"]})
    weights = {key: Fraction(pair[1], overall[1]) for key, pair in prior_pairs.items()}
    weight_rows = indexed(result["segment_weights"], ("prior_outcome",))
    require(set(weight_rows) == {(key,) for key in weights}, "prior weight coverage")
    for key, weight in weights.items():
        row = weight_rows[key,]
        require((row["weight_numerator"], row["weight_denominator"]) ==
                (prior_pairs[key][1], overall[1]), f"prior weight counts {key}")
        close(row["weight"], weight, f"prior weight {key}")
    adjusted = indexed(result["segment_adjusted"], ("dimension", "level"))
    require(set(adjusted) == {(dim, level) for dim in CROSS_SEGMENTS for level in levels[dim]},
            "adjusted segment coverage")
    for (dim, level), row in adjusted.items():
        stratum_pairs = {key: pairs[dim, level, "prior_outcome", key] for key in weights}
        sparse = sum(not supported(pair) for pair in stratum_pairs.values())
        require(row["sparse_strata"] == sparse, f"adjusted segment support {dim} {level}")
        standardized = None if sparse else sum(weights[key] * proportion(pair)
                                                for key, pair in stratum_pairs.items())
        close(row["adjusted_pct"], None if sparse else 100 * standardized, (dim, level))
        close(row["gap_pp"], None if sparse else 100 * (standardized - overall_rate), (dim, level))


def check_interval(cell, observed, total, key):
    bounds = cell["wilson_low_pct"], cell["wilson_high_pct"]
    if observed is None:
        require(bounds == (None, None), f"empty interval {key}")
        return
    p = float(observed)
    z = 1.96
    divisor = 1 + z * z / total
    center = (p + z * z / (2 * total)) / divisor
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / divisor
    expected = max(0, center - radius) * 100, min(1, center + radius) * 100
    require(all(math.isclose(float(a), b, rel_tol=0, abs_tol=1e-10)
                for a, b in zip(bounds, expected)), f"Wilson interval {key}")


def verify_channel(result, pairs, strata):
    actual_weights = indexed(result["channel_weights"], ("stratum_type", "stratum"))
    actual_summary = indexed(result["channel_adjusted"], ("stratum_type",))
    require(set(actual_weights) == {(kind, level) for kind, levels in strata.items() for level in levels},
            "channel weight coverage")
    require(set(actual_summary) == {(kind,) for kind in strata}, "channel summary coverage")
    for kind, levels in strata.items():
        cells = {level: [pairs["contact", group, kind, level] for group in ("cellular", "telephone")]
                 for level in levels}
        included = {level: group for level, group in cells.items() if all(map(supported, group))}
        pooled = sum(sum(pair[1] for pair in group) for group in included.values())
        summary = actual_summary[kind,]
        require(summary["included_strata"] == len(included), f"channel stratum support {kind}")
        for level, group in cells.items():
            weight_count = sum(pair[1] for pair in group) if level in included else 0
            row = actual_weights[kind, level]
            require((row["included"], row["weight_numerator"], row["weight_denominator"]) ==
                    (level in included, weight_count, pooled), f"channel weight counts {kind} {level}")
            close(row["weight"], Fraction(weight_count, pooled), f"channel weight {kind} {level}")
            for prefix, pair in zip(("cellular", "telephone"), group):
                require((row[prefix + "_yes"], row[prefix + "_n"]) == pair,
                        f"channel cell counts {kind} {level} {prefix}")
                pct = proportion(pair)
                close(row[prefix + "_pct"], None if pct is None else 100 * pct,
                      f"channel cell rate {kind} {level} {prefix}")
            a, b = map(proportion, group)
            close(row["gap_pp"], None if a is None or b is None else 100 * (a - b),
                  f"channel stratum gap {kind} {level}")
        rates = []
        for index, prefix in enumerate(("cellular", "telephone")):
            totals = tuple(sum(group[index][j] for group in included.values()) for j in (0, 1))
            require((summary[prefix + "_yes"], summary[prefix + "_n"]) == totals,
                    f"channel summary counts {kind} {prefix}")
            standardized = sum(Fraction(sum(pair[1] for pair in group), pooled) *
                               proportion(group[index]) for group in included.values())
            rates.append(standardized)
            close(summary[prefix + "_pct"], 100 * standardized, f"channel adjusted {kind} {prefix}")
        close(summary["gap_pp"], 100 * (rates[0] - rates[1]), f"channel adjusted gap {kind}")


def render(result):
    print("# Segmentation and campaign performance tables\n")
    print("Rates and Wilson intervals are percentages. Gaps are percentage points. "
          "A dash indicates an unavailable estimate. See the [findings and methods](segmentation-findings.md).")
    for kind, title in (("overall", "Marginal results"), ("prior_outcome", "By previous outcome"),
                        ("contact_month", "Contact channel by month")):
        print(f"\n## {title}\n")
        print("| Dimension | Level | Stratum | Subscribed / observations | Rate | 95% Wilson | Reference | Gap | Sparse |")
        print("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        for row in result["cells"]:
            if row["stratum_type"] != kind:
                continue
            interval = ("—" if row["wilson_low_pct"] is None else
                        f'{fmt(row["wilson_low_pct"])} to {fmt(row["wilson_high_pct"])}')
            print(f'| {row["dimension"]} | {row["level"]} | {row["stratum"] or "All"} | '
                  f'{row["numerator"]:,} / {row["denominator"]:,} | {fmt(row["rate_pct"])} | '
                  f'{interval} | {fmt(row["reference_pct"])} | {fmt(row["gap_pp"], signed=True)} | '
                  f'{"Yes" if row["sparse"] else ""} |')
    print("\n## Channel comparison weights\n")
    print("| Stratified by | Stratum | Cellular n/N | Telephone n/N | Gap (pp) | Weight |")
    print("| --- | --- | ---: | ---: | ---: | ---: |")
    for row in result["channel_weights"]:
        weight = (f'{row["weight_numerator"]:,}/{row["weight_denominator"]:,}'
                  if row["included"] else "Excluded")
        print(f'| {row["stratum_type"]} | {row["stratum"]} | '
              f'{row["cellular_yes"]:,}/{row["cellular_n"]:,} | '
              f'{row["telephone_yes"]:,}/{row["telephone_n"]:,} | {fmt(row["gap_pp"], signed=True)} | {weight} |')
    print("\n## Prior-outcome weights for segments\n")
    for row in result["segment_weights"]:
        print(f'- {row["prior_outcome"]}: {row["weight_numerator"]:,}/{row["weight_denominator"]:,}.')
    print("\n## Prior-outcome-standardized segment results\n")
    print("| Dimension | Level | Adjusted rate (%) | Gap to baseline (pp) | Sparse outcome strata |")
    print("| --- | --- | ---: | ---: | ---: |")
    for row in result["segment_adjusted"]:
        print(f'| {row["dimension"]} | {row["level"]} | {fmt(row["adjusted_pct"])} | '
              f'{fmt(row["gap_pp"], signed=True)} | {row["sparse_strata"]} |')


def fmt(value, *, signed=False):
    return "—" if value is None else format(value, "+.2f" if signed else ".2f")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--tables", action="store_true", help="write reconciled Markdown to stdout")
    args = parser.parse_args()
    try:
        data = json.loads(args.result.read_text(), parse_float=Decimal)
        verify(data)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit(str(error))
    if args.tables:
        render(data)
    else:
        print("Task 005 SQL counts, support, rates, Wilson intervals and adjusted results reconcile.")
