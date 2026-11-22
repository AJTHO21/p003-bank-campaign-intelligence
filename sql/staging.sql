CREATE SCHEMA IF NOT EXISTS p003_bank_campaign;
REVOKE ALL ON SCHEMA p003_bank_campaign FROM PUBLIC;

CREATE TABLE IF NOT EXISTS p003_bank_campaign.source_snapshot (
    source_sha256 text PRIMARY KEY CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    manifest jsonb NOT NULL,
    source_rows integer NOT NULL CHECK (source_rows = 41188),
    loaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    loaded_by name NOT NULL DEFAULT current_user,
    load_elapsed interval NOT NULL
);

CREATE TABLE IF NOT EXISTS p003_bank_campaign.source_observation (
    source_sha256 text NOT NULL REFERENCES p003_bank_campaign.source_snapshot
        DEFERRABLE INITIALLY DEFERRED,
    source_row integer NOT NULL CHECK (source_row BETWEEN 1 AND 41188),
    age integer NOT NULL CHECK (age > 0),
    job text NOT NULL,
    marital text NOT NULL,
    education text NOT NULL,
    "default" text NOT NULL,
    housing text NOT NULL,
    loan text NOT NULL,
    contact text NOT NULL,
    month text NOT NULL,
    day_of_week text NOT NULL,
    duration integer NOT NULL CHECK (duration >= 0),
    campaign integer NOT NULL CHECK (campaign >= 1),
    pdays integer NOT NULL CHECK (pdays >= 0),
    previous integer NOT NULL CHECK (previous >= 0),
    poutcome text NOT NULL,
    "emp.var.rate" numeric NOT NULL,
    "cons.price.idx" numeric NOT NULL CHECK ("cons.price.idx" > 0),
    "cons.conf.idx" numeric NOT NULL,
    euribor3m numeric NOT NULL,
    "nr.employed" numeric NOT NULL CHECK ("nr.employed" > 0),
    y text NOT NULL CHECK (y IN ('yes', 'no')),
    PRIMARY KEY (source_sha256, source_row)
);

COMMENT ON COLUMN p003_bank_campaign.source_observation.source_row IS
    'One-based CSV record ordinal excluding the header. Identifies a released row within its snapshot.';

CREATE TABLE IF NOT EXISTS p003_bank_campaign.qa_run (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_sha256 text NOT NULL REFERENCES p003_bank_campaign.source_snapshot,
    checked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    checked_by name NOT NULL DEFAULT current_user,
    qa_elapsed interval NOT NULL,
    result jsonb NOT NULL
);

CREATE OR REPLACE FUNCTION p003_bank_campaign.reject_source_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'P003 source records are immutable';
END;
$$;

CREATE OR REPLACE FUNCTION p003_bank_campaign.reject_sealed_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM p003_bank_campaign.source_snapshot
               WHERE source_sha256 = NEW.source_sha256) THEN
        RAISE EXCEPTION 'P003 source snapshot is sealed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER source_observation_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON p003_bank_campaign.source_observation
FOR EACH STATEMENT EXECUTE FUNCTION p003_bank_campaign.reject_source_change();

CREATE OR REPLACE TRIGGER source_snapshot_immutable
BEFORE UPDATE OR DELETE OR TRUNCATE ON p003_bank_campaign.source_snapshot
FOR EACH STATEMENT EXECUTE FUNCTION p003_bank_campaign.reject_source_change();

CREATE OR REPLACE TRIGGER source_observation_sealed
BEFORE INSERT ON p003_bank_campaign.source_observation
FOR EACH ROW EXECUTE FUNCTION p003_bank_campaign.reject_sealed_insert();
