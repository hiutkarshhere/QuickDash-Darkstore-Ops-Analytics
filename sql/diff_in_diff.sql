-- diff_in_diff.sql
-- The 2x2 DiD table in pure SQL. The regression version (with clustered SEs
-- and city-tier/day-of-week controls) is done in Python -- statsmodels, not
-- BigQuery ML, since a clustered-SE OLS isn't something BQML exposes
-- cleanly. This query is the sanity-check table you'd run first, before
-- ever opening Python, to see if there's something worth modeling properly.

WITH clean_panel AS (
  SELECT
    *,
    IF(date >= DATE('2026-04-01'), 1, 0) AS post,
    IF(treatment_group = 'treated', 1, 0) AS treated
  FROM `YOUR_GCP_PROJECT_ID.quickdash_analytics.store_daily_metrics`
  WHERE avg_delivery_time_min >= 0
)
SELECT
  treated,
  post,
  ROUND(AVG(avg_delivery_time_min), 2) AS avg_delivery_time_min,
  ROUND(AVG(pct_on_time_15min), 2) AS avg_on_time_pct,
  COUNT(*) AS store_days
FROM clean_panel
GROUP BY treated, post
ORDER BY treated, post;

-- quick manual DiD from the four cells above:
-- DiD = (treated_post - treated_pre) - (control_post - control_pre)
