# P003 Bank Campaign Intelligence

## Project overview

This portfolio project converts a historical bank marketing dataset into a reproducible analytical workflow and a two-page Power BI report. It focuses on clear denominators, visible support limits, and a defensible distinction between observed association and causal effect.

**Source:** Moro, Rita, and Cortez’s UCI Bank Marketing dataset, full bank-additional variant. The source citation, license, and snapshot fingerprint are documented in [provenance](provenance.md).

## The reporting experience

**Executive Campaign Overview** presents the eligible observation and subscription baseline, observed rates by realized channel and previous campaign outcome, and their supporting counts.

**Channel & Campaign Performance** adds the channel breakdown by previous outcome, observed rates by pooled calendar month, campaign contact frequency, and separate standardized channel comparisons. The supported month chart displays March through November in calendar order and pools observations across years. Hovering a supported month displays sample counts for both channels.

December is excluded from the standardized month comparison for both channels. The exclusion covers 182 observations (149 cellular and 33 telephone). The telephone cell falls below the support threshold.

## Verified results

The reporting bundle contains 12 aggregate tables and 383 summary rows. In the full eligible snapshot, 4,640 of 41,188 observations subscribed (11.27%). Cellular observations had a 14.74% subscription rate (3,853 / 26,144); telephone observations had a 5.23% rate (787 / 15,044).

The observed cellular-minus-telephone gap is +9.51 percentage points. It is +6.43 pp after standardizing by previous campaign outcome and +8.04 pp after standardizing by supported month. Each adjustment uses its own shared reference mix.

## How it was built

- Verified and fingerprinted the source snapshot and reporting exports.
- Defined explicit grains, denominators, unknown-category handling, and support rules.
- Reconciled the PostgreSQL-derived reporting bundle to pinned aggregate data.
- Built PBIP, PBIR, TMDL, and DAX definitions with deterministic generators.
- Added atomic writes, exact-hash preflight checks, regression tests, and a strict drift-guarded Windows handoff.
- Preserved noncausal interpretation and observation counts alongside rates.

The channel standardizations require each included channel cell to have at least 50 observations, five subscriptions, and five non-subscriptions. Unsupported cells remain visible in the underlying analysis and are excluded from the corresponding standardization.

## Interpretation and limits

This is descriptive analysis of selected outreach records from one Portuguese bank in 2008–2010. Channel, timing, customer composition, follow-up, and stopping decisions may differ across groups. Customer and campaign identifiers are not available, so observations may not be independent. Month pools contacts across years, and the month and previous-outcome comparisons are separate adjustments. No causal effect, future targeting performance, campaign economics, or return on investment is established.

## Reproducibility and data handling

The repository contains project definitions, analysis code, QA records, and documentation. Local raw-data copies and aggregate CSV exports are excluded from Git; no private CSV bundle is part of this case study. The public source citation and license are available in [provenance](provenance.md). Refreshing the report requires the exact pinned local reporting bundle and a machine-local CSV folder parameter. See the [Power BI guide](../powerbi/README.md).

Run the PBIP build, static project validation, and test suites from the WSL checkout using the commands in the [repository README](../README.md). Power BI Desktop acceptance is complete for the approved dashboard. The public copy retains its analytics and report definitions with a portable data-folder parameter. Both report pages loaded and refreshed, the supported month chart displayed March through November, and the December exclusion card displayed 182 observations. The [dashboard previews](../README.md#dashboard-previews) show the accepted report.
