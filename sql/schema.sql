-- schema.sql
-- BigQuery Standard SQL. Same "swap the project ID" pattern as the other
-- two portfolio projects.

CREATE SCHEMA IF NOT EXISTS `YOUR_GCP_PROJECT_ID.quickdash_analytics`;

CREATE OR REPLACE TABLE `YOUR_GCP_PROJECT_ID.quickdash_analytics.dark_stores` (
  store_id       STRING NOT NULL,
  city           STRING NOT NULL,
  city_tier      STRING NOT NULL,
  zone           STRING NOT NULL,
  launch_date    DATE,
  sq_ft          INT64,
  sku_count      INT64,
  staff_count    INT64,
  catchment_km   FLOAT64,
  treatment_group STRING,   -- treated | control
  rollout_date    DATE      -- null for control stores
);

CREATE OR REPLACE TABLE `YOUR_GCP_PROJECT_ID.quickdash_analytics.store_daily_metrics` (
  date                       DATE NOT NULL,
  store_id                   STRING NOT NULL,
  city                       STRING,
  city_tier                  STRING,
  treatment_group            STRING,
  orders_placed              INT64,
  orders_delivered           INT64,
  orders_cancelled_stockout  INT64,
  orders_cancelled_other     INT64,
  avg_delivery_time_min      FLOAT64,   -- a handful of rows are negative, see note below
  pct_on_time_15min          FLOAT64,
  gtv_inr                    NUMERIC
);
-- Note: ~0.4% of rows have a negative avg_delivery_time_min, traced to a
-- clock-sync glitch on a subset of stores in February. Filter these out with
-- `WHERE avg_delivery_time_min >= 0` -- every query below already does this.

CREATE OR REPLACE TABLE `YOUR_GCP_PROJECT_ID.quickdash_analytics.sessions_sample` (
  session_id            INT64 NOT NULL,
  session_date          DATE NOT NULL,
  store_id              STRING NOT NULL,
  city_tier             STRING,
  device_os             STRING,
  reached_browse        BOOL,
  reached_add_to_cart   BOOL,
  reached_checkout      BOOL,
  order_outcome         STRING  -- ORDER_PLACED | CHECKOUT_FAILED_STOCKOUT |
                                 -- CHECKOUT_FAILED_OTHER | ABANDONED_NO_CHECKOUT
);

-- bq load --source_format=CSV --skip_leading_rows=1 YOUR_GCP_PROJECT_ID:quickdash_analytics.dark_stores data/raw/dark_stores.csv
-- bq load --source_format=CSV --skip_leading_rows=1 YOUR_GCP_PROJECT_ID:quickdash_analytics.store_daily_metrics data/raw/store_daily_metrics.csv
-- bq load --source_format=CSV --skip_leading_rows=1 YOUR_GCP_PROJECT_ID:quickdash_analytics.sessions_sample data/raw/sessions_sample.csv
