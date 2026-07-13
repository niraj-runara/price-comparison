#!/usr/bin/env python3
"""Break-even cost helpers for unified RTX PRO 6000 vs unified 4x L4.

Only the *baseline* hourly cost is hardcoded. For each concurrency level, given
measured tok/s for both deployments:

  cost/1M = hourly / (tok/s * 3600) * 1e6

Set cost/1M_l4 == cost/1M_rtx and solve for the L4 side's hourly:

  break_even_hourly_l4 = baseline_hourly * (tps_l4 / tps_rtx)

Change BASELINE_HOURLY_USD (or pass --baseline-hourly to plot_results.py) and
re-run plot_results.py on existing results — no need to re-benchmark.
"""

# Approximate on-demand list for g4-standard-48 (1x RTX PRO 6000), us-central1.
# Override via plot_results.py --baseline-hourly without re-running the load test.
BASELINE_HOURLY_USD = 4.50

BASELINE_DEPLOYMENT = "unified_rtx"
OTHER_DEPLOYMENT = "unified_l4"


def cost_per_million_tokens(hourly_usd: float, tokens_per_sec: float) -> float:
    if tokens_per_sec <= 0:
        return float("inf")
    return hourly_usd / (tokens_per_sec * 3600) * 1_000_000


def break_even_hourly(
    baseline_hourly_usd: float,
    baseline_tokens_per_sec: float,
    other_tokens_per_sec: float,
) -> float:
    """Hourly $/hr the *other* deployment needs to match baseline cost/1M tokens."""
    if baseline_tokens_per_sec <= 0:
        return float("inf")
    return baseline_hourly_usd * (other_tokens_per_sec / baseline_tokens_per_sec)


if __name__ == "__main__":
    print(f"baseline ({BASELINE_DEPLOYMENT}): ${BASELINE_HOURLY_USD:.2f}/hr")
    print(
        "break_even_hourly_other = "
        f"{BASELINE_HOURLY_USD} * (tps_{OTHER_DEPLOYMENT} / tps_{BASELINE_DEPLOYMENT})"
    )
