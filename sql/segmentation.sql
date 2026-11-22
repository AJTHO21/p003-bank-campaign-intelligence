BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH snapshot AS (
    SELECT '74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8'::text AS source_sha256
), baseline AS (
    SELECT numerator, denominator, subscription_rate
    FROM p003_bank_campaign.subscription_overall JOIN snapshot USING (source_sha256)
), eligible AS (
    SELECT job, education, age, housing, loan, contact, month, day_of_week, poutcome, y
    FROM p003_bank_campaign.source_observation JOIN snapshot USING (source_sha256)
    WHERE y IN ('yes', 'no')
), segments AS (
    SELECT dimension, level, poutcome, month, y
    FROM eligible
    CROSS JOIN LATERAL (VALUES
        ('job', job), ('education', education),
        ('age_band', CASE WHEN age < 30 THEN 'Under 30' WHEN age < 40 THEN '30–39'
                          WHEN age < 50 THEN '40–49' WHEN age < 60 THEN '50–59'
                          ELSE '60+' END),
        ('housing', housing), ('loan', loan),
        ('contact', CASE WHEN contact IN ('cellular', 'telephone') THEN contact END),
        ('month', month), ('day_of_week', day_of_week)
    ) segment(dimension, level)
    WHERE level IS NOT NULL
), margins AS (
    SELECT dimension, level, count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator
    FROM segments GROUP BY dimension, level
), prior AS (
    SELECT poutcome, numerator, denominator, subscription_rate
    FROM p003_bank_campaign.subscription_by_prior_outcome JOIN snapshot USING (source_sha256)
), cross_counts AS (
    SELECT dimension, level, 'prior_outcome'::text AS stratum_type, poutcome AS stratum,
           count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator
    FROM segments WHERE dimension IN ('contact', 'job', 'education', 'age_band', 'housing', 'loan')
    GROUP BY dimension, level, poutcome
    UNION ALL
    SELECT dimension, level, 'contact_month', month,
           count(*) FILTER (WHERE y = 'yes'), count(*)
    FROM segments WHERE dimension = 'contact' GROUP BY dimension, level, month
), cross_grid AS (
    SELECT dimension, level, 'prior_outcome'::text AS stratum_type, poutcome AS stratum,
           prior.subscription_rate AS reference_rate
    FROM margins CROSS JOIN prior
    WHERE dimension IN ('contact', 'job', 'education', 'age_band', 'housing', 'loan')
    UNION ALL
    SELECT 'contact', channel.level, 'contact_month', month.level,
           month.numerator::numeric / month.denominator
    FROM margins channel CROSS JOIN margins month
    WHERE channel.dimension = 'contact' AND month.dimension = 'month'
), counts AS (
    SELECT dimension, level, 'overall'::text AS stratum_type, NULL::text AS stratum,
           numerator, denominator, subscription_rate AS reference_rate
    FROM margins CROSS JOIN (SELECT subscription_rate FROM baseline) base
    UNION ALL
    SELECT dimension, level, stratum_type, stratum,
           coalesce(numerator, 0), coalesce(denominator, 0), reference_rate
    FROM cross_grid LEFT JOIN cross_counts USING (dimension, level, stratum_type, stratum)
), rates AS (
    SELECT *, numerator::numeric / NULLIF(denominator, 0) AS rate,
           denominator < 50 OR least(numerator, denominator - numerator) < 5 AS sparse
    FROM counts
), intervals AS (
    SELECT *, (rate + 1.96^2 / (2 * NULLIF(denominator, 0))) /
                  (1 + 1.96^2 / NULLIF(denominator, 0)) AS center,
           1.96 * sqrt((rate * (1 - rate) + 1.96^2 / (4 * NULLIF(denominator, 0))) /
                       NULLIF(denominator, 0)) / (1 + 1.96^2 / NULLIF(denominator, 0)) AS radius
    FROM rates
), scored AS (
    SELECT dimension, level, stratum_type, stratum, numerator, denominator, sparse,
           100 * rate AS rate_pct, 100 * reference_rate AS reference_pct,
           100 * (rate - reference_rate) AS gap_pp,
           CASE WHEN denominator > 0 THEN 100 * greatest(0, center - radius) END AS wilson_low_pct,
           CASE WHEN denominator > 0 THEN 100 * least(1, center + radius) END AS wilson_high_pct
    FROM intervals
), channel_pairs AS (
    SELECT c.stratum_type, c.stratum, c.numerator AS cellular_yes, c.denominator AS cellular_n,
           t.numerator AS telephone_yes, t.denominator AS telephone_n,
           c.rate_pct AS cellular_pct, t.rate_pct AS telephone_pct,
           c.rate_pct - t.rate_pct AS gap_pp, NOT (c.sparse OR t.sparse) AS included
    FROM scored c JOIN scored t USING (dimension, stratum_type, stratum)
    WHERE c.dimension = 'contact' AND c.level = 'cellular' AND t.level = 'telephone'
), channel_counts AS (
    SELECT *, CASE WHEN included THEN cellular_n + telephone_n ELSE 0 END AS weight_numerator
    FROM channel_pairs
), channel_weights AS (
    SELECT *, sum(weight_numerator) OVER (PARTITION BY stratum_type) AS weight_denominator,
           weight_numerator / NULLIF(sum(weight_numerator) OVER (PARTITION BY stratum_type), 0) AS weight
    FROM channel_counts
), channel_adjusted AS (
    SELECT stratum_type, count(*) FILTER (WHERE included) AS included_strata,
           sum(cellular_yes) FILTER (WHERE included) AS cellular_yes,
           sum(cellular_n) FILTER (WHERE included) AS cellular_n,
           sum(telephone_yes) FILTER (WHERE included) AS telephone_yes,
           sum(telephone_n) FILTER (WHERE included) AS telephone_n,
           sum(weight * cellular_pct) FILTER (WHERE included) AS cellular_pct,
           sum(weight * telephone_pct) FILTER (WHERE included) AS telephone_pct,
           sum(weight * gap_pp) FILTER (WHERE included) AS gap_pp
    FROM channel_weights GROUP BY stratum_type
), segment_adjusted AS (
    SELECT dimension, level, count(*) FILTER (WHERE sparse) AS sparse_strata,
           CASE WHEN NOT bool_or(sparse)
                THEN sum(rate_pct * prior.denominator / baseline.denominator) END AS adjusted_pct
    FROM scored JOIN prior ON stratum = poutcome CROSS JOIN baseline
    WHERE stratum_type = 'prior_outcome' AND dimension <> 'contact'
    GROUP BY dimension, level
)
SELECT jsonb_build_object(
    'source_sha256', (SELECT source_sha256 FROM snapshot),
    'baseline', (SELECT to_jsonb(baseline) FROM baseline),
    'minimums', jsonb_build_object('observations', 50, 'per_outcome', 5),
    'cells', (SELECT jsonb_agg(to_jsonb(scored) ORDER BY dimension, level, stratum_type, stratum)
              FROM scored),
    'channel_weights', (SELECT jsonb_agg(to_jsonb(channel_weights) ORDER BY stratum_type, stratum)
                        FROM channel_weights),
    'channel_adjusted', (SELECT jsonb_agg(to_jsonb(channel_adjusted) ORDER BY stratum_type)
                         FROM channel_adjusted),
    'segment_weights', (SELECT jsonb_agg(jsonb_build_object(
        'prior_outcome', poutcome, 'weight_numerator', prior.denominator,
        'weight_denominator', baseline.denominator,
        'weight', prior.denominator::numeric / baseline.denominator) ORDER BY poutcome)
        FROM prior CROSS JOIN baseline),
    'segment_adjusted', (SELECT jsonb_agg(to_jsonb(s) ||
        jsonb_build_object('gap_pp', adjusted_pct - 100 * subscription_rate) ORDER BY dimension, level)
        FROM segment_adjusted s CROSS JOIN baseline)
) AS p003_segmentation;
COMMIT;
