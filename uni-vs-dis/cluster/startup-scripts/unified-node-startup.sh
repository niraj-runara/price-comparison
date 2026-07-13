#!/usr/bin/env bash
# ==============================================================================
# Setup script for `unified-node` — the non-disaggregated baseline.
# g4-standard-48, 1x NVIDIA RTX PRO 6000, tp-size 1.
#
# Then run cluster/deploy-unified.sh — it pushes config/cluster.env and runs
# this script for you over SSH (without touching the disaggregated cluster).
#
# Idempotent — safe to re-run any time.
# ==============================================================================
set -euo pipefail

if [ ! -f /opt/runara/config/cluster.env ]; then
  echo "ERROR: /opt/runara/config/cluster.env not found. Run cluster/deploy-unified.sh" \
       "from your workstation first — it stages this file before running this script." >&2
  exit 1
fi

mkdir -p /opt/runara/bin /opt/runara/config

cat > /opt/runara/bin/run_model_sync.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source /opt/runara/config/cluster.env
mkdir -p "${MODEL_LOCAL_DIR}"
echo "Syncing model weights from ${MODEL_GCS_PATH} to ${MODEL_LOCAL_DIR} ..."
gcloud storage rsync -r "${MODEL_GCS_PATH}" "${MODEL_LOCAL_DIR}"
echo "Model sync complete."
EOF
chmod +x /opt/runara/bin/run_model_sync.sh

cat > /etc/systemd/system/model-sync.service <<'EOF'
[Unit]
Description=Sync Qwen2.5-72B-Instruct FP8 weights from GCS
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/runara/bin/run_model_sync.sh
RemainAfterExit=yes
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------------------------------------------------------
# Combined (non-disaggregated) SGLang server — 1x RTX PRO 6000
# ---------------------------------------------------------------------------
cat > /opt/runara/bin/run_unified_server.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source /opt/runara/config/cluster.env
docker rm -f sglang-unified 2>/dev/null || true
exec docker run --name sglang-unified \
  --gpus all \
  --network host \
  --shm-size "${SGLANG_DOCKER_SHM_SIZE}" \
  -v "${MODEL_LOCAL_DIR}:${MODEL_LOCAL_DIR}:ro" \
  "${SGLANG_DOCKER_IMAGE}" \
  python3 -m sglang.launch_server \
  --model-path "${MODEL_LOCAL_DIR}" \
  --host 0.0.0.0 \
  --port "${UNIFIED_SERVER_PORT}" \
  --tp-size "${UNIFIED_TP_SIZE}" \
  --mem-fraction-static "${SGLANG_MEM_FRACTION}" \
  --quantization fp8
EOF
chmod +x /opt/runara/bin/run_unified_server.sh

cat > /etc/systemd/system/unified-server.service <<'EOF'
[Unit]
Description=SGLang unified (combined prefill+decode) server
After=network-online.target model-sync.service
Requires=model-sync.service
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/opt/runara/bin/run_unified_server.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------------------------------------------------------
# nginx: expose on port 80 too, so unified and disaggregated share the same
# "http://<ip>" convention for the benchmark client.
# ---------------------------------------------------------------------------
if ! command -v nginx >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y nginx
fi

cat > /etc/nginx/sites-available/runara-unified <<'EOF'
upstream runara_unified {
    server 127.0.0.1:30000;
}

server {
    listen 80 default_server;

    location / {
        proxy_pass http://runara_unified;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/runara-unified /etc/nginx/sites-enabled/runara-unified
nginx -t

systemctl daemon-reload
systemctl enable --now model-sync.service
systemctl enable --now unified-server.service
systemctl enable --now nginx

echo "unified-node startup script complete."
