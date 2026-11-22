"""Load and verify the pinned UCI snapshot in a single PostgreSQL transaction."""
import csv
import json
import subprocess
import tempfile
import time

from profile_data import SCHEMA, read_rows, verify_snapshot
from source import CSV, RAW, ROOT

SNAPSHOT_SHA = "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8"
SCHEMA_NAME = "p003_bank_campaign"
TABLE = f"{SCHEMA_NAME}.source_observation"


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def write_transaction(output, manifest, rows, *, offline_csv=None):
    """Generate the transaction. Offline testing uses server-side COPY of the same payload."""
    names = [quoted(name) for name in SCHEMA]
    columns = ", ".join(names)
    definitions = ", ".join(f"{name} text NOT NULL" for name in names)
    types = {int: "integer", float: "numeric", str: "text"}
    typed = ", ".join(f"{quoted(name)}::{types[kind]}" for name, kind in SCHEMA.items())
    actual = ", ".join(f"db.{name}::text" for name in names)
    expected = ", ".join(f"csv.{name}" for name in names)
    sha = sql_literal(SNAPSHOT_SHA)
    provenance = sql_literal(json.dumps(manifest))
    output.write(f"""BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL standard_conforming_strings = on;
SELECT pg_advisory_xact_lock(222, 3003);
""")
    output.write((ROOT / "sql/staging.sql").read_text())
    output.write(f"""
CREATE TEMP TABLE p003_csv (source_row integer PRIMARY KEY, {definitions}) ON COMMIT DROP;
COPY pg_temp.p003_csv FROM {"STDIN" if offline_csv is None else sql_literal(str(offline_csv))}
WITH (FORMAT csv, FORCE_NOT_NULL ({columns}));
""")
    if offline_csv is None:
        csv.writer(output, lineterminator="\n").writerows(
            (index, *row) for index, row in enumerate(rows, start=1)
        )
        output.write("\\.\n")
    output.write(f"""
DO $load$
DECLARE
    started_at timestamptz := clock_timestamp();
BEGIN
    IF NOT EXISTS (SELECT 1 FROM {SCHEMA_NAME}.source_snapshot WHERE source_sha256 = {sha}) THEN
        INSERT INTO {TABLE} (source_sha256, source_row, {columns})
        SELECT {sha}, source_row, {typed} FROM pg_temp.p003_csv ORDER BY source_row;
        INSERT INTO {SCHEMA_NAME}.source_snapshot (source_sha256, manifest, source_rows, load_elapsed)
        VALUES ({sha}, {provenance}::jsonb, {len(rows)}, clock_timestamp() - started_at);
    ELSIF EXISTS (SELECT 1 FROM {SCHEMA_NAME}.source_snapshot
                  WHERE source_sha256 = {sha}
                    AND manifest->'files'->'{CSV}' IS DISTINCT FROM
                        ({provenance}::jsonb)->'files'->'{CSV}') THEN
        RAISE EXCEPTION 'P003 snapshot metadata differs from the verified source';
    END IF;
END;
$load$;
""")
    output.write((ROOT / "sql/reporting.sql").read_text())
    output.write(f"""
DO $qa$
DECLARE
    started_at timestamptz := clock_timestamp();
    result jsonb;
    first_mismatch integer;
BEGIN
    SELECT min(coalesce(csv.source_row, db.source_row)) INTO first_mismatch
    FROM pg_temp.p003_csv csv
    FULL JOIN (SELECT * FROM {TABLE} WHERE source_sha256 = {sha}) db USING (source_row)
    WHERE csv.source_row IS NULL OR db.source_row IS NULL
       OR ROW({expected}) IS DISTINCT FROM ROW({actual});
    IF first_mismatch IS NOT NULL THEN
        RAISE EXCEPTION 'P003 CSV reconciliation failed at source row %', first_mismatch;
    END IF;

    SELECT jsonb_build_object(
        'rows', count(*), 'yes', count(*) FILTER (WHERE y = 'yes'),
        'no', count(*) FILTER (WHERE y = 'no'),
        'additional_exact_duplicates', count(*) - count(DISTINCT ROW({columns})),
        'pdays_999', count(*) FILTER (WHERE pdays = 999),
        'pdays_999_with_prior_contacts', count(*) FILTER (WHERE pdays = 999 AND previous > 0),
        'zero_duration', count(*) FILTER (WHERE duration = 0),
        'exact_ordinal_value_comparison', true
    ) INTO result
    FROM {TABLE} WHERE source_sha256 = {sha};

    IF result <> '{{"rows":41188,"yes":4640,"no":36548,"additional_exact_duplicates":12,
                    "pdays_999":39673,"pdays_999_with_prior_contacts":4110,"zero_duration":4,
                    "exact_ordinal_value_comparison":true}}'::jsonb THEN
        RAISE EXCEPTION 'P003 aggregate reconciliation failed: %', result;
    END IF;
    INSERT INTO {SCHEMA_NAME}.qa_run (source_sha256, qa_elapsed, result)
    VALUES ({sha}, clock_timestamp() - started_at, result);
END;
$qa$;

COMMIT;
SELECT q.checked_at, s.loaded_at, s.load_elapsed, q.qa_elapsed, q.result
FROM {SCHEMA_NAME}.qa_run q JOIN {SCHEMA_NAME}.source_snapshot s USING (source_sha256)
WHERE source_sha256 = {sha} ORDER BY q.run_id DESC LIMIT 1;
""")


def main():
    started = time.monotonic()
    manifest = verify_snapshot(RAW)
    if manifest["files"][CSV]["sha256"] != SNAPSHOT_SHA:
        raise ValueError("CSV hash differs from the approved Task 003 snapshot")
    rows = read_rows(RAW / CSV)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="") as sql:
        write_transaction(sql, manifest, rows)
        sql.seek(0)
        subprocess.run(
            ["psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", "-f", "-"],
            stdin=sql, check=True,
        )
    print(f"P003 ingestion and QA execution: {time.monotonic() - started:.3f} seconds")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"PostgreSQL ingestion failed: {error}")
