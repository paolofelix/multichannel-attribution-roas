-- Reporting layer: join ad spend to attributed revenue.
-- These views feed the model comparison (07) and any BI dashboard.

-- Campaign x model: spend, platform-reported results, and what each attribution model credits.
CREATE OR REPLACE VIEW attribution_demo.rpt_campaign_model AS
WITH spend AS (
  SELECT
    channel, campaign,
    SUM(spend)                AS spend,
    SUM(clicks)               AS clicks,
    SUM(platform_conversions) AS platform_conversions,
    SUM(platform_revenue)     AS platform_revenue
  FROM attribution_demo.stg_ad_performance
  GROUP BY channel, campaign
),
credit AS (
  SELECT model, campaign,
         SUM(credit)             AS attributed_conversions,
         SUM(attributed_revenue) AS attributed_revenue
  FROM attribution_demo.attribution_credits
  GROUP BY model, campaign
),
models AS (SELECT DISTINCT model FROM attribution_demo.attribution_credits)
SELECT
  m.model,
  s.channel,
  s.campaign,
  ROUND(s.spend, 2)                                         AS spend,
  s.clicks,
  ROUND(s.platform_conversions, 1)                          AS platform_conversions,
  ROUND(s.platform_revenue, 2)                              AS platform_revenue,
  ROUND(SAFE_DIVIDE(s.platform_revenue, s.spend), 2)        AS platform_roas,
  ROUND(COALESCE(c.attributed_conversions, 0), 2)           AS attributed_conversions,
  ROUND(COALESCE(c.attributed_revenue, 0), 2)               AS attributed_revenue,
  ROUND(SAFE_DIVIDE(c.attributed_revenue, s.spend), 3)      AS attributed_roas,
  ROUND(SAFE_DIVIDE(s.spend, SUM(s.spend) OVER (PARTITION BY m.model)), 4) AS share_of_spend,
  ROUND(SAFE_DIVIDE(COALESCE(c.attributed_revenue, 0),
        SUM(COALESCE(c.attributed_revenue, 0)) OVER (PARTITION BY m.model)), 4) AS share_of_credit
FROM models m
CROSS JOIN spend s
LEFT JOIN credit c
  ON c.model = m.model AND c.campaign = s.campaign;

-- Channel x model, with an efficiency index: share of credit / share of spend.
-- Index > 1 = the channel earns more credit than its share of budget (candidate to scale).
CREATE OR REPLACE VIEW attribution_demo.rpt_channel_model AS
SELECT
  model,
  channel,
  ROUND(SUM(spend), 2)                     AS spend,
  ROUND(SUM(platform_revenue), 2)          AS platform_revenue,
  ROUND(SAFE_DIVIDE(SUM(platform_revenue), SUM(spend)), 2) AS platform_roas,
  ROUND(SUM(attributed_conversions), 2)    AS attributed_conversions,
  ROUND(SUM(attributed_revenue), 2)        AS attributed_revenue,
  ROUND(SUM(share_of_spend), 4)            AS share_of_spend,
  ROUND(SUM(share_of_credit), 4)           AS share_of_credit,
  ROUND(SAFE_DIVIDE(SUM(share_of_credit), SUM(share_of_spend)), 2) AS efficiency_index
FROM attribution_demo.rpt_campaign_model
GROUP BY model, channel;
