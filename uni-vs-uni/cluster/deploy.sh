#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — set up the GCP unified 4x L4 node only.
#
# The RTX PRO 6000 baseline runs on Vast.ai and is reached via local SSH tunnel
# (see README / benchmark.env) — it is NOT deployed by this script.
#
# Usage: ./cluster/deploy.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/deploy.env"

: "${PROJECT_ID:?set in cluster/deploy.env}"
: "${ZONE:?set in cluster/deploy.env}"
: "${UNIFIED_L4_NODE:?set in cluster/deploy.env}"

GCLOUD_SSH=(gcloud compute ssh --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)
GCLOUD_SCP=(gcloud compute scp --zone="${ZONE}" --project="${PROJECT_ID}" --tunnel-through-iap)

CLUSTER_ENV="${SCRIPT_DIR}/../config/cluster.env"
cat > "${CLUSTER_ENV}" <<EOF
export PROJECT_ID="${PROJECT_ID}"
export ZONE="${ZONE}"

export UNIFIED_L4_NODE="${UNIFIED_L4_NODE}"
export UNIFIED_L4_NODE_HOST="${UNIFIED_L4_NODE}"

export MODEL_GCS_PATH="gs://gcp-models-bucket/qwen2.5-72b-instruct-fp8"
export MODEL_LOCAL_DIR="/mnt/models/qwen2.5-72b-instruct-fp8"

export SGLANG_DOCKER_IMAGE="lmsysorg/sglang:v0.5.13-cu129"
export SGLANG_DOCKER_SHM_SIZE="32g"
export UNIFIED_L4_TP_SIZE=4
export SGLANG_MEM_FRACTION=0.85

export UNIFIED_SERVER_PORT=30000
export NGINX_PORT=80
EOF
echo "Rendered ${CLUSTER_ENV} from deploy.env"

echo "=== Setting up unified-l4-node (${UNIFIED_L4_NODE}) ==="
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo mkdir -p /opt/runara/config"
"${GCLOUD_SCP[@]}" "${CLUSTER_ENV}" "${UNIFIED_L4_NODE}:/tmp/cluster.env"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo mv /tmp/cluster.env /opt/runara/config/cluster.env"
"${GCLOUD_SCP[@]}" "${SCRIPT_DIR}/startup-scripts/unified-l4-node-startup.sh" "${UNIFIED_L4_NODE}:/tmp/setup.sh"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo bash /tmp/setup.sh"

echo ">>> [${UNIFIED_L4_NODE}] restarting model sync + unified server"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo systemctl restart model-sync.service"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo systemctl restart unified-server.service"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command "sudo systemctl reload nginx || sudo systemctl restart nginx"

echo ">>> [${UNIFIED_L4_NODE}] waiting for /health (up to 30 min for model sync + load)"
"${GCLOUD_SSH[@]}" "${UNIFIED_L4_NODE}" --command \
  "curl -fsS -o /dev/null --retry-connrefused --retry 600 --retry-delay 3 --retry-max-time 1800 -m 5 http://127.0.0.1:30000/health"

echo "GCP unified L4 node is up on port 80 (nginx) and 30000 (direct)."
echo "NOTE: RTX baseline is on Vast.ai — open the SSH tunnel before benchmarking."
