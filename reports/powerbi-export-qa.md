# Task 006 export QA

The eight-test suite passed in a disposable PostgreSQL 18.6 cluster on 2026-11-21. Suite wall time was **13.059 s**. The combined read-only SQL took **0.809 s** including single-user process startup. Reconciliation and CSV checks took **1.954 s**. The sandbox blocked the persistent server socket.

QA reconciled the query outputs from the verified raw CSV through the Task 004B and Task 005 independent verifiers. Added checks verified exact campaign-frequency bins, category totals, 1,515 elapsed-day observations, the 12 output grains and their field types, deterministic file bytes, hashes, supported strata and exclusions, and weighted-rate reconstruction from exported stratum counts. The verified baseline was 4,640 / 41,188. Adjusted gaps matched the previously verified results. The bundle writer passed rerun and tamper-rejection tests. Source bytes and persistent staging records were preserved.

## Live WSL reproduction

Run from normal WSL with the existing libpq connection settings and a login with the read permissions described in the [reporting guide](../docs/powerbi-reporting-layer.md). The command validates the SQL output before creating a private, content-addressed bundle. Its first output line is the bundle path. Rerunning against the same result reuses the bundle after byte verification.

```bash
python3 scripts/export_powerbi.py
```

Re-run the complete suite in a disposable cluster:

```bash
python3 scripts/profile_data.py
P003_PG_BIN="$(pg_config --bindir)" python3 -m unittest discover -s tests -v
```

The exports are Git-ignored under `data/reporting/task006/`. Keep the raw source and exports local outside the public repository.
