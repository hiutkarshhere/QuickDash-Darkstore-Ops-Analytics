# Assumptions Behind the Data

Same reasoning as the other two projects in this series: there's no public
dataset with dark-store-level operational data (delivery times, fulfillment
rates, a routing-algorithm rollout) at the granularity needed for this kind
of analysis, so this is a simulation with documented, defensible parameters
rather than a proxy dataset wearing a q-commerce label. Below is what's
baked in and why.

## Footprint
- 60 dark stores across 10 Indian cities (6 Tier 1, 4 Tier 2), weighted
  roughly by real metro population/order-density differences
- Jan 1 – Jun 30, 2026, full daily panel (10,860 store-days)
- ~1.9M total orders across the panel; a 85,000-session *sample* for the
  funnel work (see note below on why sessions are sampled but the panel isn't)

## Why sessions are a sample and the panel isn't
Full session volume across 6 months for 60 stores would run into the tens
of millions of rows -- more than needed to characterize a conversion funnel
reliably, and not something worth the storage/runtime cost for a portfolio
project. `store_daily_metrics.csv` stays full-population because anything
volume-sensitive (GTV, total orders, fulfillment rate) needs to actually
reflect total volume, not a sample. This split -- full population for
aggregate metrics, sampled event-level data for funnel/behavioral work -- is
the same tradeoff most companies make internally, since raw event logs are
usually too large to query directly for exploratory work.

## Store Baseline Performance
Each store gets a random baseline delivery time (~N(16.3, 1.6) minutes) and
volume multiplier, representing real store-to-store variation in staffing,
layout, and manager quality that isn't otherwise modeled. Tier 1 stores get
a higher base order volume (165/day) than Tier 2 (95/day), consistent with
population density differences.

**Why the average delivery time (16.3 min) is above the 15-min SLA:** this
isn't a mistake -- it's the whole premise of the project. QuickDash is a
company where the median store is *missing* its delivery promise, which is
exactly the kind of problem that justifies testing and shipping a new
routing/batching engine. A dataset where everything already hits target
wouldn't need this analysis to exist.

## Common Trends (apply to every store, treated or not)
- Category growth: gentle upward drift in order volume across the window
- Friday/Saturday order bump (+18%)
- A monsoon-season delivery time hit in June (roads, riders slow down) —
  this matters for the DiD design specifically: it's a shock that hits
  *both* treated and control stores, so a naive before/after comparison on
  treated stores alone would understate the routing engine's benefit (it'd
  look like delivery times crept back up in June, when really they'd have
  gone up more without the fix). This is the actual reason to use
  diff-in-diff instead of a simple pre/post comparison.

## The Routing Engine Rollout (the natural experiment)
- Rolled out April 1, 2026 to stores in Bengaluru, Mumbai, and Delhi NCR
  (22 stores) — **not randomized**. Product/eng picked these cities first
  because that's where the batching problem was reportedly worst (biggest,
  densest metro clusters). Everywhere else (38 stores) stayed on the old
  system through the observation window.
- Planted treatment effect: -1.75 min average delivery time, applied from
  the rollout date onward, only to treated stores.
- Because this wasn't randomized, a straight treated-vs-control comparison
  risks confounding city effects with treatment effects. The diff-in-diff
  design (`scripts/04_diffindiff_routing_experiment.py`) explicitly checks
  pre-period trends between the two groups before trusting the estimate —
  see the README for that check.

## The Deliberate Data Glitch
`store_daily_metrics.csv` has 40 rows (out of 10,860, ~0.4%) with a
negative `avg_delivery_time_min`, concentrated in a subset of stores in
February. This simulates a real category of data-quality issue (a
logging/clock-sync bug on some store devices) — not a designed feature of
the business, just messy source data. It's caught and dropped in
`scripts/03_store_performance_tiering.py` and
`scripts/04_diffindiff_routing_experiment.py`, with the row count and
affected stores printed to console rather than silently discarded. Every
SQL query in `sql/` filters it out too.

## Checkout Failure Split (funnel)
Of sessions reaching checkout, ~9% fail specifically because an item in the
cart goes out of stock at the moment of checkout, vs. ~4% for other reasons
(payment declines etc). This is a real q-commerce-specific failure mode —
inventory turns fast enough in a dark store that "in stock when you added
it, gone by checkout" is a genuine, common failure path, unlike a
warehouse-fulfilled e-commerce model where this is rare.

## What This Doesn't Claim
None of these numbers are real QuickDash/Zepto/Blinkit/Instamart figures —
QuickDash isn't a real company. This is a transparent simulation built to
demonstrate the analytical workflow (operational KPI design, funnel
analysis with a domain-specific failure mode, and causal inference on a
non-randomized rollout) the way it'd actually be done against a live
warehouse.
