-- Dementia Atlas - gold schema for PostGIS.
-- Applied by pipeline/src/load_postgis.py before each load; idempotent.
-- Tables mirror the Parquet files under pipeline/data/processed/gold/.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS gold;

DROP TABLE IF EXISTS gold.observation, gold.diagnosis_rate, gold.geometry, gold.series_break,
                     gold.period, gold.measure, gold.organisation CASCADE;

CREATE TABLE gold.organisation (
    org_level          text NOT NULL,   -- country | nhs_region | icb | sub_icb | practice | gor | utla | ltla
    org_code           text NOT NULL,   -- ODS code for NHS levels, ONS code for local-government levels
    ons_code           text,
    name               text,
    parent_org_level   text,
    parent_org_code    text,
    first_period       date NOT NULL,
    last_period        date NOT NULL,
    is_current         boolean NOT NULL,
    series_break_from  text,            -- YYYY-MM from which the series is not comparable with its past
    PRIMARY KEY (org_level, org_code)
);

CREATE TABLE gold.measure (
    measure_key        text PRIMARY KEY,   -- MEASURE:BREAKDOWN[:dim=value...]
    measure            text NOT NULL,
    breakdown          text NOT NULL,
    age                text NOT NULL,
    gender             text NOT NULL,
    ethnicity          text NOT NULL,
    dementia_type      text NOT NULL,
    residential_type   text NOT NULL,
    description        text,
    unit               text NOT NULL,      -- count | estimate | percent
    is_additive        boolean NOT NULL,
    comparability      text NOT NULL       -- comparable | labels_only | not_comparable | era_a_only | era_b_only
);

CREATE TABLE gold.period (
    period_end         date PRIMARY KEY,
    period             text NOT NULL,      -- YYYY-MM
    publication_era    text NOT NULL,      -- A | B
    source_release     text NOT NULL,
    dictionary_version text NOT NULL,
    n_rows             bigint NOT NULL
);

CREATE TABLE gold.observation (
    period_end         date NOT NULL REFERENCES gold.period (period_end),
    org_level          text NOT NULL,
    org_code           text NOT NULL,
    measure_key        text NOT NULL REFERENCES gold.measure (measure_key),
    value              double precision,   -- NULL when suppressed or blank
    value_state        text NOT NULL,      -- numeric | suppressed | blank | not_applicable | minimum
    value_lower        double precision,   -- exact bounds; equal to value when numeric
    value_upper        double precision,
    is_derived         boolean NOT NULL,   -- computed by the pipeline, not published
    dq_flag            boolean NOT NULL,
    comparability      text NOT NULL,
    source_release     text NOT NULL,
    PRIMARY KEY (period_end, org_level, org_code, measure_key),
    FOREIGN KEY (org_level, org_code) REFERENCES gold.organisation (org_level, org_code)
);
CREATE INDEX observation_org_idx ON gold.observation (org_level, org_code, measure_key, period_end);
CREATE INDEX observation_measure_period_idx ON gold.observation (measure_key, period_end, org_level);

CREATE TABLE gold.diagnosis_rate (
    period_end         date NOT NULL REFERENCES gold.period (period_end),
    org_level          text NOT NULL,
    org_code           text NOT NULL,
    register_65_plus   double precision,
    estimate_65_plus   double precision,
    diag_rate          double precision,   -- percent
    diag_rate_ll       double precision,
    diag_rate_ul       double precision,
    dq_flag            boolean NOT NULL,   -- denominator smaller than the CFAS II reference population
    PRIMARY KEY (period_end, org_level, org_code),
    FOREIGN KEY (org_level, org_code) REFERENCES gold.organisation (org_level, org_code)
);
CREATE INDEX diagnosis_rate_level_period_idx ON gold.diagnosis_rate (org_level, period_end);

CREATE TABLE gold.series_break (
    scope              text NOT NULL,      -- org | measure
    org_level          text,
    org_code           text,
    measure            text,
    breakdown          text,
    effective_from     text NOT NULL,      -- YYYY-MM
    kind               text NOT NULL,
    note               text,
    source             text
);
CREATE INDEX series_break_org_idx ON gold.series_break (org_level, org_code);
CREATE INDEX series_break_measure_idx ON gold.series_break (measure, breakdown);

CREATE TABLE gold.geometry (
    org_level              text NOT NULL,
    org_code               text,           -- NULL if the boundary file has a Sub-ICB silver has never seen
    ons_code               text NOT NULL,
    name_in_boundary_file  text,
    boundary_version       text NOT NULL,  -- YYYY-MM of the boundary set
    geometry_geojson       text NOT NULL,
    geom                   geometry(MultiPolygon, 4326),
    PRIMARY KEY (org_level, ons_code, boundary_version)
);
CREATE INDEX geometry_geom_idx ON gold.geometry USING gist (geom);
