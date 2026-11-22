# Analytical contract

**Task 002 proposal.** Scope is the acquired UCI 222 full bank-additional snapshot. Statistical units are released outreach observations carrying a last-contact description, current campaign contact count and subscription outcome. Customer and campaign identifiers and exact contact dates are absent. A source snapshot plus 1-based CSV record ordinal (header excluded) can identify a released row and preserve source order.

## Reporting definitions

Every subscription rate is the count of eligible rows with `y = yes` divided by eligible rows with `y` in `{yes, no}`. Apply filters to both numerator and denominator. Show numerator and denominator with the rate, and report a zero denominator as unavailable. Flag small denominators and avoid ranking sparse groups without a disclosed rule. This snapshot has valid outcomes for all rows. Future invalid or missing outcomes should fail validation and trigger review.

| Metric | Eligible rows and grouping |
| --- | --- |
| Overall subscription rate | All released rows with valid outcomes, including exact repeats. Baseline is 4,640 / 41,188 (11.27%). |
| Customer segment subscription rate | Group eligible rows by a documented client attribute. Use source levels for categorical fields and disclose any age band boundaries before use. Report unknown and missing levels separately when present. Rates describe observations within segments. |
| Contact channel subscription rate | Group eligible rows by realized last-contact channel, cellular or telephone. If a later snapshot has unavailable channel values, disclose those rows separately and exclude them from channel-specific denominators. |
| Prior outcome subscription rate | Group eligible rows by recorded `poutcome`, retaining failure, success and nonexistent. Keep any unavailable values separate. A previously contacted subset, if reported, must state its eligibility rule, such as `previous > 0`, and disclose the denominator. |
| Campaign contact-frequency patterns | For rows with valid `campaign >= 1`, report distributions of recorded contacts per observation, using counts and shares by exact count or explicitly stated bands. Apply the subscription-rate denominator within each band. The count includes the last contact. Row-level counts cannot establish unique call volume or the effect of an extra call. |

## Field availability

| Timing class | Fields | Rule |
| --- | --- | --- |
| Candidate before contact | `age`, `job`, `marital`, `education`, `default`, `housing`, `loan`, `previous`, `poutcome` | Require evidence that the client snapshot and prior campaign history existed at the chosen decision time. |
| Candidate before contact, reference date unresolved | `pdays` | Require a verified as-of date and consistent semantics before any targeting use. |
| During or after contact | `contact`, `month`, `day_of_week`, `duration`, `campaign`, `y` | These are realized last-contact fields, cumulative campaign counts and the realized outcome. Exclude the released values from pre-call targeting. Call duration is expressly excluded from every pre-call analysis, including feature selection and eligibility rules. A future planned channel or as-of contact count would require separately verified data. |
| Historical contextual information | `emp.var.rate`, `cons.price.idx`, `cons.conf.idx`, `euribor3m`, `nr.employed` | Use descriptively. Pre-call use requires recoverable dates and point-in-time publication and revision evidence. |

## Data handling

- Preserve raw bytes and source order. Retain exact repeat rows in the primary denominator. A sensitivity calculation may count one copy per exact 21-field tuple and must disclose the changed denominator. Tuple equality cannot establish customer identity.
- Preserve literal `unknown` as recorded categorical missingness. Report it as a separate level and keep it distinct from blanks, which would have a separate missing label in analytical outputs. Review unexpected blanks and categories during validation. Skip imputation.
- Preserve raw `pdays = 999`. UCI defines it as no previous contact. Given its disagreement with other history fields, report it as the **999 sentinel** and exclude it from elapsed-day calculations. Retain `previous` and `poutcome` as separately recorded. Report conflicts explicitly. Treat `poutcome = nonexistent` as a source-defined category.
- Review invalid values before ingestion. Validate finite numeric parsing, positive age, campaign count, consumer price index and employment level, and nonnegative duration, days and prior-contact count. Treat observed maxima as snapshot facts. Retain IQR flags and zero-duration rows.

## Use and ingestion readiness

The records describe outreach by one Portuguese bank in 2008–2010. Month and weekday repeat across years. Source order supports relative sequence only. Outreach selection, channel assignment and follow-up decisions limit comparisons. Segment, channel and frequency results are observational associations. Costs and revenue are unavailable, so the release cannot establish profit or ROI.

The snapshot is ready for a future lossless PostgreSQL staging load once these rules are accepted. Stage every record with snapshot identity and source ordinal. Check the loaded row count, domains, outcome totals, duplicate multiplicities, blank and unknown counts, and sentinel disagreement against the [verified audit](../reports/initial-audit.md). Preserve raw field values and document any subsequent typed analytical representation. Eligibility for pre-call targeting remains unverified.
