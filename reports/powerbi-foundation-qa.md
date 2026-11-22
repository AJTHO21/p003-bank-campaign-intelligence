# Task 007 offline QA

| Check | Result |
| --- | --- |
| Task 006 provenance | Pinned manifest and all 12 CSV SHA-256 hashes verified. The available artifact is the disposable-PostgreSQL export from Task 006. |
| Imports | 12 tables, 383 aggregate rows. Exact ordered headers, column types, nullable fields, unique grain keys and snapshot fingerprint verified. |
| Executive baseline | 41,188 observations, 4,640 subscriptions, 11.27%. |
| Realized channels | Cellular 3,853 / 26,144 (14.74%). Telephone 787 / 15,044 (5.23%). Crude gap +9.51 pp. |
| Channel standardization | +6.43 pp by previous outcome. +8.04 pp by contact month. |
| Prior-failure comparisons | +38.46 pp crude, +31.10 pp by month, +34.26 pp in seven-month sensitivity, +37.97 pp by contact frequency. |
| Definition validation | Seven PBIP/PBIR/PBISM documents passed Microsoft JSON Schema checks. Static TMDL checks verified 12 import partitions, exact model/source types and DAX references, a safe P003-only Windows path and zero model relationships. |
| Transfer safeguards | Seven offline tests passed on disposable paths. They exercised unchanged reruns, rollback, cache preservation, modified CSV and type rejection, destination drift, corrupt backup, unapplied query changes and recovery of a partially interrupted transfer. |
| Prior analytics regression | All eight existing tests passed in disposable PostgreSQL, including Task 006 deterministic export reconciliation. |
| Runtime checks deferred at Task 007 | Desktop load, Microsoft TOM deserialization, Power Query refresh, DAX evaluation, theme application and Windows transfer behavior. |

Task 007 ended before Windows sync or visual construction. Both pages in the later dashboard checkpoint loaded and refreshed in Power BI Desktop. [Portfolio case study](../docs/portfolio-case-study.md) See the [project inventory](../powerbi/README.md) and [handoff procedure](../powerbi/windows-handoff.md).
