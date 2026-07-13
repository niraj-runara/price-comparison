# Qwen2.5-72B-Instruct FP8 — unified (Vast.ai) vs disaggregated (GCP)

Compare a **Vast.ai** 1× RTX PRO 6000 unified baseline against a **GCP**
prefill/decode disaggregated cluster (4× L4 each).

## Architecture

```
  Vast.ai (baseline)                          GCP (disaggregated)
  ┌─────────────────────────┐                 ┌─────────────────────────────┐
  │ 1x RTX PRO 6000 (tp=1)  │                 │  cpu-node (n2-standard-8)    │
  │ SGLang on :8080         │                 │  nginx :80 / router :8000    │
  └───────────▲─────────────┘                 └───────────┬─────────┬────────┘
              │ SSH -L 8080:localhost:8080                 │         │
              │                            prefill:30000  │         │ decode:30001
  laptop :8080                             ┌──────────────▼──┐   ┌──▼──────────────┐
                                           │ prefill-node     │   │ decode-node      │
                                           │ g2-standard-48   │   │ g2-standard-48   │
                                           │ 4x L4 (tp=4)     │   │ 4x L4 (tp=4)     │
                                           └──────────────────┘   └──────────────────┘
```

| Role | Where | Machine / GPU | TP |
| --- | --- | --- | --- |
| Unified baseline | Vast.ai | 1× RTX PRO 6000 | 1 |
| Prefill | GCP | `g2-standard-48` (4× L4) | 4 |
| Decode | GCP | `g2-standard-48` (4× L4) | 4 |
| Router / nginx | GCP | `n2-standard-8` | — |

GCP model weights: `gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8/` →
`/mnt/models/qwen2.5-72b-instruct-fp8`. Project: `main-entropy-495701-p6`.

## Vast.ai RTX baseline (tunnel)

Keep this tunnel open while benchmarking (forwards local `8080` → instance `8080`):

```bash
ssh -p 19270 root@99.148.65.9 -L 8080:localhost:8080
```

Benchmark client hits `http://127.0.0.1:8080` (see `benchmark/benchmark.env`).
SGLang on the Vast box must be listening on port **8080**.

## GCP disaggregated cluster

```bash
gcloud compute instances create cpu-node \
  --project=main-entropy-495701-p6 --zone=us-central1-a \
  --machine-type=n2-standard-8 --image-family=runara-base-sglang \
  --image-project=main-entropy-495701-p6

gcloud compute instances create prefill-node decode-node \
  --project=main-entropy-495701-p6 --zone=us-central1-a \
  --machine-type=g2-standard-48 --maintenance-policy=TERMINATE \
  --image-family=runara-base-sglang --image-project=main-entropy-495701-p6

chmod +x cluster/deploy.sh cluster/orchestrate.sh
./cluster/deploy.sh
./cluster/orchestrate.sh status
```

`deploy.sh` only configures GCP cpu/prefill/decode — not the Vast RTX box.

## Benchmark

```bash
# Terminal 1 — keep tunnel up
ssh -p 19270 root@99.148.65.9 -L 8080:localhost:8080

# Terminal 2 — set DISAGGREGATED_ENDPOINT to cpu-node IP, then:
pip install -r benchmark/requirements.txt
# edit benchmark/benchmark.env if needed (UNIFIED_ENDPOINT already localhost:8080)
python3 benchmark/run_benchmark.py
python3 benchmark/plot_results.py --baseline-hourly <vast_rtx_$/hr>
```

Get cpu-node IP:

```bash
gcloud compute instances describe cpu-node --zone=us-central1-a \
  --project=main-entropy-495701-p6 \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Cost analysis is post-hoc: hardcode / pass the **Vast.ai** RTX `$/hr`, then
solve for disaggregated break-even `$/hr`:

```text
break_even_disagg_$/hr = vast_rtx_$/hr * (tps_disagg / tps_unified)
```

Outputs: `combined_results.json`, `breakeven.json`, throughput / latency /
`break_even_hourly.png` under `benchmark/results/`.

## Layout

```
cluster/deploy.env                        # GCP project, zone, instance names
cluster/deploy.sh                         # deploy GCP PD cluster only
cluster/orchestrate.sh                    # up | down | status | restart
cluster/startup-scripts/{cpu,prefill,decode}-node-startup.sh
benchmark/benchmark.env                   # UNIFIED=127.0.0.1:8080, DISAGG=GCP IP
benchmark/cost_model.py                   # Vast.ai baseline $/hr + break-even helpers
```
