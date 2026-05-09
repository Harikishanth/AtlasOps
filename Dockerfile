FROM python:3.11-slim

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

# Env vars to configure via HF Space Secrets:
#   BACKEND=openai
#   VLLM_BASE=https://router.huggingface.co/v1
#   LLM_API_KEY=hf_xxx
#   AGENT_MODEL=Qwen/Qwen2.5-7B-Instruct
#   PROMETHEUS_URL, ALERTMANAGER_URL, JAEGER_URL  (GKE LoadBalancer IPs)
#   GRAFANA_URL, ARGOCD_URL, BOUTIQUE_URL
#   ATLASOPS_API_KEY, ALERTMANAGER_WEBHOOK_SECRET

CMD ["python", "app.py"]
