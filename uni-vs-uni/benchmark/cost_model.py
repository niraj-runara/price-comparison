#!/usr/bin/env python3
"""GCP cost model for unified RTX PRO 6000 vs unified 4x L4.

*** These hourly prices are approximate on-demand list prices and WILL drift.
*** Verify current numbers at https://cloud.google.com/compute/all-pricing
*** before trusting cost-per-1M-tokens numbers.
"""

HOURLY_COST_USD = {
    # 48 vCPU / 180 GB + 1x NVIDIA RTX PRO 6000 (g4), us-central1 on-demand ~.
    "g4-standard-48": 4.50,
    # 48 vCPU / 192 GB + 4x NVIDIA L4 (g2), us-central1 on-demand ~.
    "g2-standard-48": 4.00,
}

DEPLOYMENT_INSTANCES = {
    "unified_rtx": {
        "unified-rtx-node": "g4-standard-48",
    },
    "unified_l4": {
        "unified-l4-node": "g2-standard-48",
    },
}


def hourly_cost(deployment: str) -> float:
    instances = DEPLOYMENT_INSTANCES[deployment]
    return sum(HOURLY_COST_USD[machine_type] for machine_type in instances.values())


def cost_per_million_tokens(deployment: str, tokens_per_sec: float) -> float:
    if tokens_per_sec <= 0:
        return float("inf")
    tokens_per_hour = tokens_per_sec * 3600
    cost_per_hour = hourly_cost(deployment)
    cost_per_token = cost_per_hour / tokens_per_hour
    return cost_per_token * 1_000_000


if __name__ == "__main__":
    for deployment in DEPLOYMENT_INSTANCES:
        print(f"{deployment}: ${hourly_cost(deployment):.4f}/hr across {list(DEPLOYMENT_INSTANCES[deployment])}")
