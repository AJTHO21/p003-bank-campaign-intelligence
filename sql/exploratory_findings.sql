BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH snapshot AS (
    SELECT '74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8'::text AS source_sha256
), eligible AS (
    SELECT contact, month, campaign, pdays, poutcome, y
    FROM p003_bank_campaign.source_observation JOIN snapshot USING (source_sha256)
    WHERE y IN ('yes', 'no')
), baseline AS (
    SELECT numerator, denominator, 100 * subscription_rate AS rate_pct
    FROM p003_bank_campaign.subscription_overall JOIN snapshot USING (source_sha256)
), channels AS (
    SELECT contact, numerator, denominator, 100 * subscription_rate AS rate_pct
    FROM p003_bank_campaign.subscription_by_channel JOIN snapshot USING (source_sha256)
), outcomes AS (
    SELECT poutcome, numerator, denominator, 100 * subscription_rate AS rate_pct
    FROM p003_bank_campaign.subscription_by_prior_outcome JOIN snapshot USING (source_sha256)
), history AS (
    SELECT recorded_prior_contacts, poutcome, pdays_sentinel, history_disagreement,
           numerator, denominator, 100 * subscription_rate AS rate_pct
    FROM p003_bank_campaign.prior_contact_history JOIN snapshot USING (source_sha256)
), elapsed AS (
    SELECT poutcome, pdays, count(*) FILTER (WHERE y = 'yes') AS numerator,
           count(*) AS denominator,
           100::numeric * count(*) FILTER (WHERE y = 'yes') / count(*) AS rate_pct
    FROM eligible WHERE pdays <> 999
    GROUP BY GROUPING SETS ((poutcome, pdays), (poutcome), (pdays), ())
), failure AS (
    SELECT *, pdays = 999 AS sentinel FROM eligible WHERE poutcome = 'failure'
), stratified AS (
    SELECT dimension, stratum,
           count(*) FILTER (WHERE NOT sentinel AND y = 'yes') AS elapsed_yes,
           count(*) FILTER (WHERE NOT sentinel) AS elapsed_n,
           count(*) FILTER (WHERE sentinel AND y = 'yes') AS sentinel_yes,
           count(*) FILTER (WHERE sentinel) AS sentinel_n
    FROM failure
    CROSS JOIN LATERAL (VALUES
        ('channel', CASE WHEN contact IN ('cellular', 'telephone') THEN contact END),
        ('month', month),
        ('frequency', CASE WHEN campaign BETWEEN 1 AND 3 THEN campaign::text
                           WHEN campaign >= 4 THEN '4+' END)
    ) AS strata(dimension, stratum)
    WHERE stratum IS NOT NULL
    GROUP BY dimension, stratum
), strata_rates AS (
    SELECT *, 100::numeric * elapsed_yes / NULLIF(elapsed_n, 0) AS elapsed_pct,
           100::numeric * sentinel_yes / NULLIF(sentinel_n, 0) AS sentinel_pct,
           least(elapsed_n, sentinel_n) < 10 AS sparse
    FROM stratified
), definitions(analysis, dimension, minimum_per_group) AS (
    VALUES ('month_standardized', 'month', 1),
           ('seven_month_sensitivity', 'month', 10),
           ('frequency_standardized', 'frequency', 1)
), weight_counts AS (
    SELECT analysis, stratum, minimum_per_group, elapsed_yes, elapsed_n, sentinel_yes, sentinel_n,
           elapsed_pct, sentinel_pct, sparse,
           least(elapsed_n, sentinel_n) >= minimum_per_group AS included,
           CASE WHEN least(elapsed_n, sentinel_n) >= minimum_per_group
                THEN elapsed_n + sentinel_n ELSE 0 END AS weight_numerator
    FROM definitions JOIN strata_rates USING (dimension)
), weights AS (
    SELECT *, sum(weight_numerator) OVER (PARTITION BY analysis) AS weight_denominator,
           weight_numerator::numeric /
               NULLIF(sum(weight_numerator) OVER (PARTITION BY analysis), 0) AS weight
    FROM weight_counts
), comparisons AS (
    SELECT analysis, count(*) FILTER (WHERE included) AS included_strata,
           sum(elapsed_yes) FILTER (WHERE included) AS elapsed_yes,
           sum(elapsed_n) FILTER (WHERE included) AS elapsed_n,
           sum(sentinel_yes) FILTER (WHERE included) AS sentinel_yes,
           sum(sentinel_n) FILTER (WHERE included) AS sentinel_n,
           sum(weight * elapsed_pct) FILTER (WHERE included) AS elapsed_pct,
           sum(weight * sentinel_pct) FILTER (WHERE included) AS sentinel_pct
    FROM weights GROUP BY analysis
)
SELECT jsonb_build_object(
    'source_sha256', (SELECT source_sha256 FROM snapshot),
    'baseline', (SELECT to_jsonb(baseline) FROM baseline),
    'channels', (SELECT jsonb_agg(to_jsonb(channels) ORDER BY contact) FROM channels),
    'channel_gap_pp', (SELECT max(rate_pct) FILTER (WHERE contact = 'cellular')
                            - max(rate_pct) FILTER (WHERE contact = 'telephone') FROM channels),
    'outcomes', (SELECT jsonb_agg(to_jsonb(outcomes) ORDER BY poutcome) FROM outcomes),
    'history', (SELECT jsonb_agg(to_jsonb(history) ORDER BY poutcome, pdays_sentinel,
                               recorded_prior_contacts) FROM history),
    'elapsed_days', (SELECT jsonb_agg(to_jsonb(elapsed) ORDER BY poutcome, pdays) FROM elapsed),
    'strata', (SELECT jsonb_agg(to_jsonb(s) || jsonb_build_object('gap_pp', elapsed_pct - sentinel_pct)
                               ORDER BY dimension, stratum) FROM strata_rates s),
    'weights', (SELECT jsonb_agg(to_jsonb(weights) ORDER BY analysis, stratum) FROM weights),
    'standardized', (SELECT jsonb_agg(to_jsonb(c) ||
                         jsonb_build_object('gap_pp', elapsed_pct - sentinel_pct) ORDER BY analysis)
                     FROM comparisons c)
) AS p003_findings;
COMMIT;
