-- funnel.sql
-- session -> order funnel + checkout failure split, matches scripts/02_demand_funnel.py

SELECT
  'Session Started' AS stage, 1 AS stage_order, COUNT(*) AS sessions
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
UNION ALL
SELECT 'Reached Browse', 2, COUNTIF(reached_browse)
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
UNION ALL
SELECT 'Added to Cart', 3, COUNTIF(reached_add_to_cart)
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
UNION ALL
SELECT 'Reached Checkout', 4, COUNTIF(reached_checkout)
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
UNION ALL
SELECT 'Order Placed', 5, COUNTIF(order_outcome = 'ORDER_PLACED')
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
ORDER BY stage_order;

-- checkout failure breakdown -- the stockout number is the one to watch
SELECT
  order_outcome,
  COUNT(*) AS n,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 1) AS pct_of_checkouts_reached
FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample`
WHERE reached_checkout
GROUP BY order_outcome
ORDER BY n DESC;
