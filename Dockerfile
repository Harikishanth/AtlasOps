FROM python:3.11-slim
# cache-bust: 2026-05-10

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg && \
    # Install kubectl
    curl -fsSL "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
        -o /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    httpx requests jinja2 \
    google-cloud-monitoring google-cloud-logging google-cloud-pubsub \
    google-auth kubernetes rich python-dotenv \
    fastapi uvicorn[standard] aiofiles pydantic

COPY . .

# HF Spaces runs as user 1000 — ensure data dirs are writable
RUN mkdir -p data docs/postmortems && chmod -R 777 data docs

# HF Spaces port
EXPOSE 7860

# ── HF Space Secrets (minimal — see docs/HF_SPACE_SETUP.md) ───────────────────
#   HF_TOKEN=<read + inference capable>
#   ATLASOPS_USE_HF_INFERENCE=1
#   AGENT_MODEL=your-org/merged-atlasops-7b-grpo      # Hub id after merging LoRA
#   JUDGE_MODEL=Qwen/Qwen2.5-72B-Instruct-AWQ         # or a smaller HF id Router allows
# Optional: ATLASOPS_LIVE_JUDGE=1|0                     (defaults ON when inference pack enabled)
#
# Comms out (optional):
#   DISCORD_WEBHOOK_URL   # Server Settings → Integrations → Webhooks → channel URL
#   SLACK_WEBHOOK_URL

# Existing cluster / Grafana wiring:
#   PROMETHEUS_URL, ALERTMANAGER_URL, JAEGER_URL, GRAFANA_URL, ARGOCD_URL, BOUTIQUE_URL
#   ATLASOPS_API_KEY, ALERTMANAGER_WEBHOOK_SECRET
# If kubectl cannot reach GKE from this container (typical HF Space):
#   ATLASOPS_SKIP_KUBECTL_INJECT=1

CMD ["python", "app.py"]
