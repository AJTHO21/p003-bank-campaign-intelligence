# Power BI Desktop setup

The public project uses a neutral `P003CsvFolder` placeholder. Obtain the exact pinned reporting bundle and complete the local checks before preparing a Desktop copy. [Reproduction instructions](../README.md#reproduce-locally)

## Configure a Desktop copy

1. With Power BI Desktop closed, copy the PBIP entry point and its adjacent Report and SemanticModel directories into a separate folder visible to Windows. Keep the source checkout as the deterministic validation copy.
2. In the Desktop copy, open the SemanticModel directory's `definition/expressions.tmdl` in a text editor. Replace only `SET_P003_CSV_FOLDER` within the string assigned to `P003CsvFolder` with the full Windows path to the verified aggregate CSV directory. Preserve the surrounding quotes and parameter metadata. Use a folder without a trailing separator.
3. Open the copied PBIP in Power BI Desktop and refresh. Confirm all 12 table counts, both report pages, and the March–November chart and 182-observation December exclusion. The source data and Desktop caches stay local. [Microsoft PBIP documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)

The approved dashboards were accepted in Desktop. The public copy needs the machine-local setup above, and a saved edit to the working report belongs in the Desktop copy.

## Optional guarded transfer from WSL

For repeatable transfers, choose a dedicated destination outside the checkout. Set `P003_DESTINATION` in your shell to its absolute path as seen from WSL. Run these commands from the repository root with Power BI Desktop closed before any transfer.

```bash
python3 powerbi/tools/sync.py plan --destination "${P003_DESTINATION:?Set a local destination}"
python3 powerbi/tools/sync.py sync --destination "$P003_DESTINATION" --desktop-closed
```

The plan is read-only. A transfer places the validated, portable project and private aggregate CSVs in the destination, so choose a location with appropriate Windows access controls. It leaves the neutral parameter in the managed files. Use the transferred project as the source for a separate, configured Desktop copy. Direct edits to the managed destination trigger drift refusal. Destination-specific state and backups are kept under the checkout's ignored `powerbi/.sync/` directory.

For a completed transfer use `rollback`; for a pending journal use `recover`. Pass the same destination and `--desktop-closed`. Recovery checks the recorded hashes and refuses changes outside the recorded transfer states.
