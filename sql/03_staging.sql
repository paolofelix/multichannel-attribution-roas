-- Staging layer: clean and standardize the raw sources.
-- Uses the functions from 02_udfs.sql.

-- One row per date x channel x campaign, same column names and units for all 3 platforms.
CREATE OR REPLACE VIEW attribution_demo.stg_ad_performance AS
SELECT
  attribution_demo.to_date(day)                    AS date,
  'Google Ads'                                     AS channel,
  UPPER(TRIM(campaign))                            AS campaign,
  CAST(attribution_demo.to_num(impressions) AS INT64) AS impressions,
  CAST(attribution_demo.to_num(clicks) AS INT64)   AS clicks,
  attribution_demo.to_num(cost_micros) / 1000000   AS spend,          -- micros -> currency
  attribution_demo.to_num(conversions)             AS platform_conversions,
  attribution_demo.to_num(conv_value)              AS platform_revenue
FROM attribution_demo.raw_google_ads
WHERE TRIM(campaign) != ''

UNION ALL
SELECT
  attribution_demo.to_date(date_start),
  'Meta Ads',
  UPPER(TRIM(campaign_name)),                       -- fixes mixed case + trailing spaces
  CAST(attribution_demo.to_num(impressions) AS INT64),
  CAST(attribution_demo.to_num(link_clicks) AS INT64),
  attribution_demo.to_num(amount_spent),
  COALESCE(attribution_demo.to_num(purchases), 0),
  COALESCE(attribution_demo.to_num(purchase_value), 0)
FROM attribution_demo.raw_meta_ads
WHERE TRIM(campaign_name) != ''

UNION ALL
SELECT
  attribution_demo.to_date(time_period),            -- MM/DD/YYYY -> DATE
  'Microsoft Ads',
  UPPER(TRIM(campaign_name)),
  CAST(attribution_demo.to_num(impressions) AS INT64),
  CAST(attribution_demo.to_num(clicks) AS INT64),
  attribution_demo.to_num(spend),
  attribution_demo.to_num(conversions),
  attribution_demo.to_num(revenue)
FROM attribution_demo.raw_microsoft_ads
WHERE TRIM(campaign_name) != '';

-- Ad clicks per user. Maps the messy "source" labels to one channel name.
CREATE OR REPLACE VIEW attribution_demo.stg_touchpoints AS
SELECT
  TRIM(touch_id)                    AS touch_id,
  TRIM(user_id)                     AS user_id,
  attribution_demo.to_dt(touch_time) AS touch_time,
  CASE
    WHEN REGEXP_CONTAINS(LOWER(source), r'google')            THEN 'Google Ads'
    WHEN REGEXP_CONTAINS(LOWER(source), r'facebook|^fb|meta') THEN 'Meta Ads'
    WHEN REGEXP_CONTAINS(LOWER(source), r'bing|microsoft')    THEN 'Microsoft Ads'
    ELSE 'Other'
  END                               AS channel,
  UPPER(TRIM(campaign))             AS campaign,
  TRIM(click_id)                    AS click_id
FROM attribution_demo.raw_touchpoints
WHERE TRIM(touch_id) != '';

-- Orders with revenue.
CREATE OR REPLACE VIEW attribution_demo.stg_conversions AS
SELECT
  TRIM(order_id)                           AS order_id,
  TRIM(user_id)                            AS user_id,
  attribution_demo.to_dt(conversion_time)  AS conversion_time,
  attribution_demo.to_num(revenue)         AS revenue
FROM attribution_demo.raw_conversions
WHERE TRIM(order_id) != '';
