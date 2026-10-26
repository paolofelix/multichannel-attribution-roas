-- Step 0: create the dataset
CREATE SCHEMA IF NOT EXISTS attribution_demo OPTIONS (location = 'US');

-- Step 1: link each Google Sheet tab as an external table.
-- Replace YOUR_SHEET_ID with the ID from your Google Sheet URL before running.
-- All columns load as STRING; cleaning happens in 03_staging.sql.

CREATE OR REPLACE EXTERNAL TABLE attribution_demo.raw_google_ads (
  day STRING, campaign STRING, impressions STRING, clicks STRING,
  cost_micros STRING, conversions STRING, conv_value STRING
)
OPTIONS (format = 'GOOGLE_SHEETS', uris = ['https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID'],
  sheet_range = 'google_ads_raw!A:G', skip_leading_rows = 1);

CREATE OR REPLACE EXTERNAL TABLE attribution_demo.raw_meta_ads (
  date_start STRING, campaign_name STRING, impressions STRING, link_clicks STRING,
  amount_spent STRING, purchases STRING, purchase_value STRING
)
OPTIONS (format = 'GOOGLE_SHEETS', uris = ['https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID'],
  sheet_range = 'meta_ads_raw!A:G', skip_leading_rows = 1);

CREATE OR REPLACE EXTERNAL TABLE attribution_demo.raw_microsoft_ads (
  time_period STRING, campaign_name STRING, impressions STRING, clicks STRING,
  spend STRING, conversions STRING, revenue STRING
)
OPTIONS (format = 'GOOGLE_SHEETS', uris = ['https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID'],
  sheet_range = 'microsoft_ads_raw!A:G', skip_leading_rows = 1);

CREATE OR REPLACE EXTERNAL TABLE attribution_demo.raw_touchpoints (
  touch_id STRING, user_id STRING, touch_time STRING, source STRING,
  campaign STRING, click_id STRING
)
OPTIONS (format = 'GOOGLE_SHEETS', uris = ['https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID'],
  sheet_range = 'touchpoints!A:F', skip_leading_rows = 1);

CREATE OR REPLACE EXTERNAL TABLE attribution_demo.raw_conversions (
  order_id STRING, user_id STRING, conversion_time STRING, revenue STRING
)
OPTIONS (format = 'GOOGLE_SHEETS', uris = ['https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID'],
  sheet_range = 'conversions!A:D', skip_leading_rows = 1);
