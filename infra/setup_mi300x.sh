#!/usr/bin/env bash
# infra/setup_mi300x.sh — AtlasOps MI300X training environment setup
#
# Run this ONCE after SSHing into your AMD Developer Cloud GPU Droplet:
#   ssh root@<your-droplet-ip>
#   curl -fsSL https://raw.githubusercontent.com/Harikishanth/AtlasOps/main/infra/setup_mi300x.sh | bash
#
# Prerequisites on the droplet (pre-installed on AMD ROCm images):
#   - ROCm 6.x
#   - Python 3.11+
#   - git, curl
set -euo pipefail

echo "=== AtlasOps MI300X Setup ==="

# ── 1. Verify ROCm + MI300X ──────────────────────────────────────────────────
echo "[1/6] Verifying AMD hardware..."
rocm-smi --showproductname 2>/dev/null || { echo "ERROR: rocm-smi not found. Is this a ROCm image?"; exit 1; }
rocm-smi --showmeminfo vram 2>/dev/null | head -5
echo ""

# ── 2. Clone repo ─────────────────────────────────────────────────────────────
echo "[2/6] Cloning AtlasOps..."
if [ ! -d "AtlasOps" ]; then
  git clone https://github.com/Harikishanth/AtlasOps.git
fi
cd AtlasOps

# ── 3. Install Python dependencies ────────────────────────────────────────────
echo "[3/6] Installing dependencies (ROCm build)..."
pip install --upgrade pip
# Install base deps
pip install -e "." --quiet
# Install training deps with ROCm-compatible torch
pip install torch --index-url https://download.pytorch.org/whl/rocm6.2 --quiet
pip install -e ".[train]" --quiet
# Hugging Face Optimum-AMD — required for Track 2 (AMD GPU optimised inference + quantisation)
pip install optimum[amd] --quiet
# Install vLLM for serving (ROCm build)
pip install vllm --quiet || echo "Warning: vLLM install failed — will use HF transformers for inference"

# ── 4. Set up environment variables ───────────────────────────────────────────
echo "[4/6] Creating .env file..."
cat > .env << 'ENVEOF'
# ── GCP / GKE ───────────────────────────────────────────────────────────────
GCP_PROJECT=cloudsre-v3-amd

# These are set after gcloud auth — run:
#   gcloud container clusters get-credentials atlasops --region=us-central1 --project=cloudsre-v3-amd
# Then kubectl will work from this machine

# ── Prometheus (port-forward from laptop OR use LoadBalancer IP) ─────────────
PROMETHEUS_URL=http://136.119.60.129:80/prometheus
# If Grafana LB doesn't expose Prometheus, use:
# kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090 &
# PROMETHEUS_URL=http://localhost:9090

# ── Jaeger ───────────────────────────────────────────────────────────────────
# kubectl port-forward svc/jaeger-query -n tracing 16686:16686 &
JAEGER_URL=http://localhost:16686

# ── Alertmanager ─────────────────────────────────────────────────────────────
ALERTMANAGER_URL=http://localhost:9093

# ── LLM serving (set after vllm serve runs) ──────────────────────────────────
VLLM_BASE=http://localhost:8000/v1
JUDGE_URL=http://localhost:8001/v1
AGENT_MODEL=Qwen/Qwen2.5-7B-Instruct
JUDGE_MODEL=Qwen/Qwen2.5-72B-Instruct

# ── Slack (optional) ─────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=
ENVEOF
echo "      .env created — edit GCP_PROJECT and URLs as needed"

# ── 5. Download base models ───────────────────────────────────────────────────
echo "[5/6] Pre-downloading base models (7B + 72B)..."
python - << 'PYEOF'
from huggingface_hub import snapshot_download
import os
print("Downloading Qwen2.5-7B-Instruct (~15 GB)...")
snapshot_download("Qwen/Qwen2.5-7B-Instruct", ignore_patterns=["*.bin"])
print("Downloading Qwen2.5-72B-Instruct (~37 GB in 4-bit)...")
snapshot_download("Qwen/Qwen2.5-72B-Instruct-GGUF", ignore_patterns=["*.bin"])
print("Models downloaded.")
PYEOF

# ── 6. Print next steps ───────────────────────────────────────────────────────
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "=== NEXT STEPS ==="
echo ""
echo "Terminal 1 — Serve 7B agents:"
echo "  vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000 --dtype bfloat16 --enable-lora --max-lora-rank 16"
echo ""
echo "Terminal 2 — Serve 72B judge:"
echo "  vllm serve Qwen/Qwen2.5-72B-Instruct --port 8001 --dtype bfloat16"
echo ""
echo "Terminal 3 — Training pipeline:"
echo "  source .env"
echo "  make trajectories   # ~3 hours (generates SFT corpus from real GKE)"
echo "  make sft            # ~2 hours (QLoRA SFT)"
echo "  make grpo           # ~4 hours (GRPO with Optuna)"
echo "  make bench          # ~1 hour  (benchmark + comparison table)"
echo ""
echo "Evidence capture:"
echo "  rocm-smi --showproductname --showmeminfo vram > docs/MI300X_EVIDENCE.md"
echo "  rocm-smi --showpids >> docs/MI300X_EVIDENCE.md"
echo ""
echo "=== rocm-smi snapshot ==="
rocm-smi 2>/dev/null || true
