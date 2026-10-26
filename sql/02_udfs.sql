-- Reusable cleaning functions used by the staging views (03_staging.sql).

-- Text -> number. Strips spaces, thousands separators and currency symbols.
CREATE OR REPLACE FUNCTION attribution_demo.to_num(s STRING) AS (
  SAFE_CAST(REGEXP_REPLACE(TRIM(s), r'[,$₱\s]', '') AS FLOAT64)
);

-- Text -> DATE. Accepts 2026-07-01, 07/01/2026 and 7/1/2026.
CREATE OR REPLACE FUNCTION attribution_demo.to_date(s STRING) AS (
  COALESCE(
    SAFE.PARSE_DATE('%Y-%m-%d', TRIM(s)),
    SAFE.PARSE_DATE('%m/%d/%Y', TRIM(s))
  )
);

-- Text -> DATETIME. Accepts ISO and US formats, with or without seconds / AM-PM.
CREATE OR REPLACE FUNCTION attribution_demo.to_dt(s STRING) AS (
  COALESCE(
    SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S', TRIM(s)),
    SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M', TRIM(s)),
    SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S', TRIM(s)),
    SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M', TRIM(s)),
    SAFE.PARSE_DATETIME('%m/%d/%Y %I:%M:%S %p', TRIM(s))
  )
);
