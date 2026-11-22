# P003 Power BI foundation

Open [P003_Bank_Campaign_Intelligence.pbip](P003_Bank_Campaign_Intelligence.pbip) in Power BI Desktop after the separately authorized Windows handoff. The PBIP includes the 16:9 Executive Campaign Overview and Channel & Campaign Performance pages and a TMDL semantic model. This is a local project.

The model requires the exact pinned Task 006 bundle, which is kept locally. That bundle was produced and reconciled in a disposable PostgreSQL cluster. The model carries one disconnected import table per CSV. The private copy lives in `private_csv/` and is excluded from Git along with Desktop caches and sync backups.

| Import table | Rows | Grain, within the snapshot |
| --- | ---: | --- |
| executive_baseline | 1 | Whole snapshot |
| observed_segments | 48 | Dimension × level |
| observed_cross_tabs | 119 | Dimension × level × stratum type × stratum |
| previous_outcome | 3 | Previous outcome |
| campaign_frequency | 42 | Exact campaign contact count |
| prior_contact_history | 4 | Previous outcome × prior-contact flag × sentinel flag |
| non_sentinel_days | 72 | Scope × optional previous outcome × optional elapsed day |
| prior_failure_strata | 16 | Stratum dimension × stratum |
| comparison_estimates | 7 | Comparison family × method |
| comparison_weights | 37 | Comparison family × method × stratum |
| segment_estimates | 31 | Dimension × level |
| segment_weights | 3 | Previous outcome |
| **Total** | **383** | Inventory metric only |

Each Power Query import validates the ordered CSV headers and row count, parses UTF-8 using `en-US` decimal conventions, converts nullable blanks to null, and applies manifest-driven types. Model fields preserve counts, uncertainty intervals, sparse flags, source levels, weights, and support indicators. All 12 tables use the `P003CsvFolder` parameter. The checked-in value is the portable placeholder `SET_P003_CSV_FOLDER`. Configure the verified local CSV directory in a separate Desktop copy before opening the project. [Desktop setup](windows-handoff.md#configure-a-desktop-copy)

The model has zero relationships and disables default column summarization. Calculated observed rates divide subscription counts by eligible observation counts. The dimension, scope and stratum-type guards enforce a single compatible partition where needed. Standardized rate measures display a value only when exactly one summary row is selected. Aggregate counts describe overlapping observations across tables. Keep reports scoped to the [approved reporting grains and filters](../docs/powerbi-reporting-layer.md).

## Reproduce and validate locally

Follow the [source and export steps](../README.md#reproduce-locally) to obtain the exact pinned local bundle. From the repository root, run with Python 3 and the `jsonschema` and `referencing` packages available. The build reconstructs missing definitions and approved visuals. It upgrades the exact Task 007 blank page once and refuses to overwrite edited definitions or changed data. The generated project includes the Executive Campaign Overview and Channel & Campaign Performance pages. Static validation covers both pages and their model bindings.

```bash
python3 powerbi/tools/project.py build
python3 -m unittest discover -s powerbi/tools -v
```

Offline validation checks 29 schema-bearing project documents, generated TMDL structure, field types, Power Query paths, DAX references, and model integrity. Both pages loaded and refreshed in Power BI Desktop at the approved checkpoint. The supported month chart displayed March through November and the December card displayed 182 excluded observations. [Microsoft PBIP documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview) · [Microsoft TMDL parser documentation](https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-how-to)

Release validation passed 27 Power BI tests and eight analytical and disposable PostgreSQL tests. The checks used a disposable checkout with the verified raw snapshot, generated profile, and pinned reporting CSVs. These inputs stay outside Git. The public copy was validated offline. Refreshing it in Desktop requires the local folder setup above.

See [design system](design-system.md), [Windows handoff and recovery](windows-handoff.md), and [QA results](../reports/powerbi-foundation-qa.md).
