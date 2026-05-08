#!/usr/bin/env bash
# infra/setup.sh — AtlasOps one-shot GCP provisioning
# Usage: bash infra/setup.sh <PROJECT_ID> [REGION] [CLUSTER_NAME]
#
# Prerequisites (run once before this script):
#   gcloud auth login
#   gcloud auth application-default login
#   gcloud components install gke-gcloud-auth-plugin kubectl
#
# Estimated time: ~20 min on a fresh GCP project
set -euo pipefail

PROJECT="${1:?Usage: $0 <PROJECT_ID> [REGION] [CLUSTER_NAME]}"
REGION="${2:-us-central1}"
CLUSTER="${3:-atlasops}"
BOUTIQUE_VERSION="v0.10.0"

echo "=== AtlasOps — Provisioning GCP Infrastructure ==="
echo "  Project : $PROJECT"
echo "  Region  : $REGION"
echo "  Cluster : $CLUSTER"
echo ""

# ── 0. Project setup ──────────────────────────────────────────────────────────
gcloud config set project "$PROJECT"
gcloud services enable \
  container.googleapis.com \
  sqladmin.googleapis.com \
  pubsub.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT"

echo "[1/8] GCP APIs enabled"

# ── 1. GKE Standard cluster ───────────────────────────────────────────────────
# IMPORTANT: Must be Standard, NOT Autopilot.
# Chaos Mesh requires privileged pods, hostPID, and hostPath mounts — all
# blocked by GKE Autopilot's Warden admission controller.
if ! gcloud container clusters describe "$CLUSTER" --region="$REGION" --project="$PROJECT" &>/dev/null; then
  gcloud container clusters create "$CLUSTER" \
    --region="$REGION" \
    --project="$PROJECT" \
    --machine-type=e2-standard-4 \
    --num-nodes=1 \
    --release-channel=stable \
    --workload-pool="${PROJECT}.svc.id.goog"
  echo "[2/8] GKE Standard cluster created: $CLUSTER (3× e2-standard-4)"
else
  echo "[2/8] GKE cluster already exists — skipping"
fi

gcloud container clusters get-credentials "$CLUSTER" --region="$REGION" --project="$PROJECT"
echo "      kubectl context set to GKE cluster"

# ── 2. Online Boutique (Google's reference app — 11 real microservices) ───────
echo "[3/8] Deploying Online Boutique $BOUTIQUE_VERSION..."
kubectl apply -f \
  "https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/refs/tags/${BOUTIQUE_VERSION}/release/kubernetes-manifests.yaml"

echo "      Waiting for Online Boutique pods to be Running (up to 5 min)..."
kubectl wait --for=condition=ready pod -l app=frontend --timeout=300s 2>/dev/null || \
  echo "      Warning: frontend pod not ready yet, continuing"

# ── 3. Cloud SQL (Postgres 15) — real managed database ───────────────────────
DB_INSTANCE="AtlasOps-cart-db"
if ! gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT" &>/dev/null; then
  gcloud sql instances create "$DB_INSTANCE" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --project="$PROJECT" \
    --storage-type=SSD \
    --storage-size=10GB \
    --no-backup
  gcloud sql databases create sre_events --instance="$DB_INSTANCE" --project="$PROJECT"
  echo "[4/8] Cloud SQL Postgres instance created: $DB_INSTANCE"
else
  echo "[4/8] Cloud SQL instance already exists — skipping"
fi

# ── 4. Cloud PubSub — real message queue ─────────────────────────────────────
gcloud pubsub topics create AtlasOps-checkout-events --project="$PROJECT" 2>/dev/null || true
gcloud pubsub topics create AtlasOps-alerts --project="$PROJECT" 2>/dev/null || true
gcloud pubsub subscriptions create AtlasOps-checkout-sub \
  --topic=AtlasOps-checkout-events \
  --project="$PROJECT" \
  --ack-deadline=60 2>/dev/null || true
gcloud pubsub subscriptions create AtlasOps-alerts-sub \
  --topic=AtlasOps-alerts \
  --project="$PROJECT" \
  --ack-deadline=60 2>/dev/null || true
echo "[5/8] Cloud PubSub topics + subscriptions created"

# ── 5. Helm repos ─────────────────────────────────────────────────────────────
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add jaegertracing          https://jaegertracing.github.io/helm-charts
helm repo add argo                   https://argoproj.github.io/argo-helm
helm repo add chaos-mesh             https://charts.chaos-mesh.org
helm repo update
echo "[6/8] Helm repos updated"

# ── 6. Prometheus + Grafana (kube-prometheus-stack) ──────────────────────────
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Pre-create Alertmanager config as Secret because kube-prometheus-stack
# alertmanager.alertmanagerSpec.configSecret expects a Secret name.
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-AtlasOps-config
  namespace: monitoring
stringData:
  alertmanager.yaml: |
    global:
      resolve_timeout: 5m
    route:
      group_by: ['alertname', 'namespace']
      receiver: AtlasOps-coordinator
    receivers:
    - name: AtlasOps-coordinator
      webhook_configs:
      - url: 'http://AtlasOps-coordinator-svc.default.svc.cluster.local:9099/webhook'
        send_resolved: true
EOF

helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values infra/values/kube-prometheus-stack.yaml \
  --wait --timeout=5m
echo "      Prometheus + Grafana deployed"

# ── 7. Jaeger + OTel Collector ────────────────────────────────────────────────
kubectl create namespace tracing --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install jaeger jaegertracing/jaeger \
  --namespace tracing \
  --values infra/values/jaeger.yaml \
  --wait --timeout=5m
echo "      Jaeger deployed"

# ── 8. Argo CD ────────────────────────────────────────────────────────────────
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --values infra/values/argocd.yaml \
  --wait --timeout=5m
echo "      Argo CD deployed"

# ── 9. Chaos Mesh ─────────────────────────────────────────────────────────────
kubectl create namespace chaos-mesh --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --values infra/values/chaos-mesh.yaml \
  --set chaosDaemon.runtime=containerd \
  --wait --timeout=5m
echo "      Chaos Mesh deployed"

# ── 10. Linkerd service mesh ──────────────────────────────────────────────────
if ! command -v linkerd &>/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSfL https://run.linkerd.io/install | sh
  export PATH="$HOME/.linkerd2/bin:$PATH"
fi
linkerd check --pre 2>/dev/null || true
linkerd install --crds | kubectl apply -f -
linkerd install | kubectl apply -f -
linkerd check 2>/dev/null || echo "      Warning: Linkerd check had issues, continuing"
echo "[6/8] Linkerd service mesh deployed"

# ── 11. Alertmanager webhook config verification ──────────────────────────────
echo "      Alertmanager webhook secret configured: alertmanager-AtlasOps-config"

echo ""
echo "=== [8/8] AtlasOps Infrastructure Ready ==="
echo ""
echo "Verify with:"
echo "  kubectl get pods -A"
echo "  make chaos SCENARIO=sf-001"
echo ""

# Print service endpoints
echo "=== Service Endpoints ==="
echo -n "  Grafana:     "
kubectl get svc -n monitoring prometheus-grafana -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null && echo ":80" || echo "(pending — check: kubectl get svc -n monitoring)"
echo -n "  Jaeger UI:   "
kubectl get svc -n tracing jaeger-query -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null && echo ":16686" || echo "(pending)"
echo -n "  Argo CD:     "
kubectl get svc -n argocd argocd-server -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null && echo ":443" || echo "(pending)"
echo ""
echo "Set budget alert: gcloud billing budgets create --billing-account=<ACCOUNT_ID> --display-name=atlasops-budget --budget-amount=50USD"
