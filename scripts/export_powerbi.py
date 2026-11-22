"""Export verified P003 aggregates as a private, deterministic Power BI bundle."""
import csv
import hashlib
import io
import json
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

from load_postgresql import SNAPSHOT_SHA
from profile_data import SCHEMA, read_rows
from source import CSV, RAW, ROOT
from verify_exploratory_findings import close, require, verify as verify_exploration
from verify_segmentation import verify as verify_segmentation

BEGIN = "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;"
SQL_FILES = ("exploratory_findings.sql", "segmentation.sql", "reporting_export.sql")


@dataclass(frozen=True)
class Dataset:
    grain: tuple
    expected: int
    fields: dict
    rows: list


def read_sql():
    statements = []
    for name in SQL_FILES[:2]:
        query = (ROOT / "sql" / name).read_text().strip()
        if not (query.startswith(BEGIN) and query.endswith("COMMIT;")):
            raise ValueError(f"Unexpected transaction wrapper in {name}")
        statements.append(query[len(BEGIN):-len("COMMIT;")].strip())
    statements.append((ROOT / "sql" / SQL_FILES[-1]).read_text().strip())
    return "\n".join([BEGIN, *statements, "COMMIT;", ""])


def validate_frequency(rows):
    outcome = list(SCHEMA).index("y")
    contact_count = list(SCHEMA).index("campaign")
    source = read_rows(RAW / CSV)
    eligible = [(int(r[contact_count]), r[outcome]) for r in source if int(r[contact_count]) >= 1]
    totals = Counter(count for count, _ in eligible)
    yes = Counter(count for count, target in eligible if target == "yes")
    require([row["campaign"] for row in rows] == sorted(totals), "exact contact-count levels")
    for row in rows:
        count = row["campaign"]
        require((row["numerator"], row["denominator"], row["frequency_numerator"],
                 row["frequency_denominator"]) ==
                (yes[count], totals[count], totals[count], len(eligible)), f"frequency counts {count}")
        close(row["subscription_rate"], Fraction(yes[count], totals[count]), f"frequency rate {count}")
        close(row["observation_share"], Fraction(totals[count], len(eligible)), f"frequency share {count}")


def rate_fraction(percent):
    with localcontext() as context:
        context.prec = 80
        return None if percent is None else Decimal(percent) / 100


def weighted_events(percent, denominator):
    with localcontext() as context:
        context.prec = 80
        return None if percent is None else rate_fraction(percent) * denominator


def observed(row):
    return dict(row, rate=rate_fraction(row["rate_pct"]))


def comparison_rows(exploration, segments):
    history = {row["pdays_sentinel"]: row for row in exploration["history"] if row["poutcome"] == "failure"}
    channels = {row["contact"]: row for row in exploration["channels"]}
    for family, groups, first, second in (
        ("prior_failure", history, False, True), ("channel", channels, "cellular", "telephone")
    ):
        a, b = groups[first], groups[second]
        yield {
            "family": family, "method": "crude", "estimate_type": "observed",
            "included_strata": None, "a_yes": a["numerator"], "a_n": a["denominator"],
            "b_yes": b["numerator"], "b_n": b["denominator"],
            "a_rate": rate_fraction(a["rate_pct"]), "b_rate": rate_fraction(b["rate_pct"]),
            "gap_pp": a["rate_pct"] - b["rate_pct"],
            "weighted_a_numerator": None, "weighted_b_numerator": None, "weighted_denominator": None,
        }
    for family, estimates, a, b, method in (
        ("prior_failure", exploration["standardized"], "elapsed", "sentinel", "analysis"),
        ("channel", segments["channel_adjusted"], "cellular", "telephone", "stratum_type"),
    ):
        for row in estimates:
            yield {
                "family": family, "method": row[method], "estimate_type": "standardized",
                "included_strata": row["included_strata"],
                "a_yes": row[a + "_yes"], "a_n": row[a + "_n"],
                "b_yes": row[b + "_yes"], "b_n": row[b + "_n"],
                "a_rate": rate_fraction(row[a + "_pct"]), "b_rate": rate_fraction(row[b + "_pct"]),
                "gap_pp": row["gap_pp"],
                "weighted_a_numerator": weighted_events(row[a + "_pct"], row[a + "_n"] + row[b + "_n"]),
                "weighted_b_numerator": weighted_events(row[b + "_pct"], row[a + "_n"] + row[b + "_n"]),
                "weighted_denominator": row[a + "_n"] + row[b + "_n"],
            }


