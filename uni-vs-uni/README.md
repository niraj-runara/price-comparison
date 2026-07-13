# Qwen2.5-72B-Instruct FP8 — unified Vast.ai RTX vs unified GCP L4

| Role | Where | Machine / GPU | TP |
| --- | --- | --- | --- |
| Unified baseline | Vast.ai | 1× RTX PRO 6000 | 1 |
| Unified L4 | GCP | `g2-standard-48` (4× L4) | 4 |

GCP project: `main-entropy-495701-p6`, zone: `northamerica-northeast2-b`.
L4 VM uses stock **Ubuntu 22.04** + NVIDIA drivers + Docker +
`lmsysorg/sglang:latest`. Model from `gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8/`.

## Endpoints (current)

| Side | URL |
| --- | --- |
| Vast RTX (via tunnel) | `http://127.0.0.1:8080` |
| GCP 4× L4 | `http://34.130.185.86` (nginx :80 → SGLang :30000) |

## Benchmark

```bash
# Terminal 1 — Vast tunnel
ssh -p 19270 root@99.148.65.9 -L 8080:localhost:8080

# Terminal 2
cd uni-vs-uni
pip install -r benchmark/requirements.txt
# benchmark/benchmark.env already has both endpoints
python3 benchmark/run_benchmark.py
python3 benchmark/plot_results.py --baseline-hourly <vast_rtx_$/hr>
```

```text
break_even_l4_$/hr = vast_rtx_$/hr * (tps_l4 / tps_rtx)
```

## Recreate L4 VM (if needed)

```bash
gcloud compute instances create unified-l4-node \
  --project=main-entropy-495701-p6 --zone=northamerica-northeast2-b \
  --machine-type=g2-standard-48 --maintenance-policy=TERMINATE \
  --boot-disk-size=250GB --boot-disk-type=pd-balanced \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --scopes=cloud-platform --tags=sglang
```

Then: install `nvidia-driver-580-open`, Docker, nvidia-container-toolkit,
rsync model from GCS, `docker run` SGLang with `--tp-size 4
--disable-piecewise-cuda-graph`, nginx on :80.
