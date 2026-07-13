#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — set up the GCP disaggregated cluster only (cpu / prefill / decode).
#
# The unified RTX PRO 6000 baseline runs on Vast.ai and is reached via local SSH
# tunnel (see README / benchmark.env) — it is NOT deployed by this script.
#
# Usage: ./cluster/deploy.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/deploy.env"

: "${PROJECT_ID:?set in cluster/deploy.env}"
: "${ZONE:?set in cluster/deploy.env}"
: "${CPU_NODE:?set in cluster/deploy.env}"
: "${PREFILL_NODE:?set in cluster/deploy.env}"
: "${DECODE_NODE:?set in cluster/deploy.env}"

GCLOUD_SSH=(gcloud compute ssh --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)
GCLOUD_SCP=(gcloud compute scp --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)

CLUSTER_ENV="${SCRIPT_DIR}/../config/cluster.env"
DECODE_NODES="${DECODE_NODE}"
cat > "${CLUSTER_ENV}" <<EOF
export PROJECT_ID="${PROJECT_ID}"
export ZONE="${ZONE}"

export CPU_NODE="${CPU_NODE}"
export PREFILL_NODE="${PREFILL_NODE}"
export DECODE_NODE="${DECODE_NODE}"

export CPU_NODE_HOST="${CPU_NODE}"
export PREFILL_NODE_HOST="${PREFILL_NODE}"
export DECODE_NODE_HOST="${DECODE_NODE}"
export DECODE_NODES="${DECODE_NODES}"

export MODEL_GCS_PATH="gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8"
export MODEL_LOCAL_DIR="/mnt/models/qwen2.5-72b-instruct-fp8"

export SGLANG_DOCKER_IMAGE="lmsysorg/sglang:v0.5.13-cu129"
export SGLANG_DOCKER_SHM_SIZE="32g"
export SGLANG_TP_SIZE=4
export SGLANG_MEM_FRACTION=0.85
export DISAGG_TRANSFER_BACKEND="mooncake_tcp"
export DISAGG_BOOTSTRAP_PORT=9000

export PREFILL_WORKER_PORT=30000
export DECODE_WORKER_PORT=30001
export ROUTER_PORT=8000
export NGINX_PORT=80
EOF
echo "Rendered ${CLUSTER_ENV} from deploy.env"

push_cluster_env() {
  local instance="$1"
  echo ">>> [${instance}] pushing cluster.env"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo mkdir -p /opt/runara/config"
  "${GCLOUD_SCP[@]}" "${CLUSTER_ENV}" "${instance}:/tmp/cluster.env"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo mv /tmp/cluster.env /opt/runara/config/cluster.env"
}

push_and_run_setup() {
  local instance="$1" script="$2"
  echo ">>> [${instance}] pushing and running $(basename "${script}")"
  "${GCLOUD_SCP[@]}" "${script}" "${instance}:/tmp/setup.sh"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo bash /tmp/setup.sh"
}

setup_instance() {
  local instance="$1" script="${SCRIPT_DIR}/startup-scripts/$2"
  push_cluster_env "${instance}"
  push_and_run_setup "${instance}" "${script}"
}

echo "=== Setting up cpu-node (${CPU_NODE}) ==="
setup_instance "${CPU_NODE}" "cpu-node-startup.sh"

echo "=== Setting up prefill-node (${PREFILL_NODE}) ==="
setup_instance "${PREFILL_NODE}" "prefill-node-startup.sh"

echo "=== Setting up decode-node (${DECODE_NODE}) ==="
setup_instance "${DECODE_NODE}" "decode-node-startup.sh"

echo "=== GCP PD cluster configured. Bringing cluster up in order... ==="
echo "NOTE: RTX unified baseline is on Vast.ai — open the SSH tunnel before benchmarking."
exec "${SCRIPT_DIR}/orchestrate.sh" up
