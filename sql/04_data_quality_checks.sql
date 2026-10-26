-- Data quality check after staging.
-- Expected: ad_performance 180 rows, touchpoints 211, conversions 50,
-- and every "bad_" column = 0.

SELECT 'ad_performance' AS source, COUNT(*) AS row_count,
       COUNTIF(date IS NULL) AS bad_dates, COUNTIF(spend IS NULL) AS bad_numbers
FROM attribution_demo.stg_ad_performance
UNION ALL
SELECT 'touchpoints', COUNT(*), COUNTIF(touch_time IS NULL), COUNTIF(channel = 'Other')
FROM attribution_demo.stg_touchpoints
UNION ALL
SELECT 'conversions', COUNT(*), COUNTIF(conversion_time IS NULL), COUNTIF(revenue IS NULL)
FROM attribution_demo.stg_conversions;
