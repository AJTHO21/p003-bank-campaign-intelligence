# Data quality and analytical issue register

| Issue | Verified evidence | Proposed handling and outstanding risk |
| --- | --- | --- |
| Source integrity | Manifest sizes and SHA-256 hashes verified. CSV and saved profile agree | Pin the CSV hash and reconcile row counts on a future load |
| Record identity | 41,188 outreach observations. Customer, campaign and call identifiers are absent | Track a source record ordinal per snapshot. Unique customer counts and linkage remain unsupported |
| Exact repeats | 12 pairs, 24 participating rows and 12 additional copies | Retain all rows. Report exact-tuple sensitivity where relevant. Repeat origin is unresolved |
| Categorical missingness | Zero blank or whitespace-only cells. 10,700 rows contain literal unknown across six fields | Keep unknown levels and disclose their prevalence. Missingness mechanism is unknown |
| Prior contact sentinel | 39,673 rows have pdays=999. Of these, 4,110 record positive previous contacts and a prior failure | Preserve raw fields, flag disagreement and exclude 999 from elapsed-day summaries. Prior contact status cannot be inferred from the sentinel alone |
| Structural prior outcome | 35,563 nonexistent outcomes, all with previous=0 and pdays=999 | Keep nonexistent as its own source-defined grouping |
| Numeric validity and tails | Semantic minimum checks passed. Multiple fields have IQR flags, including every nonzero previous count | Retain tails. Investigate extreme values in context. IQR flags carry no automatic exclusion |
| Target balance | 4,640 yes and 36,548 no | Show rates with numerators and denominators |
| Duration leakage | Duration is measured at the last call. Four zero-duration rows all have y=no | Exclude duration from all pre-call targeting analyses |
| Other information leakage | Realized channel, timing, cumulative contacts and outcome depend on the recorded outreach. Client snapshots and indicator release timing are unverified | Require a defined decision time and evidence of as-of availability |
| Time coverage | Source notes give May 2008 through November 2010 in chronological file order, with month and weekday fields | Preserve order. Exact dates, year-specific seasonality and applicability to current campaigns remain unverified |
| Selection and confounding | The release contains observations from outreach by one bank | Interpret segment, channel and frequency comparisons descriptively. Selection, assignment and stopping decisions may influence results |
| Campaign economics | The schema contains neither verified costs nor revenue | Subscription rates are in scope. Profit, ROI and break-even require additional data |

See the [analytical contract](analytical-contract.md) and [verified audit](../reports/initial-audit.md).
