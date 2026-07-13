# Qwen2.5-72B-Instruct FP8 — unified Vast.ai RTX vs unified GCP L4

Compare two **unified** deployments of the same checkpoint:

| Role | Where | Machine / GPU | TP |
| --- | --- | --- | --- |
| Unified baseline | Vast.ai | 1× RTX PRO 6000 | 1 |
| Unified L4 | GCP | `g2-standard-48` (4× L4) | 4 |

```
  Vast.ai (baseline)                    GCP
  ┌─────────────────────────┐           ┌─────────────────────────┐
  │ 1x RTX PRO 6000 (tp=1)  │           │ unified-l4-node          │
  │ SGLang on :8080         │           │ g2-standard-48           │
  └───────────▲─────────────┘           │ 4x L4 (tp=4)             │
              │ SSH tunnel              │ nginx :80 + SGLang :30000│
  laptop :8080                          └─────────────────────────┘
```

GCP model: `gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8/`.
Project: `main-entropy-495701-p6`.

## Vast.ai RTX baseline (tunnel)

```bash
ssh -p 19270 root@99.148.65.9 -L 8080:localhost:8080
```

Benchmark hits `http://127.0.0.1:8080`. SGLang on Vast must listen on **8080**.

## GCP 4× L4 unified node

```bash
gcloud compute instances create unified-l4-node \
  --project=main-entropy-495701-p6 --zone=us-central1-a \
  --machine-type=g2-standard-48 --maintenance-policy=TERMINATE \
  --image-family=runara-base-sglang --image-project=main-entropy-495701-p6

chmod +x cluster/deploy.sh
./cluster/deploy.sh
```

`deploy.sh` only sets up the GCP L4 node — not the Vast RTX box.

## Benchmark

```bash
# Terminal 1 — keep tunnel up
ssh -p 19270 root@99.148.65.9 -L 8080:localhost:8080

# Terminal 2
gcloud compute instances describe unified-l4-node --zone=us-central1-a \
  --project=main-entropy-495701-p6 \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

pip install -r benchmark/requirements.txt
# edit benchmark/benchmark.env — set UNIFIED_L4_ENDPOINT (RTX already localhost:8080)
python3 benchmark/run_benchmark.py
python3 benchmark/plot_results.py --baseline-hourly <vast_rtx_$/hr>
```

```text
break_even_l4_$/hr = vast_rtx_$/hr * (tps_l4 / tps_rtx)
```

Outputs: `combined_results.json`, `breakeven.json`, plots under `benchmark/results/`.

## Layout

```
cluster/deploy.env                              # GCP L4 node only
cluster/deploy.sh
cluster/startup-scripts/unified-l4-node-startup.sh
benchmark/benchmark.env                         # RTX=127.0.0.1:8080, L4=GCP IP
benchmark/cost_model.py                         # Vast.ai baseline $/hr
```
