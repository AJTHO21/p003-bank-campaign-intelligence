# Task 003 PostgreSQL QA

**2026-11-21, PostgreSQL 18.6.** Eight tests passed in 6.096 seconds. A disposable single-user cluster executed the ingestion transaction with server-side COPY. The normal WSL client COPY payload was separately checked against every source record. The sandbox denied PostgreSQL socket connections and server binds, so the live WSL client load remains pending.

| Reconciliation check | PostgreSQL result |
| --- | ---: |
| Source observations | 41,188 |
| Subscriptions, yes | 4,640 |
| Subscriptions, no | 36,548 |
| Additional exact duplicates | 12 |
| pdays = 999 | 39,673 |
| pdays = 999 with positive prior contacts | 4,110 |
| Zero-duration observations | 4 |
| Missing, extra or changed ordinal/value matches | 0 |

The comparison checked all 21 fields for every ordinal against the exact parsed CSV tokens. The match verifies the numeric ranges and decimal scale, all categorical distributions, and unknown counts (default 8,597, education 1,731, housing 990, loan 990, job 330 and marital 80). The raw manifest and saved profile also passed the Task 002 regression tests.

The initial typed insert and snapshot registration took 0.540 seconds. Reconciliation took 0.411 seconds initially and 0.498 seconds on repeat. The repeat retained a single snapshot with identical observations and recorded a second QA run. A deliberately changed input value failed reconciliation at ordinal 1 and rolled back. The test checked the reporting view denominators, read-only group privileges, rejected deletion and rejected insertion into the sealed snapshot.

The row sequence is the CSV ordinal. The source still has no customer identifier or exact dates, and the prior-history disagreement remains unresolved. Reporting is descriptive. Duration is absent from the reporting views.

Run the [normal WSL ingestion command](../docs/postgresql-ingestion.md) to establish the persistent staging schema and record live QA.
