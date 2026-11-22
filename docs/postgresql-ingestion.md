# PostgreSQL staging and integrity

## Run in normal WSL

Use a running PostgreSQL 14+ server, `psql`, and a login authorized to create the project schema and reporting role. On reruns the login needs ownership of the project objects and grant authority on the reporting role's project privileges. The loader targets only the project schema in the database you select. It uses libpq environment settings, honors a private `PGPASSFILE` or local peer authentication, and runs with password prompting disabled.

For a running local WSL server with an existing administrative login and peer authentication, use the following from the project root. Set `PGUSER` to the authorized login if it differs from your WSL username. The dedicated database creation is a one-time step; use an existing approved database if you prefer the isolated schema alone.

```bash
export PGPORT="${PGPORT:-5432}" PGUSER="${PGUSER:-$(id -un)}"
PGDATABASE=postgres createdb --no-password p003_bank_campaign
export PGDATABASE=p003_bank_campaign
python3 scripts/load_postgresql.py
```

Run the last line again to verify the repeat path. It leaves the snapshot and observations intact and appends a successful QA run. Set `PGHOST` if your server uses a socket directory other than the libpq default. For a password-authenticated server, set the host, port, database and user for that server and point `PGPASSFILE` at a private password file outside the project. Keep connection credentials and database dumps outside the workspace.

A database administrator can grant the NOLOGIN group role `p003_bank_reporter` to existing reporting logins. The group has schema usage and SELECT on the six reporting views. Its members' other grants are managed separately. The group has no direct access to the staged observations or metadata and receives no project write privileges.

## Schema and safeguards

| Object | Purpose |
| --- | --- |
| `p003_bank_campaign.source_snapshot` | Verified CSV SHA-256, complete source manifest, row count, load timestamp, login and load duration |
| `p003_bank_campaign.source_observation` | All 21 original columns typed as integer, exact unconstrained numeric or text. Composite key is snapshot SHA-256 and 1-based CSV record ordinal. Retrieve the original sequence with `ORDER BY source_row` within the snapshot |
| `p003_bank_campaign.qa_run` | Successful reconciliation timestamp, login, QA duration and results. The CLI also prints overall elapsed wall time |
| [Reporting view definitions](../sql/reporting.sql) | Row-based subscription rates and campaign frequencies. Each rate carries numerator and denominator. Age uses exact years. The prior-history view exposes sentinel and disagreement flags |

The loader pins the approved CSV hash, checks all manifest file hashes, and builds a temporary text relation keyed by the source ordinal. It uses client-streamed COPY. A transaction-scoped advisory lock serializes runs. Before commit, a full join by ordinal detects missing, extra, reordered or changed observations. Each typed value is cast back to text and compared to the exact parsed source token, including decimal scale. This reconciles numeric ranges, categorical distributions and unknown frequencies as a consequence of record equality. A failed load or comparison rolls back. Once registered, a snapshot rejects inserts, updates, deletes and truncation through ordinary DML. Administrative users with DDL authority can override database protections.

Reporting rates describe released observations. A group with no eligible rows has no view row and should be rendered unavailable. Show support counts and disclose any reporting threshold before comparing sparse groups. Contact channel describes the realized last contact. Prior-history comparisons use `previous > 0` as recorded history and retain the original outcome and sentinel separately. The views include no call duration or predictive features.

## Reproduce database-engine QA

An isolated single-user PostgreSQL cluster exercises the same transaction using server-side COPY of the identical CSV payload. It requires the server binaries and a non-root user. On a WSL installation with the matching PostgreSQL tools on the path:

```bash
python3 scripts/profile_data.py
P003_PG_BIN="$(pg_config --bindir)" python3 -m unittest discover -s tests -v
```

See the [Task 003 QA record](../reports/postgresql-qa.md) for execution results and the live connection limitation.
