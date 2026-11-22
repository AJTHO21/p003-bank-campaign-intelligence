"""Validate and profile the unmodified UCI CSV using the Python standard library."""
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import mean, quantiles
from tempfile import NamedTemporaryFile

from source import ARCHIVE, CSV, INNER, MANIFEST, RAW, README, ROOT, ROWS, URL, digest

SCHEMA = {
    "age": int, "job": str, "marital": str, "education": str, "default": str,
    "housing": str, "loan": str, "contact": str, "month": str, "day_of_week": str,
    "duration": int, "campaign": int, "pdays": int, "previous": int,
    "poutcome": str, "emp.var.rate": float, "cons.price.idx": float,
    "cons.conf.idx": float, "euribor3m": float, "nr.employed": float, "y": str,
}


def verify_snapshot(directory):
    manifest = json.loads((directory / MANIFEST).read_text())
    expected = {ARCHIVE, INNER, CSV, README}
    if manifest["source_url"] != URL or set(manifest["files"]) != expected:
        raise ValueError("Unexpected manifest source URL or file list")
    for filename, metadata in manifest["files"].items():
        path = directory / filename
        if path.stat().st_size != metadata["bytes"] or digest(path) != metadata["sha256"]:
            raise ValueError(f"Source integrity check failed for {filename}")
    return manifest


def read_rows(path):
    rows = []
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, delimiter=";", strict=True)
        if next(reader, None) != list(SCHEMA):
            raise ValueError("Unexpected header, column order, or delimiter")
        for record in reader:
            if len(record) != len(SCHEMA):
                raise ValueError(f"Wrong field count on line {reader.line_num}")
            for (name, kind), value in zip(SCHEMA.items(), record):
                if kind is str or not value.strip():
                    continue
                try:
                    if kind is int and not re.fullmatch(r"[+-]?[0-9]+", value):
                        raise ValueError("Expected integer")
                    if not math.isfinite(kind(value)):
                        raise ValueError("Expected finite number")
                except (ValueError, OverflowError) as error:
                    raise ValueError(f"Invalid {name} on line {reader.line_num}") from error
            rows.append(tuple(record))
    if len(rows) != ROWS:
        raise ValueError(f"Expected {ROWS:,} records, found {len(rows):,}")
    if {row[-1] for row in rows} != {"yes", "no"}:
        raise ValueError("Expected target classes yes and no")
    return rows


def numeric_summary(values, sentinel=None):
    valid = sorted(value for value in values if value != sentinel)
    result = {"parsed_count": len(values),
              "raw_min": min(values, default=None), "raw_max": max(values, default=None),
              "sentinel": sentinel,
              "sentinel_count": len(values) - len(valid)}
    if not valid:
        return result
    q1, median, q3 = quantiles(valid, n=4, method="inclusive") if len(valid) > 1 else valid * 3
    spread = q3 - q1
    lower, upper = q1 - 1.5 * spread, q3 + 1.5 * spread
    result.update(min=valid[0], max=valid[-1], mean=mean(valid),
                  q1=q1, median=median, q3=q3, lower_fence=lower, upper_fence=upper,
                  below_fence=sum(value < lower for value in valid),
                  above_fence=sum(value > upper for value in valid))
    return result


def profile(rows, manifest):
    count = len(rows)
    frequencies = Counter(rows)
    duplicate_groups = [frequency for frequency in frequencies.values() if frequency > 1]
    columns = {}
    for (name, kind), values in zip(SCHEMA.items(), zip(*rows)):
        counts = Counter(values)
        details = {
            "type": kind.__name__,
            "empty": counts[""],
            "whitespace_only": sum(n for value, n in counts.items() if value and not value.strip()),
            "unknown_literal": counts["unknown"],
            "distinct_raw_values": len(counts),
        }
        if kind is str:
            details["distribution"] = {
                value: {"count": n, "percent_of_rows": 100 * n / count}
                for value, n in sorted(counts.items())
            }
        else:
            details["numeric"] = numeric_summary(
                [kind(value) for value in values if value.strip()], 999 if name == "pdays" else None
            )
        columns[name] = details
    return {
        "source": manifest,
        "validation": "SHA-256 and sizes, exact header, row/field counts, numeric types and target domain passed",
        "rows": count, "columns": len(SCHEMA), "inputs": len(SCHEMA) - 1,
        "rows_with_empty_or_whitespace": sum(any(not value.strip() for value in row) for row in rows),
        "rows_with_unknown_literal": sum("unknown" in row for row in rows),
        "exact_duplicate_groups": len(duplicate_groups),
        "rows_in_duplicate_groups": sum(duplicate_groups),
        "duplicate_rows_beyond_first": count - len(frequencies),
        "target": columns["y"]["distribution"],
        "duration_zero_by_target": dict(Counter(row[-1] for row in rows if row[10].strip() and int(row[10]) == 0)),
        "previous_zero_by_pdays_sentinel": dict(Counter(
            "sentinel" if int(row[12]) == 999 else "elapsed_days"
            for row in rows if row[13].strip() and int(row[13]) == 0 and row[12].strip()
        )),
        "fields": columns,
    }


def main():
    manifest = verify_snapshot(RAW)
    result = profile(read_rows(RAW / CSV), manifest)
    output = ROOT / "reports/profile.json"
    with NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.close()
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"{result['rows']:,} records × {result['columns']} columns")
    print(f"Target: {result['target']}")
    print(f"Additional exact duplicates: {result['duplicate_rows_beyond_first']}")
    print(f"Full audit: {output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, csv.Error) as error:
        raise SystemExit(f"Profiling failed: {error}")