def support_rows(exploration, segments):
    for row in exploration["weights"]:
        yield dict(row, family="prior_failure", method=row["analysis"],
                   a_yes=row["elapsed_yes"], a_n=row["elapsed_n"],
                   b_yes=row["sentinel_yes"], b_n=row["sentinel_n"],
                   a_rate=rate_fraction(row["elapsed_pct"]), b_rate=rate_fraction(row["sentinel_pct"]),
                   a_sparse=row["elapsed_n"] < 10, b_sparse=row["sentinel_n"] < 10)
    for row in segments["channel_weights"]:
        yield dict(row, family="channel", method=row["stratum_type"],
                   a_yes=row["cellular_yes"], a_n=row["cellular_n"],
                   b_yes=row["telephone_yes"], b_n=row["telephone_n"],
                   a_rate=rate_fraction(row["cellular_pct"]), b_rate=rate_fraction(row["telephone_pct"]),
                   a_sparse=not_supported(row["cellular_yes"], row["cellular_n"]),
                   b_sparse=not_supported(row["telephone_yes"], row["telephone_n"]),
                   minimum_per_group=50)


def not_supported(yes, n):
    return n < 50 or min(yes, n - yes) < 5


def build_datasets(exploration, segments, extra):
    verify_exploration(exploration)
    verify_segmentation(segments)
    validate_frequency(extra["frequency"])
    metric = {"numerator": "int64", "denominator": "int64", "rate": "decimal?"}
    cell = {**metric, "reference_pct": "decimal", "gap_pp": "decimal?",
            "wilson_low_pct": "decimal?", "wilson_high_pct": "decimal?", "sparse": "logical"}
    weights = {"weight_numerator": "int64", "weight_denominator": "int64", "weight": "decimal"}
    paired = {"a_yes": "int64", "a_n": "int64", "b_yes": "int64", "b_n": "int64",
              "a_rate": "decimal?", "b_rate": "decimal?"}
    marginal = [observed(r) for r in segments["cells"] if r["stratum_type"] == "overall"]
    cells = [observed(r) for r in segments["cells"] if r["stratum_type"] != "overall"]
    by_segment = {(r["dimension"], r["level"]): r for r in marginal}
    strata = [dict(r, a_yes=r["elapsed_yes"], a_n=r["elapsed_n"],
                   b_yes=r["sentinel_yes"], b_n=r["sentinel_n"],
                   a_rate=rate_fraction(r["elapsed_pct"]), b_rate=rate_fraction(r["sentinel_pct"]))
              for r in exploration["strata"]]
    # An adjusted rate is a weighted average. The counts remain raw support.
    adjusted_segments = [
        dict(r, adjusted_rate=rate_fraction(r["adjusted_pct"]),
             numerator=by_segment[r["dimension"], r["level"]]["numerator"],
             denominator=by_segment[r["dimension"], r["level"]]["denominator"],
             weighted_numerator=weighted_events(r["adjusted_pct"], segments["baseline"]["denominator"]),
             weighted_denominator=segments["baseline"]["denominator"] if r["adjusted_pct"] is not None else None)
        for r in segments["segment_adjusted"]
    ]
    return {
        "executive_baseline": Dataset((), 1, metric, [observed(exploration["baseline"])]),
        "observed_segments": Dataset(("dimension", "level"), 48,
            {"dimension": "text", "level": "text", **cell}, marginal),
        "observed_cross_tabs": Dataset(("dimension", "level", "stratum_type", "stratum"), 119,
            {"dimension": "text", "level": "text", "stratum_type": "text", "stratum": "text", **cell}, cells),
        "previous_outcome": Dataset(("poutcome",), 3, {"poutcome": "text", **metric},
                                    [observed(r) for r in exploration["outcomes"]]),
        "campaign_frequency": Dataset(("campaign",), 42,
            {"campaign": "int64", **metric, "frequency_numerator": "int64",
             "frequency_denominator": "int64", "observation_share": "decimal"},
            [dict(r, rate=r["subscription_rate"]) for r in extra["frequency"]]),
        "prior_contact_history": Dataset(("poutcome", "recorded_prior_contacts", "pdays_sentinel"), 4,
            {"poutcome": "text", "recorded_prior_contacts": "logical", "pdays_sentinel": "logical",
             "history_disagreement": "logical", **metric}, [observed(r) for r in exploration["history"]]),
        "non_sentinel_days": Dataset(("scope", "poutcome", "pdays"), 72,
            {"scope": "text", "poutcome": "text?", "pdays": "int64?", **metric},
            [dict(observed(r), scope="day_by_outcome" if r["poutcome"] and r["pdays"] is not None else
                  "outcome_total" if r["poutcome"] else "day_total" if r["pdays"] is not None else "overall")
             for r in exploration["elapsed_days"]]),
        "prior_failure_strata": Dataset(("dimension", "stratum"), 16,
            {"dimension": "text", "stratum": "text", **paired, "gap_pp": "decimal?", "sparse": "logical"}, strata),
        "comparison_estimates": Dataset(("family", "method"), 7,
            {"family": "text", "method": "text", "estimate_type": "text", **paired,
             "included_strata": "int64?", "gap_pp": "decimal", "weighted_a_numerator": "decimal?",
             "weighted_b_numerator": "decimal?", "weighted_denominator": "int64?"},
            list(comparison_rows(exploration, segments))),
        "comparison_weights": Dataset(("family", "method", "stratum"), 37,
            {"family": "text", "method": "text", "stratum": "text", "included": "logical",
             "minimum_per_group": "int64", "a_sparse": "logical", "b_sparse": "logical",
             **paired, **weights}, list(support_rows(exploration, segments))),
        "segment_estimates": Dataset(("dimension", "level"), 31,
            {"dimension": "text", "level": "text", "numerator": "int64", "denominator": "int64",
             "adjusted_rate": "decimal?", "gap_pp": "decimal?", "sparse_strata": "int64",
             "weighted_numerator": "decimal?", "weighted_denominator": "int64?"}, adjusted_segments),
        "segment_weights": Dataset(("prior_outcome",), 3,
            {"prior_outcome": "text", **weights}, segments["segment_weights"]),
    }


