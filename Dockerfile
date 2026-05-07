FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps (no train extras needed for HF Space)
COPY pyproject.toml .
RUN pip install --no-cache-dir gradio>=4.36.0 httpx requests jinja2 \
    google-cloud-monitoring google-cloud-logging google-cloud-pubsub \
    google-auth kubernetes rich python-dotenv fastapi uvicorn

COPY . .

# HF Spaces runs on port 7860
ENV GRADIO_SERVER_PORT=7860
ENV GRADIO_SERVER_NAME=0.0.0.0

# Env vars set via HF Space secrets:
#   GRAFANA_IP, BOUTIQUE_IP, ARGOCD_IP
#   BACKEND, LLM_API_KEY, AGENT_MODEL
#   GCP_PROJECT, USE_GKE_GCLOUD_AUTH_PLUGIN

EXPOSE 7860

CMD ["python", "dashboard.py"]
