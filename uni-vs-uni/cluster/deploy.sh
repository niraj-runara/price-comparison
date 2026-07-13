#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — set up both unified baselines:
#   unified-rtx-node  (g4-standard-48, 1x RTX PRO 6000, tp=1)
#   unified-l4-node   (g2-standard-48, 4x L4, tp=4)
#
# Usage: ./cluster/deploy.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/deploy.env"

: "${PROJECT_ID:?set in cluster/deploy.env}"
: "${ZONE:?set in cluster/deploy.env}"
: "${UNIFIED_RTX_NODE:?set in cluster/deploy.env}"
: "${UNIFIED_L4_NODE:?set in cluster/deploy.env}"

GCLOUD_SSH=(gcloud compute ssh --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)
GCLOUD_SCP=(gcloud compute scp --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)

CLUSTER_ENV="${SCRIPT_DIR}/../config/cluster.env"
cat > "${CLUSTER_ENV}" <<EOF
export PROJECT_ID="${PROJECT_ID}"
export ZONE="${ZONE}"

export UNIFIED_RTX_NODE="${UNIFIED_RTX_NODE}"
export UNIFIED_L4_NODE="${UNIFIED_L4_NODE}"
export UNIFIED_RTX_NODE_HOST="${UNIFIED_RTX_NODE}"
export UNIFIED_L4_NODE_HOST="${UNIFIED_L4_NODE}"

export MODEL_GCS_PATH="gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8"
export MODEL_LOCAL_DIR="/mnt/models/qwen2.5-72b-instruct-fp8"

export SGLANG_DOCKER_IMAGE="lmsysorg/sglang:v0.5.13-cu129"
export SGLANG_DOCKER_SHM_SIZE="32g"
export UNIFIED_RTX_TP_SIZE=1
export UNIFIED_L4_TP_SIZE=4
export SGLANG_MEM_FRACTION=0.85

export UNIFIED_SERVER_PORT=30000
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

setup_instance() {
  local instance="$1" script="$2"
  push_cluster_env "${instance}"
  echo ">>> [${instance}] pushing and running $(basename "${script}")"
  "${GCLOUD_SCP[@]}" "${script}" "${instance}:/tmp/setup.sh"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo bash /tmp/setup.sh"
}

wait_health() {
  local instance="$1"
  echo ">>> [${instance}] waiting for /health (up to 30 min for model sync + load)"
  "${GCLOUD_SSH[@]}" "${instance}" --command \
    "curl -fsS -o /dev/null --retry-connrefused --retry 600 --retry-delay 3 --retry-max-time 1800 -m 5 http://127.0.0.1:30000/health"
}

echo "=== Setting up unified-rtx-node (${UNIFIED_RTX_NODE}) ==="
setup_instance "${UNIFIED_RTX_NODE}" "${SCRIPT_DIR}/startup-scripts/unified-rtx-node-startup.sh"

echo "=== Setting up unified-l4-node (${UNIFIED_L4_NODE}) ==="
setup_instance "${UNIFIED_L4_NODE}" "${SCRIPT_DIR}/startup-scripts/unified-l4-node-startup.sh"

echo "=== Starting services ==="
for instance in "${UNIFIED_RTX_NODE}" "${UNIFIED_L4_NODE}"; do
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo systemctl restart model-sync.service"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo systemctl restart unified-server.service"
  "${GCLOUD_SSH[@]}" "${instance}" --command "sudo systemctl reload nginx || sudo systemctl restart nginx"
done

wait_health "${UNIFIED_RTX_NODE}"
wait_health "${UNIFIED_L4_NODE}"

echo "Both unified nodes are up on port 80 (nginx) and 30000 (direct)."
