"""
Rolls up store_daily_metrics into per-store operational KPIs and tiers
stores into Top/Mid/Bottom performers. Also where the delivery-time glitch
mentioned in the generator gets caught and dealt with -- leaving that in on
purpose, since "found a data quality issue, here's how I handled it" is
a bigger green flag than data that was suspiciously clean to begin with.
"""

import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
VIZ = ROOT / "visuals"

sns.set_theme(style="whitegrid", context="talk")

panel = pd.read_csv(RAW / "store_daily_metrics.csv", parse_dates=["date"])
stores = pd.read_csv(RAW / "dark_stores.csv")

# --- data quality check: negative delivery times shouldn't exist ---
bad_rows = panel[panel.avg_delivery_time_min < 0]
print(f"found {len(bad_rows)} rows with negative avg_delivery_time_min "
      f"out of {len(panel)} ({len(bad_rows)/len(panel)*100:.2f}%)")
print("stores affected:", sorted(bad_rows.store_id.unique().tolist()))
# these all cluster in Feb -- consistent with a logging/clock-sync issue on
# a subset of stores rather than random noise, so dropping rather than
# trying to impute
panel_clean = panel[panel.avg_delivery_time_min >= 0].copy()
print(f"dropped {len(bad_rows)} rows, {len(panel_clean)} remain\n")

# --- per-store rollup ---
store_kpis = panel_clean.groupby("store_id").agg(
    total_orders=("orders_placed", "sum"),
    total_delivered=("orders_delivered", "sum"),
    total_gtv=("gtv_inr", "sum"),
    avg_delivery_time=("avg_delivery_time_min", "mean"),
    avg_on_time_pct=("pct_on_time_15min", "mean"),
    avg_stockout_cancels=("orders_cancelled_stockout", "sum"),
).round(2)

store_kpis["fulfillment_rate_pct"] = (store_kpis.total_delivered / store_kpis.total_orders * 100).round(2)
store_kpis["stockout_cancel_rate_pct"] = (store_kpis.avg_stockout_cancels / store_kpis.total_orders * 100).round(2)
store_kpis["orders_per_day"] = (store_kpis.total_orders / panel_clean.date.nunique()).round(1)

store_kpis = store_kpis.merge(stores[["store_id", "city", "city_tier"]], on="store_id")

# --- tiering: composite score from fulfillment rate, on-time %, and
# stockout rate, each z-scored so they're on the same footing before
# averaging (fulfillment rate and stockout rate are almost the same thing
# by construction, but on-time % captures something the other two don't)
for col in ["fulfillment_rate_pct", "avg_on_time_pct"]:
    store_kpis[f"z_{col}"] = (store_kpis[col] - store_kpis[col].mean()) / store_kpis[col].std()
store_kpis["z_stockout_cancel_rate_pct"] = -(
    (store_kpis["stockout_cancel_rate_pct"] - store_kpis["stockout_cancel_rate_pct"].mean())
    / store_kpis["stockout_cancel_rate_pct"].std()
)  # negated -- lower stockout rate is better

store_kpis["perf_score"] = store_kpis[
    ["z_fulfillment_rate_pct", "z_avg_on_time_pct", "z_stockout_cancel_rate_pct"]
].mean(axis=1)

store_kpis["tier"] = pd.qcut(store_kpis.perf_score, 3, labels=["Bottom Third", "Mid Third", "Top Third"])

store_kpis = store_kpis.sort_values("perf_score", ascending=False)
store_kpis.drop(columns=[c for c in store_kpis.columns if c.startswith("z_")]).to_csv(
    PROC / "store_performance_tiers.csv", index=False
)

print("=== TOP 5 STORES ===")
print(store_kpis[["store_id", "city", "fulfillment_rate_pct", "avg_on_time_pct", "orders_per_day"]].head(5).to_string(index=False))
print("\n=== BOTTOM 5 STORES ===")
print(store_kpis[["store_id", "city", "fulfillment_rate_pct", "avg_on_time_pct", "orders_per_day"]].tail(5).to_string(index=False))

tier_summary = store_kpis.groupby("tier", observed=True).agg(
    stores=("store_id", "count"),
    avg_fulfillment=("fulfillment_rate_pct", "mean"),
    avg_on_time=("avg_on_time_pct", "mean"),
    avg_stockout_rate=("stockout_cancel_rate_pct", "mean"),
    total_gtv=("total_gtv", "sum"),
).round(2)
print("\n=== TIER SUMMARY ===")
print(tier_summary.to_string())
tier_summary.to_csv(PROC / "tier_summary.csv")

gap = (store_kpis.iloc[0].fulfillment_rate_pct - store_kpis.iloc[-1].fulfillment_rate_pct)
print(f"\nFulfillment rate gap, best vs worst store: {gap:.1f} points")

# ---- chart: delivery time distribution by tier ----
merged = panel_clean.merge(
    store_kpis[["store_id", "tier"]], on="store_id"
)
fig, ax = plt.subplots(figsize=(10, 6))
sns.boxplot(data=merged, x="tier", y="avg_delivery_time_min",
            order=["Top Third", "Mid Third", "Bottom Third"],
            hue="tier", hue_order=["Top Third", "Mid Third", "Bottom Third"],
            legend=False,
            palette={"Top Third": "#2c6e8f", "Mid Third": "#8ccdd8", "Bottom Third": "#d98880"}, ax=ax)
ax.set_xlabel("Store Performance Tier")
ax.set_ylabel("Daily Avg Delivery Time (min)")
ax.set_title("Delivery Time Spread by Store Tier")
plt.tight_layout()
plt.savefig(VIZ / "03_delivery_time_by_tier.png", dpi=150)
plt.close()

# ---- chart: fulfillment vs on-time scatter, sized by volume ----
fig, ax = plt.subplots(figsize=(10, 7.5))
tier_colors = {"Top Third": "#2c6e8f", "Mid Third": "#8ccdd8", "Bottom Third": "#d98880"}
for t, sub in store_kpis.groupby("tier", observed=True):
    ax.scatter(sub.fulfillment_rate_pct, sub.avg_on_time_pct, s=sub.orders_per_day * 2.2,
               color=tier_colors[t], alpha=0.75, label=t, edgecolors="white", linewidth=0.6)
ax.set_xlabel("Fulfillment Rate (%)")
ax.set_ylabel("On-Time Delivery Rate (%, 15-min SLA)")
ax.set_title("Store Performance Map (bubble size = orders/day)")
ax.legend(title="Tier")
plt.tight_layout()
plt.savefig(VIZ / "04_store_performance_map.png", dpi=150)
plt.close()

print("\nsaved: visuals/03_delivery_time_by_tier.png, visuals/04_store_performance_map.png")
