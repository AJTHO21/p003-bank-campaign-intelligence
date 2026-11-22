# Segmentation QA and reproduction

**2026-11-21, PostgreSQL 18.6.** The eight-test suite passed in 10.277 seconds. The Task 005 SQL took **0.660 seconds** wall time, including single-user process startup, and independent source reconciliation took **0.800 seconds**. A disposable cluster was populated with the pinned snapshot. The persistent database socket was blocked by the sandbox.

The verifier checked the source manifests and recomputed all marginal counts, cross-tab counts, reference rates, percentage-point differences, sparse-cell flags, Wilson interval endpoints, weights, and standardized estimates directly from the original CSV. A deliberately altered channel weight was rejected. Earlier staging and exploration tests also passed. The source hash and prior findings were preserved.

## Live WSL reproduction

Use the existing libpq environment and a role with SELECT access to the staging observations and approved views. The query runs in a read-only transaction.

```bash
p003_segmentation_json="$(mktemp -t p003-segmentation.XXXXXX.json)"
time psql -X -w -Atq -v ON_ERROR_STOP=1 -f sql/segmentation.sql > "$p003_segmentation_json" &&
  time python3 scripts/verify_segmentation.py "$p003_segmentation_json"
```

To regenerate and compare the detailed Markdown after verification:

```bash
python3 scripts/verify_segmentation.py "$p003_segmentation_json" --tables |
  diff -u reports/segmentation-tables.md -
```

To run the full QA suite with a disposable database:

```bash
P003_PG_BIN="$(pg_config --bindir)" python3 -m unittest discover -s tests -v
```

See the [staging instructions](../docs/postgresql-ingestion.md) if the live database still needs the approved snapshot.
