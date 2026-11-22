"""Run the full transaction against a disposable PostgreSQL single-user cluster."""
import csv
import io
import json
from decimal import Decimal
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_powerbi import build_datasets, read_sql
from load_postgresql import write_transaction
from powerbi_export_checks import check_exports
from profile_data import read_rows, verify_snapshot
from source import CSV, RAW, ROOT
from verify_exploratory_findings import verify
from verify_segmentation import verify as verify_segmentation

PG_BIN = os.environ.get("P003_PG_BIN")


class PostgreSQLCopyTests(unittest.TestCase):
    def test_client_copy_payload(self):
        manifest = verify_snapshot(RAW)
        rows = read_rows(RAW / CSV)
        sql = io.StringIO()
        write_transaction(sql, manifest, rows)
        script = sql.getvalue()
        start = script.index("COPY pg_temp.p003_csv FROM STDIN")
        payload = script[start:].split("\n", 2)[2]
        data, end, remainder = payload.partition("\\.\n")
        self.assertEqual(end, "\\.\n")
        self.assertIn("COMMIT;", remainder)
        self.assertTrue(
            list(csv.reader(io.StringIO(data))) ==
            [[str(index), *row] for index, row in enumerate(rows, 1)],
        )


@unittest.skipUnless(PG_BIN, "Set P003_PG_BIN to run disposable PostgreSQL engine QA")
class PostgreSQLTests(unittest.TestCase):
    def run_sql(self, sql):
        result = subprocess.run(
            [str(Path(PG_BIN) / "postgres"), "--single", "-j", "-D", str(self.cluster), "postgres"],
            input=re.sub(r"^$", " ", sql.rstrip(), flags=re.MULTILINE) + "\n\n", text=True, capture_output=True, check=True,
        )
        return result.stdout + result.stderr

    def assert_sql_passes(self, sql, marker):
        result = self.run_sql(sql)
        self.assertNotRegex(result, r"(ERROR|FATAL|PANIC):")
        self.assertIn(f'"{marker}"', result)
        return result

    def test_load_reconciliation_repeat_and_rollback(self):
        manifest = verify_snapshot(RAW)
        rows = read_rows(RAW / CSV)
        with tempfile.TemporaryDirectory(prefix="p003-postgres-test-") as temp:
            self.cluster = Path(temp) / "db"
            payload = Path(temp) / "source.csv"
            with payload.open("w", newline="") as file:
                csv.writer(file).writerows((index, *row) for index, row in enumerate(rows, 1))
            subprocess.run([str(Path(PG_BIN) / "initdb"), "-D", str(self.cluster),
                            "-A", "trust", "--no-locale", "-E", "UTF8"],
                           capture_output=True, check=True)
            buffer = io.StringIO()
            write_transaction(buffer, manifest, rows, offline_csv=payload)
            transaction = buffer.getvalue()
            marker = "\nSELECT 'p003_verified' AS status;"
            for _ in range(2):
                result = self.assert_sql_passes(transaction + marker, "p003_verified")
                self.assertIn('"exact_ordinal_value_comparison": true', result)
                print(next(line.strip() for line in result.splitlines()
                           if re.search(r'qa_elapsed =', line)))
                print(next(line.strip() for line in result.splitlines()
                           if re.search(r'load_elapsed =', line)))
            check = """
DO $$
BEGIN
    IF (SELECT count(*) FROM p003_bank_campaign.source_snapshot) <> 1
       OR (SELECT count(*) FROM p003_bank_campaign.qa_run) <> 2
       OR NOT EXISTS (SELECT 1 FROM p003_bank_campaign.subscription_overall
                      WHERE numerator = 4640 AND denominator = 41188)
       OR (SELECT sum(denominator) FROM p003_bank_campaign.subscription_by_segment) <> 7 * 41188
       OR (SELECT sum(denominator) FROM p003_bank_campaign.subscription_by_channel) <> 41188
       OR (SELECT sum(denominator) FROM p003_bank_campaign.subscription_by_prior_outcome) <> 41188
       OR (SELECT sum(frequency_numerator) FROM p003_bank_campaign.campaign_frequency) <> 41188
       OR (SELECT sum(denominator) FROM p003_bank_campaign.prior_contact_history
           WHERE history_disagreement) <> 4110
       OR has_table_privilege('p003_bank_reporter', 'p003_bank_campaign.source_observation', 'SELECT')
       OR has_table_privilege('p003_bank_reporter', 'p003_bank_campaign.source_observation', 'INSERT')
       OR has_schema_privilege('p003_bank_reporter', 'p003_bank_campaign', 'CREATE')
       OR NOT has_table_privilege('p003_bank_reporter', 'p003_bank_campaign.subscription_overall', 'SELECT')
    THEN
        RAISE EXCEPTION 'P003 repeat or reporting contract failed';
    END IF;
END;
$$;
"""
            self.assert_sql_passes(check + marker, "p003_verified")
            exploration = (ROOT / "sql/exploratory_findings.sql").read_text()
            output = self.assert_sql_passes(exploration + marker, "p003_verified")
            match = re.search(r'p003_findings = "(\{.*\})"\s*\(typeid', output)
            self.assertIsNotNone(match, "missing PostgreSQL findings JSON")
            findings = json.loads(match[1], parse_float=Decimal)
            verify(findings)
            findings["weights"][0]["weight_numerator"] += 1
            with self.assertRaisesRegex(ValueError, "eligibility and weights"):
                verify(findings)

            started = time.monotonic()
            segmentation = (ROOT / "sql/segmentation.sql").read_text()
            output = self.assert_sql_passes(segmentation + marker, "p003_verified")
            sql_elapsed = time.monotonic() - started
            match = re.search(r'p003_segmentation = "(\{.*\})"\s*\(typeid', output)
            self.assertIsNotNone(match, "missing PostgreSQL segmentation JSON")
            result = json.loads(match[1], parse_float=Decimal)
            started = time.monotonic()
            verify_segmentation(result)
            print(f"Task 005 SQL wall time: {sql_elapsed:.3f}s; reconciliation: {time.monotonic()-started:.3f}s")
            result["channel_weights"][0]["weight_numerator"] += 1
            with self.assertRaisesRegex(ValueError, "channel weight counts"):
                verify_segmentation(result)

            started = time.monotonic()
            output = self.assert_sql_passes(read_sql() + marker, "p003_verified")
            export_sql_seconds = time.monotonic() - started
            matched = re.findall(r'p003_(?:findings|segmentation|export_frequency) = "(\{.*\})"\s*\(typeid', output)
            self.assertEqual(len(matched), 3)
            started = time.monotonic()
            datasets = build_datasets(*(json.loads(item, parse_float=Decimal) for item in matched))
            check_exports(self, datasets)
            print(f"Task 006 SQL wall time: {export_sql_seconds:.3f}s; export reconciliation: "
                  f"{time.monotonic()-started:.3f}s")

            self.assertIn("P003 source records are immutable", self.run_sql(
                "DELETE FROM p003_bank_campaign.source_observation WHERE source_row = 1;"))
            self.assertIn("P003 source snapshot is sealed", self.run_sql(
                "INSERT INTO p003_bank_campaign.source_observation "
                "SELECT * FROM p003_bank_campaign.source_observation WHERE source_row = 1;"))
            changed = transaction.replace("DO $qa$", "UPDATE pg_temp.p003_csv SET age = '999' "
                                          "WHERE source_row = 1;\nDO $qa$", 1)
            self.assertIn("P003 CSV reconciliation failed at source row 1", self.run_sql(changed))
            self.assert_sql_passes(check + marker, "p003_verified")
