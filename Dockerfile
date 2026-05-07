FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    httpx requests jinja2 \
    google-cloud-monitoring google-cloud-logging google-cloud-pubsub \
    google-auth kubernetes rich python-dotenv \
    fastapi uvicorn[standard] aiofiles

COPY . .

# HF Spaces port
EXPOSE 7860

# Env vars via HF Space Secrets:
#   BACKEND, LLM_API_KEY, AGENT_MODEL, VLLM_BASE, JUDGE_URL
#   GCP_PROJECT, USE_GKE_GCLOUD_AUTH_PLUGIN
#   PROMETHEUS_URL, JAEGER_URL, ALERTMANAGER_URL
#   SLACK_WEBHOOK_URL (optional)

CMD ["python", "app.py"]
