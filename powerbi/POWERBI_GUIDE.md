# Power BI Setup

Same deal as the other two projects in this series -- Power BI Desktop
can't be scripted from here, so this is the model + measures to paste in,
not a finished .pbix.

## Get Data
Import from `data/raw/`: `dark_stores.csv`, `store_daily_metrics.csv`,
`sessions_sample.csv`. Skip `experiment_rollout.csv` -- `dark_stores.csv`
already has `treatment_group` and `rollout_date` merged in.

**First step in Power Query, before anything else:** filter
`store_daily_metrics` to `avg_delivery_time_min >= 0`. There's a ~0.4%
glitch in the raw data (see `docs/assumptions.md`) and every number below
assumes it's filtered out.

## Model
```
dark_stores (store_id) ─── 1:M ─── store_daily_metrics (store_id)
dark_stores (store_id) ─── 1:M ─── sessions_sample (store_id)
```
Add a Date table related to `store_daily_metrics[date]`.

## DAX Measures

```dax
Total Orders = SUM(store_daily_metrics[orders_placed])

Fulfillment Rate % =
DIVIDE(SUM(store_daily_metrics[orders_delivered]), SUM(store_daily_metrics[orders_placed]), 0) * 100

Avg Delivery Time (min) = AVERAGE(store_daily_metrics[avg_delivery_time_min])

On-Time Rate % = AVERAGE(store_daily_metrics[pct_on_time_15min])

Stockout Cancel Rate % =
DIVIDE(SUM(store_daily_metrics[orders_cancelled_stockout]), SUM(store_daily_metrics[orders_placed]), 0) * 100

Total GTV = SUM(store_daily_metrics[gtv_inr])

-- funnel
Session Count = COUNTROWS(sessions_sample)
Order Rate % = DIVIDE(CALCULATE(COUNTROWS(sessions_sample), sessions_sample[order_outcome] = "ORDER_PLACED"), [Session Count], 0) * 100

-- DiD building blocks (build the actual regression in Python -- these are
-- just for a quick pre/post treated/control card view)
Avg Delivery Time (Treated, Post) =
CALCULATE([Avg Delivery Time (min)], dark_stores[treatment_group] = "treated", store_daily_metrics[date] >= DATE(2026,4,1))

Avg Delivery Time (Control, Post) =
CALCULATE([Avg Delivery Time (min)], dark_stores[treatment_group] = "control", store_daily_metrics[date] >= DATE(2026,4,1))
```

## Pages
1. **Ops Overview** — KPI cards (Fulfillment Rate, On-Time Rate, Total GTV) + daily trend line
2. **Funnel** — funnel visual on `sessions_sample`, plus a pie/donut on `order_outcome` filtered to `reached_checkout = TRUE` (this is where the stockout number lives)
3. **Store Performance** — table of `store_performance_tiers.csv` (import this processed file directly, easiest way to reproduce the Python tiering without re-deriving z-scores in DAX) with conditional formatting on tier
4. **Routing Experiment** — line chart of avg delivery time by week, split by `treatment_group`, with a reference line at April 1. Import `data/processed/diff_in_diff_results.csv` for the headline coefficient/p-value as a card.

## Note on the .pbix
As with the other projects: build it in Power BI Desktop against these
CSVs, then drop the `.pbix` in this folder and add a couple of screenshots
to the main README before pushing.
