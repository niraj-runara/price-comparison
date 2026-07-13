#!/usr/bin/env python3
"""Plot throughput/latency and break-even hourly cost from combined_results.json.

Only the RTX baseline hourly price is assumed known. For each concurrency, we
compute what the L4 unified deployment's $/hr must be to match the RTX baseline's
cost per 1M tokens — using measured tok/s only (no L4 price hardcoding).
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from cost_model import (
    BASELINE_DEPLOYMENT,
    BASELINE_HOURLY_USD,
    OTHER_DEPLOYMENT,
    break_even_hourly,
    cost_per_million_tokens,
)


def load(path):
    with open(path) as f:
        return pd.DataFrame(json.load(f))


def build_breakeven_table(df, baseline_hourly):
    base = (
        df[df["deployment"] == BASELINE_DEPLOYMENT][
            ["concurrency", "tokens_per_sec", "latency_p50_s", "latency_p95_s", "latency_p99_s", "num_errors"]
        ]
        .rename(columns={
            "tokens_per_sec": "tps_baseline",
            "latency_p50_s": "lat_p50_baseline",
            "latency_p95_s": "lat_p95_baseline",
            "latency_p99_s": "lat_p99_baseline",
            "num_errors": "errors_baseline",
        })
        .set_index("concurrency")
    )
    other = (
        df[df["deployment"] == OTHER_DEPLOYMENT][
            ["concurrency", "tokens_per_sec", "latency_p50_s", "latency_p95_s", "latency_p99_s", "num_errors"]
        ]
        .rename(columns={
            "tokens_per_sec": "tps_other",
            "latency_p50_s": "lat_p50_other",
            "latency_p95_s": "lat_p95_other",
            "latency_p99_s": "lat_p99_other",
            "num_errors": "errors_other",
        })
        .set_index("concurrency")
    )
    joined = base.join(other, how="inner").reset_index()
    joined["baseline_hourly_usd"] = baseline_hourly
    joined["baseline_cost_per_1m_usd"] = joined.apply(
        lambda r: cost_per_million_tokens(baseline_hourly, r["tps_baseline"]),
        axis=1,
    )
    joined["break_even_other_hourly_usd"] = joined.apply(
        lambda r: break_even_hourly(baseline_hourly, r["tps_baseline"], r["tps_other"]),
        axis=1,
    )
    return joined.sort_values("concurrency")


def _set_concurrency_axis(ax, concurrencies):
    """Equidistant ticks labeled by measured concurrency levels."""
    xs = sorted({int(c) for c in concurrencies})
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels([str(x) for x in xs])
    ax.minorticks_off()
    return xs


def plot_metric(df, ycol, ylabel, title, out_path):
    fig, ax = plt.subplots(figsize=(7, 5))
    xs = sorted({int(c) for c in df["concurrency"]})
    xpos = {c: i for i, c in enumerate(xs)}
    for label, group in df.groupby("deployment"):
        group = group.sort_values("concurrency")
        ax.plot(
            [xpos[int(c)] for c in group["concurrency"]],
            group[ycol],
            marker="o",
            label=label,
        )
    ax.set_xlabel("Concurrent users")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    _set_concurrency_axis(ax, xs)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def plot_latency_percentiles(df, out_path):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    xs = sorted({int(c) for c in df["concurrency"]})
    xpos = {c: i for i, c in enumerate(xs)}
    percentiles = [("latency_p50_s", "p50"), ("latency_p95_s", "p95"), ("latency_p99_s", "p99")]
    for ax, (col, name) in zip(axes, percentiles):
        for label, group in df.groupby("deployment"):
            group = group.sort_values("concurrency")
            ax.plot(
                [xpos[int(c)] for c in group["concurrency"]],
                group[col],
                marker="o",
                label=label,
            )
        ax.set_title(f"Latency {name}")
        ax.set_xlabel("Concurrent users")
        _set_concurrency_axis(ax, xs)
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Latency (s)")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def plot_breakeven(breakeven_df, baseline_hourly, out_path):
    fig, ax = plt.subplots(figsize=(7, 5))
    xs = sorted({int(c) for c in breakeven_df["concurrency"]})
    xpos = {c: i for i, c in enumerate(xs)}
    plot_x = [xpos[int(c)] for c in breakeven_df["concurrency"]]
    ys = breakeven_df["break_even_other_hourly_usd"]
    ax.plot(
        plot_x,
        ys,
        marker="o",
        label=f"{OTHER_DEPLOYMENT} break-even $/hr",
    )
    for x, y in zip(plot_x, ys):
        ax.annotate(
            f"${y:.2f}",
            (x, y),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
        )
    ax.axhline(
        baseline_hourly,
        color="gray",
        linestyle="--",
        label=f"{BASELINE_DEPLOYMENT} hourly (${baseline_hourly:.2f}/hr)",
    )
    ax.set_xlabel("Concurrent users")
    ax.set_ylabel("USD / hour")
    ax.set_title(
        f"Break-even {OTHER_DEPLOYMENT} hourly cost\n"
        f"(to match {BASELINE_DEPLOYMENT} $/1M tokens)"
    )
    _set_concurrency_axis(ax, xs)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")

def print_summary_table(breakeven_df):
    cols = [
        "concurrency",
        "tps_baseline",
        "tps_other",
        "baseline_cost_per_1m_usd",
        "break_even_other_hourly_usd",
    ]
    print(
        breakeven_df[cols]
        .rename(columns={
            "tps_baseline": f"tps_{BASELINE_DEPLOYMENT}",
            "tps_other": f"tps_{OTHER_DEPLOYMENT}",
            "baseline_cost_per_1m_usd": f"{BASELINE_DEPLOYMENT}_$/1M",
            "break_even_other_hourly_usd": f"{OTHER_DEPLOYMENT}_break_even_$/hr",
        })
        .to_string(index=False)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default=os.path.join(os.path.dirname(__file__), "results", "combined_results.json"),
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(__file__), "results", "plots"),
    )
    parser.add_argument(
        "--baseline-hourly",
        type=float,
        default=BASELINE_HOURLY_USD,
        help=f"Baseline (RTX) $/hr — default {BASELINE_HOURLY_USD}",
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    df = load(args.results)
    breakeven = build_breakeven_table(df, args.baseline_hourly)

    print(f"baseline={BASELINE_DEPLOYMENT} @ ${args.baseline_hourly:.2f}/hr")
    print(f"other={OTHER_DEPLOYMENT} break-even hourly to match baseline $/1M tokens\n")
    print_summary_table(breakeven)

    breakeven_path = os.path.join(os.path.dirname(args.results), "breakeven.json")
    with open(breakeven_path, "w") as f:
        json.dump(breakeven.to_dict(orient="records"), f, indent=2)
    print(f"\nwrote {breakeven_path}")

    plot_metric(df, "tokens_per_sec", "Tokens / sec", "Throughput: Unified RTX vs Unified L4",
                os.path.join(args.out_dir, "throughput.png"))
    plot_latency_percentiles(df, os.path.join(args.out_dir, "latency_percentiles.png"))
    plot_breakeven(
        breakeven,
        args.baseline_hourly,
        os.path.join(args.out_dir, "break_even_hourly.png"),
    )


if __name__ == "__main__":
    main()
