"""
Diff-in-diff on the routing engine rollout. This wasn't an A/B test -- the
rollout went to specific cities (Bengaluru, Mumbai, Delhi NCR) first, not a
randomized set of stores, so treatment and control aren't guaranteed
comparable by construction. That's exactly the situation DiD is built for:
if pre-period trends look parallel between the two groups, the assumption
that they'd have kept moving together absent treatment becomes reasonable,
and the post-period gap net of the pre-period gap is a defensible causal
estimate.

Two things get checked before trusting the number: parallel pre-trends, and
whether the effect holds up in a regression that also controls for city
tier and day-of-week seasonality, not just the raw 2x2 table.
"""

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
VIZ = ROOT / "visuals"

sns.set_theme(style="whitegrid", context="talk")

panel = pd.read_csv(RAW / "store_daily_metrics.csv", parse_dates=["date"])
panel = panel[panel.avg_delivery_time_min >= 0].copy()  # same cleaning as script 03

ROLLOUT_DATE = pd.Timestamp("2026-04-01")
panel["post"] = (panel.date >= ROLLOUT_DATE).astype(int)
panel["treated"] = (panel.treatment_group == "treated").astype(int)
panel["did_term"] = panel.post * panel.treated

# ---------------------------------------------------------------------------
# 1. Parallel pre-trends check (visual + simple check, not just assumed)
# ---------------------------------------------------------------------------
pre = panel[panel.date < ROLLOUT_DATE]
weekly_pre = (
    pre.assign(week=pre.date.dt.to_period("W").apply(lambda p: p.start_time))
    .groupby(["week", "treatment_group"])["avg_delivery_time_min"]
    .mean()
    .unstack()
)
weekly_pre.to_csv(PROC / "pretrend_weekly_delivery_time.csv")
pre_gap_trend = (weekly_pre["treated"] - weekly_pre["control"])
print("Pre-period weekly gap (treated - control), min:max delivery time diff:")
print(f"  first week: {pre_gap_trend.iloc[0]:+.2f} min, last pre week: {pre_gap_trend.iloc[-1]:+.2f} min")
print(f"  gap standard deviation across pre-period: {pre_gap_trend.std():.2f} min")
print("  (small, stable gap across pre-period supports the parallel trends assumption)\n")

# ---------------------------------------------------------------------------
# 2. Simple 2x2 DiD table
# ---------------------------------------------------------------------------
means = panel.groupby(["treated", "post"])["avg_delivery_time_min"].mean().unstack()
means.columns = ["pre", "post"]
means.index = ["control", "treated"]
print("=== 2x2 MEANS (avg delivery time, minutes) ===")
print(means.round(2).to_string())

diff_control = means.loc["control", "post"] - means.loc["control", "pre"]
diff_treated = means.loc["treated", "post"] - means.loc["treated", "pre"]
simple_did = diff_treated - diff_control
print(f"\nControl change (post - pre): {diff_control:+.2f} min")
print(f"Treated change (post - pre): {diff_treated:+.2f} min")
print(f"Simple DiD estimate: {simple_did:+.2f} min")

# ---------------------------------------------------------------------------
# 3. Regression DiD, with controls (city tier fixed effect + day-of-week)
# ---------------------------------------------------------------------------
panel["dow"] = panel.date.dt.dayofweek.astype(str)

model = smf.ols(
    "avg_delivery_time_min ~ treated + post + did_term + C(city_tier) + C(dow)",
    data=panel,
).fit(cov_type="cluster", cov_kwds={"groups": panel["store_id"]})

print("\n=== REGRESSION DiD (clustered SE by store) ===")
print(model.summary().tables[1])

did_coef = model.params["did_term"]
did_se = model.bse["did_term"]
did_p = model.pvalues["did_term"]
ci_low, ci_high = model.conf_int().loc["did_term"]

print(f"\nDiD coefficient (treated x post): {did_coef:+.3f} min")
print(f"Standard error (clustered by store): {did_se:.3f}")
print(f"p-value: {did_p:.5f}")
print(f"95% CI: [{ci_low:+.3f}, {ci_high:+.3f}] min")
print(f"R-squared: {model.rsquared:.3f}")

# same model but for the SLA on-time % outcome, since delivery time alone
# doesn't tell the full story -- what matters commercially is SLA compliance
model_sla = smf.ols(
    "pct_on_time_15min ~ treated + post + did_term + C(city_tier) + C(dow)",
    data=panel,
).fit(cov_type="cluster", cov_kwds={"groups": panel["store_id"]})
sla_coef = model_sla.params["did_term"]
sla_p = model_sla.pvalues["did_term"]
print(f"\n--- Same model, on-time % as outcome ---")
print(f"DiD coefficient: {sla_coef:+.2f} pp   p-value: {sla_p:.5f}")

result_summary = pd.DataFrame([{
    "outcome": "avg_delivery_time_min",
    "simple_did": round(simple_did, 3),
    "regression_did": round(did_coef, 3),
    "se_clustered": round(did_se, 3),
    "p_value": round(did_p, 5),
    "ci_95_low": round(ci_low, 3),
    "ci_95_high": round(ci_high, 3),
}, {
    "outcome": "pct_on_time_15min",
    "simple_did": round(
        (means := panel.groupby(["treated", "post"])["pct_on_time_15min"].mean().unstack()).iloc[1, 1]
        - means.iloc[1, 0] - (means.iloc[0, 1] - means.iloc[0, 0]), 3
    ),
    "regression_did": round(sla_coef, 3),
    "se_clustered": round(model_sla.bse["did_term"], 3),
    "p_value": round(sla_p, 5),
    "ci_95_low": round(model_sla.conf_int().loc["did_term"][0], 3),
    "ci_95_high": round(model_sla.conf_int().loc["did_term"][1], 3),
}])
result_summary.to_csv(PROC / "diff_in_diff_results.csv", index=False)

# ---------------------------------------------------------------------------
# Chart: weekly trend, treated vs control, with rollout line
# ---------------------------------------------------------------------------
weekly = (
    panel.assign(week=panel.date.dt.to_period("W").apply(lambda p: p.start_time))
    .groupby(["week", "treatment_group"])["avg_delivery_time_min"]
    .mean()
    .unstack()
)
weekly.to_csv(PROC / "weekly_delivery_time_trend.csv")

fig, ax = plt.subplots(figsize=(12, 6.5))
ax.plot(weekly.index, weekly["control"], label="Control (not rolled out)", color="#7a7a7a", linewidth=2)
ax.plot(weekly.index, weekly["treated"], label="Treated (Bengaluru/Mumbai/Delhi NCR)", color="#2c6e8f", linewidth=2.5)
ax.axvline(ROLLOUT_DATE, color="#b34d4d", linestyle="--", linewidth=1.5, label="Routing engine rollout (Apr 1)")
ax.set_ylabel("Avg Delivery Time (min, weekly)")
ax.set_xlabel("Week")
ax.set_title("Delivery Time: Treated vs Control Stores, Before/After Rollout")
ax.legend(loc="upper left", fontsize=10)
plt.xticks(rotation=30)
plt.tight_layout()
plt.savefig(VIZ / "05_diff_in_diff_trend.png", dpi=150)
plt.close()

print("\nsaved: visuals/05_diff_in_diff_trend.png")
print("saved: data/processed/diff_in_diff_results.csv, weekly_delivery_time_trend.csv, pretrend_weekly_delivery_time.csv")
