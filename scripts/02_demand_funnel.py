"""
Session -> order funnel, from the sampled sessions table. The interesting
bit here vs a generic e-comm funnel is the stockout failure at checkout --
that's a supply-side constraint bleeding into a demand-side metric, which
is a very q-commerce-specific thing worth calling out (a generic web funnel
doesn't have this failure mode at all).
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
PALETTE = ["#1b3a4b", "#2c6e8f", "#4fa3bf", "#8ccdd8", "#c5e8e0"]

sessions = pd.read_csv(RAW / "sessions_sample.csv")
n = len(sessions)

stage_counts = {
    "Session Started": n,
    "Reached Browse": sessions.reached_browse.sum(),
    "Added to Cart": sessions.reached_add_to_cart.sum(),
    "Reached Checkout": sessions.reached_checkout.sum(),
    "Order Placed": (sessions.order_outcome == "ORDER_PLACED").sum(),
}

funnel = pd.DataFrame({
    "stage": stage_counts.keys(),
    "sessions": stage_counts.values(),
})
funnel["pct_of_total"] = (funnel.sessions / n * 100).round(2)
funnel["step_conv_pct"] = (funnel.sessions / funnel.sessions.shift(1) * 100).round(2)
funnel.loc[0, "step_conv_pct"] = 100.0
funnel.to_csv(PROC / "session_funnel.csv", index=False)
print(funnel.to_string(index=False))

overall_conv = funnel.loc[funnel.stage == "Order Placed", "pct_of_total"].iloc[0]
print(f"\nSession -> order conversion: {overall_conv}%")

# checkout outcome breakdown, since "reached checkout" hides a meaningful split
checkout_reached = sessions[sessions.reached_checkout]
outcome_split = checkout_reached.order_outcome.value_counts()
outcome_pct = (outcome_split / len(checkout_reached) * 100).round(1)
print("\nOf sessions that reached checkout:")
print(outcome_pct.to_string())
stockout_share_of_failures = outcome_split.get("CHECKOUT_FAILED_STOCKOUT", 0) / (
    outcome_split.get("CHECKOUT_FAILED_STOCKOUT", 0) + outcome_split.get("CHECKOUT_FAILED_OTHER", 0)
) * 100
print(f"\nStockout is {stockout_share_of_failures:.0f}% of all checkout failures (vs. payment/other issues)")
outcome_pct.to_csv(PROC / "checkout_outcome_split.csv", header=["pct_of_checkouts_reached"])

# funnel by city tier -- Tier 2 conversion tends to lag on q-commerce due to
# thinner catchment density / fewer nearby stores, worth checking
by_tier = sessions.groupby("city_tier").apply(
    lambda g: pd.Series({
        "sessions": len(g),
        "order_rate_pct": round((g.order_outcome == "ORDER_PLACED").mean() * 100, 2),
    }),
    include_groups=False,
)
print("\nOrder conversion by city tier:")
print(by_tier.to_string())
by_tier.to_csv(PROC / "funnel_by_city_tier.csv")

# ---- chart: funnel ----
fig, ax = plt.subplots(figsize=(10.5, 6))
bars = ax.barh(funnel.stage[::-1], funnel.pct_of_total[::-1], color=PALETTE[::-1])
for bar, pct, cnt in zip(bars, funnel.pct_of_total[::-1], funnel.sessions[::-1]):
    ax.text(bar.get_width() + 1.2, bar.get_y() + bar.get_height() / 2,
            f"{pct}%  ({cnt:,})", va="center", fontsize=11)
ax.set_xlim(0, 112)
ax.set_xlabel("% of Sessions")
ax.set_title(f"QuickDash Session -> Order Funnel (n={n:,} sampled sessions)")
plt.tight_layout()
plt.savefig(VIZ / "01_session_funnel.png", dpi=150)
plt.close()

# ---- chart: checkout failure breakdown ----
fig, ax = plt.subplots(figsize=(7, 6))
labels = outcome_pct.index.str.replace("_", " ").str.title()
ax.pie(outcome_pct.values, labels=labels, autopct="%1.0f%%", colors=PALETTE[1:1+len(outcome_pct)],
       startangle=90, textprops={"fontsize": 10})
ax.set_title("What Happens After Checkout Starts")
plt.tight_layout()
plt.savefig(VIZ / "02_checkout_outcomes.png", dpi=150)
plt.close()

print("\nsaved: visuals/01_session_funnel.png, visuals/02_checkout_outcomes.png")