def encode(value, kind):
    if value is None and kind.endswith("?"):
        return ""
    kind = kind.removesuffix("?")
    if kind == "text" and isinstance(value, str) and value:
        return value
    if kind == "int64" and type(value) is int and -(2**63) <= value < 2**63:
        return str(value)
    if kind == "logical" and type(value) is bool:
        return str(value).lower()
    if kind == "decimal" and type(value) in (Decimal, int) and Decimal(value).is_finite():
        return format(value, "f")
    raise ValueError(f"Invalid {kind} field in export: {value!r}")


def bundle(datasets):
    files = {}
    inventory = {}
    for name, dataset in datasets.items():
        require(len(dataset.rows) == dataset.expected,
                f"{name} row count: got {len(dataset.rows)}, expected {dataset.expected}")
        fields = {"source_sha256": "text", **dataset.fields}
        grain = ("source_sha256", *dataset.grain)
        encoded = [dict(zip(fields, (encode(row[field], kind) for field, kind in fields.items())))
                   for row in (dict(row, source_sha256=SNAPSHOT_SHA) for row in dataset.rows)]
        keys = [tuple(row[field] for field in grain) for row in encoded]
        require(len(set(keys)) == len(keys), f"unique {name} grain")
        handle = io.StringIO(newline="")
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for _, row in sorted(zip(keys, encoded), key=lambda pair: pair[0]))
        filename = name + ".csv"
        files[filename] = handle.getvalue().encode("utf-8")
        inventory[filename] = {
            "rows": dataset.expected, "grain": grain,
            "columns": [{"name": field, "type": kind.removesuffix("?"), "nullable": kind.endswith("?")}
                        for field, kind in fields.items()],
            "sha256": hashlib.sha256(files[filename]).hexdigest(),
        }
    manifest = {
        "source_sha256": SNAPSHOT_SHA, "classification": "private pending publication review",
        "sql_sha256": {name: hashlib.sha256((ROOT / "sql" / name).read_bytes()).hexdigest()
                       for name in SQL_FILES},
        "encoding": "UTF-8", "delimiter": ",", "null": "", "tables": inventory,
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return files


def write_private_bundle(files, parent):
    identity = hashlib.sha256(files["manifest.json"]).hexdigest()
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        staging = Path(temp)
        for name, contents in files.items():
            path = staging / name
            path.write_bytes(contents)
            path.chmod(0o600)
        target = parent / identity
        try:
            staging.rename(target)
        except OSError:
            if not target.is_dir():
                raise
            require(not target.is_symlink() and target.stat().st_mode & 0o077 == 0,
                    "existing output directory must be private")
            require({path.name for path in target.iterdir()} == set(files), "existing bundle inventory")
            for name, payload in files.items():
                path = target / name
                require(not path.is_symlink() and path.stat().st_mode & 0o077 == 0 and
                        path.read_bytes() == payload, f"existing {name} must be private and byte-identical")
        return target


def main():
    started = time.monotonic()
    result = subprocess.run(["psql", "-X", "-w", "-Atq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                            input=read_sql(), capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    outputs = [json.loads(line, parse_float=Decimal) for line in result.stdout.splitlines() if line.strip()]
    queried = time.monotonic()
    files = bundle(build_datasets(*outputs))
    parent = ROOT / "data/reporting/task006"
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = write_private_bundle(files, parent)
    print(target)
    print(f"SQL {queried-started:.3f}s; reconciliation and export {time.monotonic()-queried:.3f}s")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Power BI export failed: {error}")
