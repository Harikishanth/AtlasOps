#!/usr/bin/env bash
# infra/teardown.sh — AtlasOps GCP resource cleanup
# Usage: bash infra/teardown.sh <PROJECT_ID> [REGION] [CLUSTER_NAME]
set -euo pipefail

PROJECT="${1:?Usage: $0 <PROJECT_ID> [REGION] [CLUSTER_NAME]}"
REGION="${2:-us-central1}"
CLUSTER="${3:-atlasops}"
DB_INSTANCE="AtlasOps-cart-db"

echo "=== AtlasOps — Tearing Down GCP Infrastructure ==="
echo "  Project : $PROJECT"
echo "  Region  : $REGION"
echo "  Cluster : $CLUSTER"
echo ""
echo "WARNING: This will delete ALL AtlasOps resources. Press Ctrl+C within 10s to abort."
sleep 10

gcloud config set project "$PROJECT"

# Delete GKE cluster (also removes all in-cluster resources: Prometheus, Jaeger, Argo CD, etc.)
if gcloud container clusters describe "$CLUSTER" --region="$REGION" --project="$PROJECT" &>/dev/null; then
  gcloud container clusters delete "$CLUSTER" \
    --region="$REGION" \
    --project="$PROJECT" \
    --quiet
  echo "[1/4] GKE cluster deleted: $CLUSTER"
else
  echo "[1/4] GKE cluster not found — skipping"
fi

# Delete Cloud SQL instance
if gcloud sql instances describe "$DB_INSTANCE" --project="$PROJECT" &>/dev/null; then
  gcloud sql instances delete "$DB_INSTANCE" \
    --project="$PROJECT" \
    --quiet
  echo "[2/4] Cloud SQL instance deleted: $DB_INSTANCE"
else
  echo "[2/4] Cloud SQL instance not found — skipping"
fi

# Delete PubSub subscriptions + topics
for sub in AtlasOps-checkout-sub AtlasOps-alerts-sub; do
  gcloud pubsub subscriptions delete "$sub" --project="$PROJECT" --quiet 2>/dev/null || true
done
for topic in AtlasOps-checkout-events AtlasOps-alerts; do
  gcloud pubsub topics delete "$topic" --project="$PROJECT" --quiet 2>/dev/null || true
done
echo "[3/4] PubSub topics and subscriptions deleted"

# Delete Artifact Registry repo if it exists
if gcloud artifacts repositories describe AtlasOps --location="$REGION" --project="$PROJECT" &>/dev/null; then
  gcloud artifacts repositories delete AtlasOps \
    --location="$REGION" \
    --project="$PROJECT" \
    --quiet
  echo "[4/4] Artifact Registry repo deleted"
else
  echo "[4/4] Artifact Registry repo not found — skipping"
fi

echo ""
echo "=== Teardown complete. Verify billing has stopped: ==="
echo "  gcloud billing accounts list"
echo "  gcloud projects describe $PROJECT"
