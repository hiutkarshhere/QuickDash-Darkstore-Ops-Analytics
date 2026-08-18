# Product Thinking

## The Business Problem
QuickDash promises 15-minute delivery, but internally, delivery time has
been creeping and SLA compliance is inconsistent store to store. Leadership
wants to know two things before signing off on a company-wide rollout of a
new order-batching/routing engine: is it actually working where it's already
live, and by how much — with enough confidence to justify the engineering
cost of rolling it out everywhere.

## Why This Isn't a Simple A/B Test
The routing engine went to specific cities first (Bengaluru, Mumbai, Delhi
NCR), not a randomized sample of stores — that's how most infra/ops rollouts
actually happen in practice (staged by market, not randomized, because
there's real deployment and ops-training cost per city). A Product Analyst
who only knows how to read an A/B test dashboard is stuck here. One who
understands diff-in-diff can still get a credible causal estimate, as long
as they check the assumption that makes it valid: did treated and control
stores move together *before* the rollout? If yes, the gap that opens up
after rollout, net of the pre-existing gap, is attributable to the
treatment — not just to Bengaluru/Mumbai/Delhi NCR being different markets.

This is deliberately the centerpiece of the project — it's the kind of
question that separates "can run a query" from "can be trusted with a real
causal claim," and it's rarely covered in generic portfolio projects.

## Hypotheses
- **H1:** Stockouts are a meaningfully large share of checkout failures,
  not a minor edge case, because dark-store inventory turns fast. →
  confirmed — stockout accounts for 70% of all checkout failures, more than
  double the "other" failure category.
- **H2:** Tier 2 city sessions convert at a lower rate than Tier 1, due to
  thinner catchment density. → **not confirmed.** Order conversion is
  31.30% (Tier 1) vs 31.35% (Tier 2) — functionally identical. Worth noting
  honestly rather than dropping quietly: not every hypothesis going in pans
  out, and this one didn't. (It does suggest catchment density isn't the
  binding constraint on Tier 2 conversion in this dataset — something else
  would be, if this were a real investigation.)
- **H3:** The routing engine reduces average delivery time, and the effect
  survives controlling for city tier and day-of-week, not just a raw
  before/after. → confirmed via diff-in-diff regression — see README for
  the coefficient, standard error, and confidence interval.

## North Star Metric
**On-Time Delivery Rate (% of orders meeting the 15-minute SLA).** Chosen
over raw delivery speed or order volume because it's the metric that
directly reflects whether QuickDash is keeping the promise it markets on —
volume can grow while the actual customer experience quietly degrades, and
SLA rate is what catches that.

### Input Metrics
- Average delivery time per store
- Stockout cancellation rate (a controllable input — better demand
  forecasting and replenishment cadence move this directly)
- Fulfillment rate (orders delivered / orders placed)

### Output Metrics
- On-Time Delivery Rate — North Star
- GTV per store (commercial outcome)
- Session → order conversion rate (demand-side health)

## What I'd Do Next
- Roll the routing engine out company-wide — the DiD estimate is
  statistically significant with a tight confidence interval, and the
  pre-trend check supports treating it as causal, not just correlational
- Investigate the bottom-tier stores specifically (see Store Performance
  section) — the fulfillment-rate gap between best and worst store is small
  in percentage terms but consistent, suggesting a fixable, structural issue
  (likely staffing or SKU assortment) rather than random noise
- Target the stockout-driven checkout failures directly — at 9% of all
  checkout attempts, this is a bigger lever than most generic "improve
  checkout UX" initiatives would touch, and it's a supply-side fix
  (inventory/demand forecasting), not a product-surface fix
- Revisit H2 with real data — if Tier 2 conversion genuinely isn't behind
  Tier 1, the growth story there might be about awareness/acquisition
  rather than in-app experience, which is a different team's problem to
  solve
