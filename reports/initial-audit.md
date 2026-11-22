# Initial profiling report

Task 002 reproduced the local profile (`reports/profile.json`) from the verified CSV. The release contains 41,188 observations and 21 fields, including 20 inputs and the target. The source notes describe chronological order from May 2008 through November 2010. Each row is a released outreach observation with last-contact fields, campaign history and an outcome. Exact customer, call and campaign identity are unavailable. [UCI field notes acquisition](../docs/provenance.md)

## Outcome, duplicates and missingness

- `y` is yes for 4,640 rows (11.2654%) and no for 36,548 (88.7346%).
- Twelve exact pairs match on every parsed field, including target. Eleven pairs have y=no and one has y=yes. Five pairs are adjacent in source order. Counting one copy per pair for sensitivity gives 4,639 / 41,176 (11.2663%). The negligible overall change leaves segment effects and the origin of repeats unresolved.
- Source record ordinal pairs, excluding the header, are (1266, 1267), (12261, 12262), (14156, 14235), (16820, 16957), (18465, 18466), (20073, 20217), (20532, 20535), (25184, 25218), (28477, 28478), (32506, 32517), (36951, 36952), (38256, 38282).
- No empty or whitespace-only cells were found. Literal unknown appears on 10,700 rows (25.98%). Counts by field are default 8,597, education 1,731, housing 990, loan 990, job 330 and marital 80. Individual field counts can overlap.

## Prior history

| pdays | previous | poutcome | Rows |
| --- | --- | --- | ---: |
| 999 | 0 | nonexistent | 35,563 |
| 999 | Positive | failure | 4,110 |
| 0–27 | Positive | failure | 142 |
| 0–27 | Positive | success | 1,373 |

The 999 sentinel occurs on 39,673 rows (96.32%). The 4,110 disagreements prevent interpreting every sentinel as a verified lack of prior outreach. The remaining 1,515 rows carry elapsed-day values. [UCI field notes acquisition](../docs/provenance.md)

## Numeric review

All numeric values parsed and were finite. The proposed semantic minimum checks passed. The table counts observations strictly outside 1.5×IQR fences; pdays excludes the sentinel for that calculation.

| Field | Observed range | IQR flags |
| --- | --- | ---: |
| age | 17–98 | 469 |
| duration (seconds) | 0–4,918 | 2,963 |
| campaign | 1–56 | 2,406 |
| pdays | 0–27 elapsed, plus 999 | 82 |
| previous | 0–7 | 5,625 |
| emp.var.rate | −3.4–1.4 | 0 |
| cons.price.idx | 92.201–94.767 | 0 |
| cons.conf.idx | −50.8–−26.9 | 447 |
| euribor3m | 0.634–5.045 | 0 |
| nr.employed | 4,963.6–5,228.1 | 0 |

The IQR of previous is zero, so every positive count is flagged. All four zero-duration observations have y=no. Keep these and other flagged values in descriptive work. Duration is a post-call measure and is excluded from pre-call targeting.

## Next analytical step

Review the [proposed contract](../docs/analytical-contract.md) and [issue register](../docs/issue-register.md) before staging. A future descriptive analysis can compare the subscription baseline with prior outcome and recorded prior-contact groups, while showing unknowns, sentinel disagreements and row denominators. Realized channel and campaign frequency comparisons describe the recorded sample. Exact dates, representative modern outcomes and campaign economics are unavailable.
