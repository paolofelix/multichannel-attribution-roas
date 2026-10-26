-- Side-by-side comparison of the three attribution models by channel.
-- Efficiency index = share of attributed revenue / share of spend.
-- Above 1.0 = the channel earns more credit than its share of budget.

SELECT
  channel,
  MAX(spend) AS spend,
  ROUND(SUM(IF(model = '1. Last click', attributed_revenue, 0)), 2)      AS last_click_revenue,
  ROUND(SUM(IF(model = '2. Linear', attributed_revenue, 0)), 2)          AS linear_revenue,
  ROUND(SUM(IF(model = '3. Time decay (7d)', attributed_revenue, 0)), 2) AS time_decay_revenue,
  ROUND(SUM(IF(model = '1. Last click', efficiency_index, 0)), 2)        AS last_click_index,
  ROUND(SUM(IF(model = '2. Linear', efficiency_index, 0)), 2)            AS linear_index,
  ROUND(SUM(IF(model = '3. Time decay (7d)', efficiency_index, 0)), 2)   AS time_decay_index
FROM attribution_demo.rpt_channel_model
GROUP BY channel
ORDER BY spend DESC;
