# P003 Power BI reporting layer

The bundle contains only aggregate reporting data for the approved UCI 222 snapshot. Keep the bundle and raw source private outside the public repository. Its manifest records the pinned source SHA-256, source-query hashes, CSV hashes, column types, nullability, primary grains and verified row counts. Every grain below is prefixed by the snapshot hash.

| CSV | Rows | Grain and supported filters |
| --- | ---: | --- |
| `executive_baseline` | 1 | Whole snapshot. Fixed executive KPI without segment or campaign slicers. |
| `observed_segments` | 48 | Dimension × level. Select one dimension for counts across levels. Dimensions are job, education, age band, housing, personal loan, realized contact channel, contact month and weekday. |
| `observed_cross_tabs` | 119 | Dimension × level × stratum type × stratum. Supports channel by previous outcome or month, and job, education, age band, housing and personal loan by previous outcome. Select one dimension and one stratum type before aggregating. |
| `previous_outcome` | 3 | Previous campaign outcome. Includes `nonexistent` as recorded. |
| `campaign_frequency` | 42 | Exact contact count within the current campaign. Filter by observed count; the fixed observation-share denominator covers all eligible frequencies. |
| `prior_contact_history` | 4 | Previous outcome × positive prior-contact flag × 999 sentinel flag. Filter by these fields or disagreement status. |
| `non_sentinel_days` | 72 | Scope × optional previous outcome × optional elapsed-day integer. Choose one scope before filtering or computing totals. |
| `prior_failure_strata` | 16 | Stratum dimension × stratum. Select channel, month or four contact-frequency bands; each dimension represents the same prior-failure population partitioned differently. |
| `comparison_estimates` | 7 | Family × method. Two crude rows and five standardized rows. Select a single row per displayed pair. |
| `comparison_weights` | 37 | Family × method × stratum. Includes support counts, exclusions and weights. Inspect within a single family and method. |
| `segment_estimates` | 31 | Segment dimension × level. Prior-outcome-standardized estimates. Select a single row per estimate. |
| `segment_weights` | 3 | Previous outcome. Fixed reference distribution for all eligible standardized segment estimates. |

**Dependencies.** The read-only queries reuse the [Task 004B exploration] and [Task 005 segmentation] and add [frequency extraction] from the approved reporting view. Execution needs SELECT access to the staged snapshot and the approved overall, channel, previous-outcome, prior-contact-history and frequency views. The existing views-only reporter role lacks staging access for detailed cross-tabs. Export verification also reads the immutable local source, manifest and Task 004B evidence fixture. No database objects are created or updated.

[Task 004B exploration]: ../sql/exploratory_findings.sql
[Task 005 segmentation]: ../sql/segmentation.sql
[frequency extraction]: ../sql/reporting_export.sql

## Field definitions and typing

CSV uses UTF-8, commas, dot decimals, invariant lowercase booleans and empty fields for null. Use the per-file manifest schema to assign Text, Whole Number, Decimal Number and True/False types. Use an explicit dot-decimal culture such as `en-US`. Use Decimal Number for rates and weighted values.

- `numerator` counts subscriptions and `denominator` counts eligible yes/no observations. `rate` is a proportion, such as 0.11265 for 11.27%. `reference_pct` and `wilson_low_pct` / `wilson_high_pct` use 0–100 units. `gap_pp` is a percentage-point difference. Observed segment levels use the overall reference. Cross-tab levels use the corresponding pooled stratum reference.
- `frequency_numerator` counts observations at that exact contact count. `frequency_denominator` is the same fixed reference population on every frequency row. `observation_share` is the proportion of the reference population at that count. `campaign` includes the recorded last contact.
- `dimension` identifies the attribute; `level` retains its observed category or the approved age band. `stratum_type` identifies the basis for stratification; `stratum` is its encoded value. The month and weekday fields describe the realized last contact. Use calendar sort keys for month and weekday labels. Absent months have no source observations.
- `recorded_prior_contacts` means `previous > 0`. `pdays_sentinel` identifies the literal 999 source code. `history_disagreement` flags positive prior contacts alongside the sentinel. The elapsed-day table excludes 999. Its scopes are `overall`, `outcome_total`, `day_total` and `day_by_outcome`. Null group keys identify rollups. Row-count denominators for task results retain exact repeats.
- `a_yes` / `a_n` and `b_yes` / `b_n` are raw supporting subscriptions and observations. In the channel family, A is cellular and B is telephone. In the prior-failure family and strata table, A is non-sentinel and B is sentinel. `gap_pp` is A minus B. `a_rate` and `b_rate` are proportions and follow the declared `estimate_type` in the estimate table. In weight and stratum tables those rates are observed.
- `weight_numerator` counts observations contributing reference weight for that stratum, and `weight_denominator` is the fixed reference population for its method. `included` identifies the supported strata selected by the method. Excluded strata have weight zero and retain their observed counts. `included_strata` counts strata used in a standardized estimate. `minimum_per_group` is the method's observation threshold. Channel standardization also requires at least five subscriptions and five non-subscriptions per channel cell.
- `weighted_a_numerator` / `weighted_b_numerator` or `weighted_numerator` represent subscriptions implied by standardization on the weighted reference population. Dividing by `weighted_denominator` gives the standardized proportion. Fractional implied subscriptions are valid. Raw support for segment estimates remains in `numerator` and `denominator`. Crude comparisons have null weighted fields. Segment estimates with sparse prior-outcome strata have null adjusted and weighted values.
- `sparse` in observed segments and cross-tabs means fewer than 50 observations or fewer than five of either outcome. In prior-failure strata, a cell is sparse when either side has fewer than 10 observations. Full prior-failure month and frequency estimates can retain sparse strata when both groups have support. The seven-month sensitivity excludes strata below 10 per group. `a_sparse` and `b_sparse` apply the corresponding family rule to each side. `sparse_strata` counts segment outcome cells failing the support screen.

## Power BI model recommendations

Import each CSV as its own aggregate table. Avoid fact-to-fact filter paths. Use conformed lookups only for labels whose meaning is shared, with single-direction filtering and slicers scoped to compatible tables. Keep executive KPIs fixed to the snapshot. Controls for month and prior outcome can use the supplied cross-tabs in separate views. The exports provide neither joint month × prior-outcome cells nor arbitrary compound filters such as age × loan status.

For observed rates, use `DIVIDE(SUM(numerator), SUM(denominator))` within a disjoint partition at the declared grain. Guard the measure with a single dimension, stratum type or scope where required. Use individual stored standardized estimates only in a single family × method or segment × level context, such as with `SELECTEDVALUE`. Adjusted rates, interval bounds, fixed reference denominators and weights are non-additive. Avoid totals across overlapping aggregate tables and averaging stored percentages. Standardized estimates use fixed comparison weights. Changes to related slicers do not re-estimate those weights.

Lead with subscriptions, observations, the 11.27% baseline and channel volumes. Follow with prior outcome, calendar and campaign contact frequency. Use a separate investigation page for sentinel handling, weights, exclusions and Wilson interval tooltips. Keep unknown labels and sparse flags visible.

## Interpretation

These are historical, descriptive associations among released observations from one Portuguese bank. The data lack verified customer IDs, exact dates and campaign costs or revenue. Wilson intervals are row-level and may understate uncertainty if observations are dependent. Intervals are unadjusted for multiple comparisons and apply only to observed cells. Standardized results are descriptive point estimates, and month and frequency adjustments are separate. No causal, ROI or targeting estimate is supported. Call duration is absent from the bundle.
