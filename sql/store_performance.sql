-- store_performance.sql
-- Per-store rollup + tiering, matches scripts/03_store_performance_tiering.py
-- (Python version uses z-scored composite; this uses NTILE on fulfillment
-- rate alone as a simpler SQL-native approximation -- close enough for a
-- quick "who's struggling" check without pulling the data out.)

WITH clean_panel AS (
  SELECT *
  FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.store_daily_metrics`
  WHERE avg_delivery_time_min >= 0   -- drop the clock-sync glitch rows
),
store_rollup AS (
  SELECT
    store_id,
    ANY_VALUE(city) AS city,
    SUM(orders_placed) AS total_orders,
    SUM(orders_delivered) AS total_delivered,
    SUM(gtv_inr) AS total_gtv,
    ROUND(AVG(avg_delivery_time_min), 2) AS avg_delivery_time,
    ROUND(AVG(pct_on_time_15min), 2) AS avg_on_time_pct,
    ROUND(SUM(orders_cancelled_stockout) / SUM(orders_placed) * 100, 2) AS stockout_cancel_rate_pct
  FROM clean_panel
  GROUP BY store_id
),
scored AS (
  SELECT
    *,
    ROUND(total_delivered / total_orders * 100, 2) AS fulfillment_rate_pct,
    NTILE(3) OVER (ORDER BY total_delivered / total_orders) AS tier_num
  FROM store_rollup
)
SELECT
  store_id, city, fulfillment_rate_pct, avg_on_time_pct, stockout_cancel_rate_pct,
  CASE tier_num WHEN 1 THEN 'Bottom Third' WHEN 2 THEN 'Mid Third' ELSE 'Top Third' END AS tier
FROM scored
ORDER BY fulfillment_rate_pct DESC;
