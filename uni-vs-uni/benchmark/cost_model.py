#!/usr/bin/env python3
"""Break-even cost helpers for Vast.ai RTX PRO 6000 vs GCP unified 4x L4.

Only the *baseline* hourly cost is hardcoded (Vast.ai rental for 1x RTX PRO 6000).
For each concurrency level, given measured tok/s:

  break_even_hourly_l4 = baseline_hourly * (tps_l4 / tps_rtx)

Change BASELINE_HOURLY_USD (or --baseline-hourly) and re-run plot_results.py —
no need to re-benchmark.
"""

# Set this to your Vast.ai RTX PRO 6000 rental $/hr (check the instance listing).
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
    print(f"baseline Vast.ai RTX ({BASELINE_DEPLOYMENT}): ${BASELINE_HOURLY_USD:.2f}/hr")
    print(
        "break_even_hourly_other = "
        f"{BASELINE_HOURLY_USD} * (tps_{OTHER_DEPLOYMENT} / tps_{BASELINE_DEPLOYMENT})"
    )
