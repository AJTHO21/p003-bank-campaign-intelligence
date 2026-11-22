# Customer segmentation and campaign performance

## What stands out

The subscription baseline was **4,640 / 41,188 observations (11.27%)**. The [full tables](segmentation-tables.md) report counts, rates, 95% Wilson intervals, and benchmark gaps for every observed job, education level, age band, loan status, channel, month and weekday. Literal `unknown` categories remain visible.

- **Realized channel.** Cellular was **3,853 / 26,144 (14.74%, 95% Wilson interval 14.31–15.17%)** and telephone was **787 / 15,044 (5.23%, 4.89–5.60%)**. The crude gap was **+9.51 percentage points**. It remained positive after separate standardization by prior outcome (**+6.43 pp**) and month (**+8.04 pp**). Cellular led within all three prior-outcome strata. Telephone led in April, August and November among the nine months included in standardization.
- **Age and job.** The 60+ group recorded **472 / 1,193 (39.56%, 36.83–42.37%)**. Students recorded **275 / 875 (31.43%, 28.44–34.58%)**, and retired observations recorded **434 / 1,720 (25.23%, 23.24–27.34%)**. Their rates remained above the overall benchmark under the common prior-outcome mix, at **32.76%**, **26.61%**, and **21.76%**, respectively. These demographic associations describe the historical sample. Job and age groups can overlap.
- **Education and loans.** University degree was **1,670 / 12,168 (13.72%)**, declining to **13.15%** after prior-outcome standardization. The rare `illiterate` category had **4 / 18 (22.22%, 9.00–45.22%)** and lacked support for an adjusted estimate. Housing and personal loan yes/no groups were within half a percentage point of the baseline after prior-outcome standardization. Unknown loan statuses remain in the descriptive tables.
- **Calendar.** March was **276 / 546 (50.55%)**, compared with **886 / 13,769 (6.43%)** in May. Month combines contacts across years and group composition varies. Weekday rates ranged from **9.95%** on Monday (847 / 8,514) to **12.12%** on Thursday (1,045 / 8,623).

## Channel comparison support

| Reference mix | Included strata | Cellular subscribed / observations | Telephone subscribed / observations | Cellular rate | Telephone rate | Cellular minus telephone |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Observed, crude | — | 3,853 / 26,144 | 787 / 15,044 | 14.74% | 5.23% | +9.51 pp |
| Prior outcome, standardized | 3 / 3 | 3,853 / 26,144 | 787 / 15,044 | 13.79% | 7.36% | +6.43 pp |
| Realized month, standardized | 9 / 10 | 3,775 / 25,995 | 776 / 15,011 | 16.98% | 8.94% | +8.04 pp |

Every reported rate uses released observations with a yes/no target and keeps exact repeats. Channel comparisons use cellular and telephone. Age bands are under 30, 30–39, 40–49, 50–59 and 60+, inclusive at the lower bound for each numbered band. Marginal rates use the overall baseline. Cross-tab rates use the corresponding pooled month or prior-outcome baseline. Gaps are calculated before rounding.

A cell needs at least **50 observations, five subscriptions and five non-subscriptions** for standardization. This is a support screen, and cells below it remain visible. Channel standardization weights each eligible stratum by its pooled count across both channels. December was excluded from month standardization because telephone had 11 subscriptions in 33 observations. The month and prior-outcome channel estimates are separate adjustments. For demographic and loan segments, the weights are the overall prior-outcome proportions. An adjusted segment rate is withheld if any outcome cell fails the screen. Eight of 31 segment levels were withheld. The [full tables](segmentation-tables.md) include all cells, weights and exclusions.

## Uncertainty and interpretation

The 95% Wilson intervals summarize row-level binomial precision for observed rates. They assume independent observations, and may be too narrow if customers or campaigns repeat. Customer and campaign identifiers are unavailable. Intervals are unadjusted for multiple comparisons. The many overlapping segment and stratum comparisons increase the chance of apparent differences, so the report avoids significance claims and rankings of sparse cells. Standardized results are descriptive point estimates. The support screen does not establish statistical robustness.

The data describe selected outreach at one Portuguese bank in 2008–2010. Differences may reflect selection, time, assignment, follow-up or other unmeasured factors. Exact dates are unavailable, and realized channel and timing are historical contact attributes. Duration was excluded from the analysis. The release has no verified costs or revenue for ROI estimates.

## Dashboard priorities

1. Start with the overall subscription rate, subscriptions and observation count. Label counts as observations.
2. Show channel comparisons with their denominators, Wilson intervals and a prior-outcome breakdown. Place the separate standardized comparisons beside their eligibility notes.
3. Pair monthly and weekday rates with observation volumes. Surface December’s sparse telephone cell and label months as pooled across years.
4. Offer job, education, age and loan-status detail with visible unknowns and support flags. Keep demographic findings descriptive.

See [QA and reproduction](segmentation-qa.md) for the verified SQL workflow.
