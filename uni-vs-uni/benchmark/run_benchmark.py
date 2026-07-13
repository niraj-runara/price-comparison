#!/usr/bin/env python3
"""Sweep concurrency levels against the RTX and L4 unified endpoints.

Runs load_test.py once per (deployment, concurrency) pair, tags each result
with its deployment and cost/1M tokens, and writes results/combined_results.json
for plot_results.py to consume.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from cost_model import cost_per_million_tokens

CONCURRENCY_LEVELS = [1, 5, 10, 20, 40, 80]
DEFAULT_ENV_FILE = os.path.join(os.path.dirname(__file__), "benchmark.env")


def load_env_file(path):
    values = {}
    if not os.path.isfile(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            key, sep, raw = line.partition("=")
            if not sep:
                continue
            value = raw.strip().strip('"').strip("'")
            values[key.strip()] = value
    return values


def wait_for_health(endpoint, label, timeout_s=1800, poll_s=5):
    health_url = endpoint.rstrip("/") + "/health"
    deadline = time.time() + timeout_s
    print(f"[{label}] waiting for {health_url} ...", file=sys.stderr)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=10) as resp:
                if resp.status == 200:
                    print(f"[{label}] ready ({health_url})", file=sys.stderr)
                    return
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                pass
            else:
                print(f"[{label}] health HTTP {exc.code}, retrying ...", file=sys.stderr)
        except Exception as exc:
            print(f"[{label}] health check failed ({exc}), retrying ...", file=sys.stderr)
        time.sleep(poll_s)
    raise SystemExit(f"[{label}] timed out waiting for {health_url}")


def run_one(endpoint, label, concurrency, requests_per_worker, input_tokens, output_tokens, out_dir):
    out_file = os.path.join(out_dir, f"{label}_c{concurrency}.json")
    cmd = [
        sys.executable, os.path.join(os.path.dirname(__file__), "load_test.py"),
        "--endpoint", endpoint,
        "--concurrency", str(concurrency),
        "--requests-per-worker", str(requests_per_worker),
        "--input-tokens", str(input_tokens),
        "--output-tokens", str(output_tokens),
        "--output-file", out_file,
    ]
    print(f"[{label}] concurrency={concurrency} ...", file=sys.stderr)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    with open(out_file) as f:
        return json.load(f)


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    pre_args, _ = pre_parser.parse_known_args()
    env = load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(description=__doc__, parents=[pre_parser])
    parser.add_argument(
        "--rtx-endpoint",
        default=env.get("UNIFIED_RTX_ENDPOINT"),
        help="e.g. http://<unified-rtx-node-ip> (or set UNIFIED_RTX_ENDPOINT in benchmark.env)",
    )
    parser.add_argument(
        "--l4-endpoint",
        default=env.get("UNIFIED_L4_ENDPOINT"),
        help="e.g. http://<unified-l4-node-ip> (or set UNIFIED_L4_ENDPOINT in benchmark.env)",
    )
    parser.add_argument(
        "--requests-per-worker",
        type=int,
        default=int(env.get("REQUESTS_PER_WORKER", 5)),
    )
    parser.add_argument("--input-tokens", type=int, default=int(env.get("INPUT_TOKENS", 256)))
    parser.add_argument("--output-tokens", type=int, default=int(env.get("OUTPUT_TOKENS", 256)))
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "results"))
    args = parser.parse_args()

    missing = [
        name
        for name, value in (
            ("UNIFIED_RTX_ENDPOINT", args.rtx_endpoint),
            ("UNIFIED_L4_ENDPOINT", args.l4_endpoint),
        )
        if not value
    ]
    if missing:
        parser.error(
            "missing endpoint(s): "
            + ", ".join(missing)
            + f". Set them in {args.env_file} or pass --rtx-endpoint / --l4-endpoint."
        )

    os.makedirs(args.out_dir, exist_ok=True)
    wait_for_health(args.rtx_endpoint, "unified_rtx")
    wait_for_health(args.l4_endpoint, "unified_l4")

    all_results = []
    for concurrency in CONCURRENCY_LEVELS:
        for label, endpoint, deployment in [
            ("unified_rtx", args.rtx_endpoint, "unified_rtx"),
            ("unified_l4", args.l4_endpoint, "unified_l4"),
        ]:
            summary = run_one(endpoint, label, concurrency, args.requests_per_worker,
                               args.input_tokens, args.output_tokens, args.out_dir)
            summary["deployment"] = label
            summary["cost_per_1m_tokens_usd"] = cost_per_million_tokens(deployment, summary["tokens_per_sec"])
            all_results.append(summary)
            print(f"  -> {summary['tokens_per_sec']:.1f} tok/s, "
                  f"p50={summary['latency_p50_s']:.2f}s p95={summary['latency_p95_s']:.2f}s "
                  f"p99={summary['latency_p99_s']:.2f}s, "
                  f"${summary['cost_per_1m_tokens_usd']:.2f}/1M tok, "
                  f"errors={summary['num_errors']}", file=sys.stderr)

    combined_path = os.path.join(args.out_dir, "combined_results.json")
    with open(combined_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Wrote {combined_path}")


if __name__ == "__main__":
    main()
