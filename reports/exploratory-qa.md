# Exploration QA and reproduction

**Result on 2026-11-21.** Eight tests passed in 6.468 seconds, including execution of the read-only exploration query in a disposable PostgreSQL 18.6 cluster populated from the verified CSV. Independent Python reconciliation recomputed every count, rate, weight and standardized gap using exact rational arithmetic. It also tested rejection of a deliberately corrupted SQL weight. The pre-existing snapshot tests verified the pinned hash and complete staging reconciliation.

**Discrepancies.** All figures supplied in Task 004B matched at their stated precision. The workspace contained no earlier exploratory query output or method notes for these standardizations. The evidence fixture therefore preserves the supplied headline figures. Pooled weights, the per-group threshold of 10 in the seven-month sensitivity, and frequency bands of 1, 2, 3 and 4+ were reconstructed and independently verified from the CSV. The sandbox blocked the live PostgreSQL socket, so production connection QA remains pending.

## Reproduce from the staged PostgreSQL snapshot

In normal WSL, use the established libpq environment for the staged P003 database. The executing role must be able to read the source observation table and reporting views. The existing reporting-only role can read the views, but the detailed stratifications also require the staging fields. The query itself runs in a read-only repeatable-read transaction.

```bash
p003_findings_json="$(mktemp -t p003-findings.XXXXXX.json)"
psql -X -w -Atq -v ON_ERROR_STOP=1 -f sql/exploratory_findings.sql > "$p003_findings_json" &&
  python3 scripts/verify_exploratory_findings.py "$p003_findings_json"
```

The JSON contains baseline, channel and prior-outcome results, observed history combinations, non-sentinel day counts, stratum rates and gaps, and every weight and inclusion flag. The verifier exits nonzero for differences and reports the affected check. If the approved snapshot has yet to be staged in WSL, see the [ingestion guide](../docs/postgresql-ingestion.md).

## Reproduce disposable database QA

```bash
P003_PG_BIN="$(pg_config --bindir)" python3 -m unittest discover -s tests -v
```
