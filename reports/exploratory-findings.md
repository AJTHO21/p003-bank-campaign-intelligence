# Exploratory findings register

The unit is one released outreach observation from the verified UCI 222 snapshot. All rates use the count of subscribed rows divided by the count of eligible yes/no rows. Exact repeats remain in the analysis.

## Baseline, realized channel and prior campaign outcome

| Eligible group | Subscribed | Observations | Rate |
| --- | ---: | ---: | ---: |
| All eligible observations | 4,640 | 41,188 | 11.27% |
| Cellular last contact | 3,853 | 26,144 | 14.74% |
| Telephone last contact | 787 | 15,044 | 5.23% |
| Previous success | 894 | 1,373 | 65.11% |
| Previous failure | 605 | 4,252 | 14.23% |
| No prior outcome, source level nonexistent | 3,141 | 35,563 | 8.83% |

The cellular rate exceeds the telephone rate by **9.51 percentage points**. Both recognized channels are represented, and all observations have a recognized channel. The previous-success rate exceeds the previous-failure rate by 50.88 pp, and the previous-failure rate exceeds the nonexistent-outcome rate by 5.40 pp.

## Prior-contact history and elapsed days

| Recorded prior contacts | Previous outcome | pdays status | Subscribed / observations | Rate |
| --- | --- | --- | ---: | ---: |
| Zero | Nonexistent | 999 sentinel | 3,141 / 35,563 | 8.83% |
| Positive | Failure | 999 sentinel | 532 / 4,110 | 12.94% |
| Positive | Failure | Non-sentinel | 73 / 142 | 51.41% |
| Positive | Success | Non-sentinel | 894 / 1,373 | 65.11% |

These are all observed history combinations. The 4,110 sentinel observations with positive prior contacts remain flagged as disagreements. Among 1,515 non-sentinel observations, 967 subscribed (63.83%). Elapsed days range from 0 through 27. The SQL output includes exact-day counts and outcomes overall and by prior outcome. Every elapsed-day denominator excludes the sentinel.

## Prior failure comparisons

All comparisons below are within the recorded prior-failure subgroup. The direction is non-sentinel minus sentinel. The unadjusted gap is **+38.46 pp** (73/142 versus 532/4,110).

| Comparison | Included strata | Non-sentinel subscribed / eligible | Sentinel subscribed / eligible | Standardized rates, non-sentinel / sentinel | Gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Month | 10 | 73 / 142 | 532 / 4,110 | 44.39% / 13.29% | **+31.10 pp** |
| Seven-month sensitivity | 7 | 66 / 128 | 415 / 3,340 | 47.06% / 12.80% | **+34.26 pp** |
| Contact frequency | 4 | 73 / 142 | 532 / 4,110 | 50.91% / 12.94% | **+37.97 pp** |

The count columns show group support. Standardized rates are weighted averages of stratum-specific rates. Each included stratum receives the same weight for both groups, equal to its pooled count divided by the pooled count of included strata. Calculations use unrounded rates and weights. Month and frequency were adjusted in separate comparisons.

### Stratum support and weights

A stratum is flagged sparse when either group has fewer than 10 observations. The full month comparison retains every observed month with both groups represented. The sensitivity comparison requires at least 10 observations in each group and excludes April, December and March, removing 14 non-sentinel and 770 sentinel observations. The four frequency bands have both groups represented and none is sparse under this rule. Blank weights indicate that standardization was not performed for that dimension.

| Dimension | Stratum | Non-sentinel n/N (rate) | Sentinel n/N (rate) | Gap (pp) | Full weight | Seven-month weight | Sparse |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| channel | cellular | 68/132 (51.52%) | 503/3,820 (13.17%) | +38.35 |  |  |  |
| channel | telephone | 5/10 (50.00%) | 29/290 (10.00%) | +40.00 |  |  |  |
| frequency | 1 | 44/73 (60.27%) | 278/2,054 (13.53%) | +46.74 | 2,127/4,252 |  |  |
| frequency | 2 | 18/43 (41.86%) | 138/1,137 (12.14%) | +29.72 | 1,180/4,252 |  |  |
| frequency | 3 | 7/13 (53.85%) | 58/412 (14.08%) | +39.77 | 425/4,252 |  |  |
| frequency | 4+ | 4/13 (30.77%) | 58/507 (11.44%) | +19.33 | 520/4,252 |  |  |
| month | apr | 1/4 (25.00%) | 72/643 (11.20%) | +13.80 | 647/4,252 | Excluded | Yes |
| month | aug | 18/31 (58.06%) | 61/223 (27.35%) | +30.71 | 254/4,252 | 254/3,468 |  |
| month | dec | 1/1 (100.00%) | 12/38 (31.58%) | +68.42 | 39/4,252 | Excluded | Yes |
| month | jul | 7/10 (70.00%) | 42/110 (38.18%) | +31.82 | 120/4,252 | 120/3,468 |  |
| month | jun | 7/10 (70.00%) | 47/161 (29.19%) | +40.81 | 171/4,252 | 171/3,468 |  |
| month | mar | 5/9 (55.56%) | 33/89 (37.08%) | +18.48 | 98/4,252 | Excluded | Yes |
| month | may | 7/18 (38.89%) | 123/1,761 (6.98%) | +31.90 | 1,779/4,252 | 1,779/3,468 |  |
| month | nov | 14/25 (56.00%) | 58/814 (7.13%) | +48.87 | 839/4,252 | 839/3,468 |  |
| month | oct | 7/21 (33.33%) | 50/147 (34.01%) | -0.68 | 168/4,252 | 168/3,468 |  |
| month | sep | 6/13 (46.15%) | 34/124 (27.42%) | +18.73 | 137/4,252 | 137/3,468 |  |

See the [limitations](statistical-limitations.md) and [QA and reproduction instructions](exploratory-qa.md).
