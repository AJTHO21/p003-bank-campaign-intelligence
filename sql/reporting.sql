-- Descriptive reporting uses released observations and their observed outcomes.
CREATE OR REPLACE VIEW p003_bank_campaign.subscription_overall AS
SELECT source_sha256, count(*) FILTER (WHERE y = 'yes') AS numerator,
       count(*) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric / NULLIF(count(*), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
WHERE y IN ('yes', 'no')
GROUP BY source_sha256;

CREATE OR REPLACE VIEW p003_bank_campaign.subscription_by_segment AS
SELECT source_sha256, segment.field, segment.level,
       count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric / NULLIF(count(*), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
CROSS JOIN LATERAL (VALUES ('age', age::text), ('job', job), ('marital', marital),
    ('education', education), ('default', "default"), ('housing', housing), ('loan', loan))
    AS segment(field, level)
WHERE y IN ('yes', 'no')
GROUP BY source_sha256, segment.field, segment.level;

CREATE OR REPLACE VIEW p003_bank_campaign.subscription_by_channel AS
SELECT source_sha256, contact,
       count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric / NULLIF(count(*), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
WHERE y IN ('yes', 'no') AND contact IN ('cellular', 'telephone')
GROUP BY source_sha256, contact;

CREATE OR REPLACE VIEW p003_bank_campaign.subscription_by_prior_outcome AS
SELECT source_sha256, poutcome,
       count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric / NULLIF(count(*), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
WHERE y IN ('yes', 'no')
GROUP BY source_sha256, poutcome;

CREATE OR REPLACE VIEW p003_bank_campaign.campaign_frequency AS
SELECT source_sha256, campaign,
       count(*) AS frequency_numerator,
       sum(count(*)) OVER (PARTITION BY source_sha256) AS frequency_denominator,
       count(*)::numeric / NULLIF(sum(count(*)) OVER (PARTITION BY source_sha256), 0)
           AS observation_share,
       count(*) FILTER (WHERE y = 'yes') AS numerator,
       count(*) FILTER (WHERE y IN ('yes', 'no')) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric /
           NULLIF(count(*) FILTER (WHERE y IN ('yes', 'no')), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
WHERE campaign >= 1
GROUP BY source_sha256, campaign;

CREATE OR REPLACE VIEW p003_bank_campaign.prior_contact_history AS
SELECT source_sha256, previous > 0 AS recorded_prior_contacts, poutcome,
       pdays = 999 AS pdays_sentinel,
       pdays = 999 AND previous > 0 AS history_disagreement,
       count(*) FILTER (WHERE y = 'yes') AS numerator, count(*) AS denominator,
       count(*) FILTER (WHERE y = 'yes')::numeric / NULLIF(count(*), 0) AS subscription_rate
FROM p003_bank_campaign.source_observation
WHERE y IN ('yes', 'no')
GROUP BY source_sha256, previous > 0, poutcome, pdays = 999, pdays = 999 AND previous > 0;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p003_bank_reporter') THEN
        CREATE ROLE p003_bank_reporter NOLOGIN;
    ELSIF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'p003_bank_reporter'
                  AND (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls
                       OR rolreplication)) THEN
        RAISE EXCEPTION 'Existing p003_bank_reporter is not the expected read-only group role';
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA p003_bank_campaign TO p003_bank_reporter;
GRANT SELECT ON p003_bank_campaign.subscription_overall,
    p003_bank_campaign.subscription_by_segment, p003_bank_campaign.subscription_by_channel,
    p003_bank_campaign.subscription_by_prior_outcome, p003_bank_campaign.campaign_frequency,
    p003_bank_campaign.prior_contact_history TO p003_bank_reporter;

REVOKE ALL ON p003_bank_campaign.source_observation, p003_bank_campaign.source_snapshot,
    p003_bank_campaign.qa_run FROM PUBLIC, p003_bank_reporter;
