-- Attribution models: one row per order x touchpoint x model,
-- with the share of credit that touch receives.
--
-- Lookback window: 30 days before the order.
-- Models:
--   1. Last click  - 100% credit to the final touch before purchase
--   2. Linear      - equal credit to every touch in the path
--   3. Time decay  - weight = 0.5 ^ (days before conversion / 7), normalized per order
--                    (7-day half-life: a touch 7 days earlier gets half the weight)

CREATE OR REPLACE TABLE attribution_demo.attribution_credits AS
WITH paths AS (
  SELECT
    c.order_id, c.user_id, c.conversion_time, c.revenue,
    t.touch_id, t.touch_time, t.channel, t.campaign,
    DATETIME_DIFF(c.conversion_time, t.touch_time, MINUTE) / 1440.0 AS days_before_conversion
  FROM attribution_demo.stg_conversions c
  JOIN attribution_demo.stg_touchpoints t
    ON  t.user_id = c.user_id
    AND t.touch_time <= c.conversion_time
    AND t.touch_time >= DATETIME_SUB(c.conversion_time, INTERVAL 30 DAY)
),
scored AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY touch_time DESC, touch_id DESC) AS touch_rank_from_last,
    COUNT(*)     OVER (PARTITION BY order_id)                                         AS path_length,
    POW(0.5, days_before_conversion / 7)                                              AS decay_weight
  FROM paths
),
credits AS (
  SELECT
    *,
    IF(touch_rank_from_last = 1, 1.0, 0.0)                         AS last_click_credit,
    1.0 / path_length                                              AS linear_credit,
    decay_weight / SUM(decay_weight) OVER (PARTITION BY order_id)  AS time_decay_credit
  FROM scored
)
SELECT
  order_id, user_id, conversion_time, revenue,
  touch_id, touch_time, channel, campaign,
  path_length, ROUND(days_before_conversion, 2) AS days_before_conversion,
  m.model,
  m.credit,
  m.credit * revenue AS attributed_revenue
FROM credits,
UNNEST([
  STRUCT('1. Last click' AS model, last_click_credit AS credit),
  STRUCT('2. Linear',              linear_credit),
  STRUCT('3. Time decay (7d)',     time_decay_credit)
]) AS m;

-- Sanity check: each model should credit exactly 50 orders and the same total revenue.
-- SELECT model, ROUND(SUM(credit), 2) AS total_credit, ROUND(SUM(attributed_revenue), 2) AS total_revenue
-- FROM attribution_demo.attribution_credits GROUP BY model ORDER BY model;
