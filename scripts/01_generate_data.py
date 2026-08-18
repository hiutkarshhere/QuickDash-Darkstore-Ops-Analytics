"""
Generates the QuickDash dataset -- a fictional 10-minute delivery app,
same idea as Zepto/Blinkit/Instamart. Nothing here is real company data,
it's a simulation with documented parameters (see docs/assumptions.md).

Four outputs:
  dark_stores.csv          - store master data (60 stores)
  experiment_rollout.csv   - which stores got the new routing engine, and when
  store_daily_metrics.csv  - full-population store x day panel (used for
                              tiering + the diff-in-diff)
  sessions_sample.csv      - a *sample* of ~85k app sessions for funnel work.
                              Full session volume would be in the tens of
                              millions across 6 months, way more than we need
                              to characterize a conversion funnel, so this is
                              deliberately a sample, not the full population.
                              (store_daily_metrics.csv is the full-population
                              table -- that's the one to trust for anything
                              volume-sensitive like GTV or order counts.)
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

rng = np.random.default_rng(7)

OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

START = datetime(2026, 1, 1)
END = datetime(2026, 6, 30)
DATES = pd.date_range(START, END, freq="D")
ROLLOUT_DATE = datetime(2026, 4, 1)  # when the new batching/routing engine went live

# ---------------------------------------------------------------------------
# 1. DARK STORES
# ---------------------------------------------------------------------------
N_STORES = 60
CITIES = {
    # city: (tier, weight)
    "Bengaluru": ("Tier 1", 10), "Mumbai": ("Tier 1", 9), "Delhi NCR": ("Tier 1", 11),
    "Hyderabad": ("Tier 1", 6), "Pune": ("Tier 1", 6), "Chennai": ("Tier 1", 5),
    "Lucknow": ("Tier 2", 4), "Jaipur": ("Tier 2", 4), "Indore": ("Tier 2", 3),
    "Bhopal": ("Tier 2", 2),
}
city_names = list(CITIES.keys())
city_weights = np.array([w for _, w in CITIES.values()], dtype=float)
city_weights = city_weights / city_weights.sum()

store_rows = []
for i in range(N_STORES):
    city = rng.choice(city_names, p=city_weights)
    tier, _ = CITIES[city]
    launch_offset_days = int(rng.integers(-720, -30))  # most stores are pre-existing
    store_rows.append({
        "store_id": f"DS{1000+i}",
        "city": city,
        "city_tier": tier,
        "zone": rng.choice(["North", "South", "East", "West", "Central"]),
        "launch_date": (START + timedelta(days=launch_offset_days)).date(),
        "sq_ft": int(rng.normal(2400, 450)),
        "sku_count": int(rng.normal(3200, 400)),
        "staff_count": int(rng.integers(14, 32)),
        "catchment_km": round(float(rng.uniform(2.0, 3.5)), 1),
    })
stores = pd.DataFrame(store_rows)
stores["sq_ft"] = stores["sq_ft"].clip(lower=1200)
stores["sku_count"] = stores["sku_count"].clip(lower=1800)

# ---------------------------------------------------------------------------
# 2. EXPERIMENT ROLLOUT
# ---------------------------------------------------------------------------
# Routing engine wasn't randomized (product/eng rolled it out to Bengaluru,
# Mumbai and Delhi NCR first, i.e. the biggest metro clusters, since that's
# where the batching problem was worst). This is a natural experiment, not
# an RCT -- worth being upfront about in the writeup, since it changes how
# much we can claim.
treated_cities = {"Bengaluru", "Mumbai", "Delhi NCR"}
stores["treatment_group"] = stores["city"].apply(lambda c: "treated" if c in treated_cities else "control")
stores["rollout_date"] = stores["treatment_group"].apply(lambda g: ROLLOUT_DATE.date() if g == "treated" else pd.NaT)

rollout = stores[["store_id", "treatment_group", "rollout_date"]].copy()
n_treated = (stores.treatment_group == "treated").sum()
n_control = (stores.treatment_group == "control").sum()

# ---------------------------------------------------------------------------
# 3. STORE-DAY PANEL (full population -- this drives tiering + DiD)
# ---------------------------------------------------------------------------
# Store-level baseline heterogeneity: some stores are just better run than
# others (staffing, layout, manager quality -- not something we model
# explicitly, just captured as a random store effect)
store_base_delivery = pd.Series(
    rng.normal(16.3, 1.6, size=N_STORES), index=stores.store_id
).clip(12, 21)

store_base_volume = pd.Series(
    rng.normal(1.0, 0.18, size=N_STORES), index=stores.store_id
).clip(0.6, 1.5)  # multiplier on the city-tier baseline order volume

TIER_BASE_ORDERS = {"Tier 1": 165, "Tier 2": 95}

panel_rows = []
for d in DATES:
    day_of_week_mult = 1.18 if d.dayofweek in (4, 5) else 1.0  # Fri/Sat bump
    # category is still growing in this window -- gentle upward trend
    growth_mult = 1.0 + 0.0022 * (d - START).days
    # monsoon-adjacent slowdown hits everyone in June regardless of treatment
    monsoon_delay = 0.55 if d.month == 6 else (0.2 if d.month == 5 and d.day > 20 else 0.0)

    for _, s in stores.iterrows():
        sid = s.store_id
        is_treated = s.treatment_group == "treated"
        post_rollout = is_treated and d >= ROLLOUT_DATE

        base_orders = TIER_BASE_ORDERS[s.city_tier] * store_base_volume[sid]
        orders_placed = int(rng.poisson(max(base_orders * day_of_week_mult * growth_mult, 10)))

        # stockout-driven cancellations -- more common in smaller-SKU stores
        stockout_rate = np.clip(0.045 - (s.sku_count - 1800) / 1800 * 0.015, 0.015, 0.06)
        other_cancel_rate = 0.012

        orders_cancelled_stockout = int(rng.binomial(orders_placed, stockout_rate))
        orders_cancelled_other = int(rng.binomial(orders_placed, other_cancel_rate))
        orders_delivered = orders_placed - orders_cancelled_stockout - orders_cancelled_other

        delivery_time = store_base_delivery[sid] + monsoon_delay + rng.normal(0, 0.9)
        if post_rollout:
            delivery_time -= 1.75  # the actual treatment effect we're planting
        delivery_time = max(delivery_time, 8.0)

        # SLA = promise is 15 min; pct_on_time computed from a distribution
        # around delivery_time rather than a hard cutoff on the mean, since
        # that's closer to how real fulfillment variance works
        sla_prob = 1 / (1 + np.exp((delivery_time - 15.0) / 2.1))  # logistic around 15min
        pct_on_time = float(np.clip(rng.normal(sla_prob, 0.04), 0.35, 0.99))

        avg_order_value = float(rng.normal(238 if s.city_tier == "Tier 1" else 205, 28))

        panel_rows.append({
            "date": d.date(),
            "store_id": sid,
            "city": s.city,
            "city_tier": s.city_tier,
            "treatment_group": s.treatment_group,
            "orders_placed": orders_placed,
            "orders_delivered": orders_delivered,
            "orders_cancelled_stockout": orders_cancelled_stockout,
            "orders_cancelled_other": orders_cancelled_other,
            "avg_delivery_time_min": round(delivery_time, 2),
            "pct_on_time_15min": round(pct_on_time * 100, 1),
            "gtv_inr": round(orders_delivered * avg_order_value, 0),
        })

panel = pd.DataFrame(panel_rows)

# a handful of stores had a GPS/clock sync issue in Feb that logged a few
# bogus negative delivery times -- keeping this in deliberately, it gets
# caught and cleaned in the analysis script rather than scrubbed here.
# (~40 rows out of 10,860 -- small enough to be a real "found it while
# poking at the data" moment, not a designed feature)
glitch_idx = rng.choice(panel.index, size=40, replace=False)
panel.loc[glitch_idx, "avg_delivery_time_min"] = -panel.loc[glitch_idx, "avg_delivery_time_min"] * 0.1

# ---------------------------------------------------------------------------
# 4. SESSION SAMPLE (funnel analysis -- deliberately a sample, see docstring)
# ---------------------------------------------------------------------------
N_SESSIONS = 85_000
session_dates = pd.to_datetime(rng.choice(DATES, size=N_SESSIONS))
session_store = rng.choice(stores.store_id, size=N_SESSIONS)
store_tier_map = stores.set_index("store_id")["city_tier"].to_dict()

# funnel stage probabilities, with a device-os effect (iOS users convert a
# touch better -- consistent with what most q-commerce apps report, iOS skews
# higher income / higher intent in the Indian market)
device_os = rng.choice(["Android", "iOS"], size=N_SESSIONS, p=[0.84, 0.16])
device_mod = np.where(device_os == "iOS", 0.02, 0.0)

p_browse = 0.81 + device_mod
p_cart = 0.62 + device_mod
p_checkout = 0.71 + device_mod

reached_browse = rng.random(N_SESSIONS) < p_browse
reached_cart = reached_browse & (rng.random(N_SESSIONS) < p_cart)
reached_checkout = reached_cart & (rng.random(N_SESSIONS) < p_checkout)

# of those who reach checkout: some fail on stockout (a key cart item goes
# out of stock right at checkout -- this is the q-commerce-specific failure
# mode that a generic e-comm funnel wouldn't have), some fail for other
# reasons (payment decline etc.), rest succeed
outcome = np.full(N_SESSIONS, "ABANDONED_NO_CHECKOUT", dtype=object)
checkout_roll = rng.random(N_SESSIONS)
outcome[reached_checkout & (checkout_roll < 0.09)] = "CHECKOUT_FAILED_STOCKOUT"
outcome[reached_checkout & (checkout_roll >= 0.09) & (checkout_roll < 0.13)] = "CHECKOUT_FAILED_OTHER"
outcome[reached_checkout & (checkout_roll >= 0.13)] = "ORDER_PLACED"

sessions = pd.DataFrame({
    "session_id": np.arange(1, N_SESSIONS + 1),
    "session_date": session_dates.date,
    "store_id": session_store,
    "city_tier": [store_tier_map[s] for s in session_store],
    "device_os": device_os,
    "reached_browse": reached_browse,
    "reached_add_to_cart": reached_cart,
    "reached_checkout": reached_checkout,
    "order_outcome": outcome,
})

# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------
stores.to_csv(OUT / "dark_stores.csv", index=False)
rollout.to_csv(OUT / "experiment_rollout.csv", index=False)
panel.to_csv(OUT / "store_daily_metrics.csv", index=False)
sessions.to_csv(OUT / "sessions_sample.csv", index=False)

print(f"stores: {len(stores)}  ({n_treated} treated / {n_control} control)")
print(f"store_daily_metrics: {len(panel):,} rows ({len(DATES)} days x {N_STORES} stores)")
print(f"sessions_sample: {len(sessions):,} rows")
print(f"total orders placed in panel: {panel.orders_placed.sum():,}")
print(f"total GTV in panel: Rs {panel.gtv_inr.sum():,.0f}")
