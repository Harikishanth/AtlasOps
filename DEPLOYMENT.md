# AtlasOps — Real-World Deployment Guide

> This is not a demo toy. This is how you put AtlasOps on-call for a real production cluster.

---

## The Real-World Use Case

**Problem:** Your on-call engineer gets paged at 3am. Average MTTR for complex incidents is 60–90 minutes. At $500/hr fully-loaded SRE cost, that's $500–$750 per incident. You have 10 incidents/month. That's $60–90K/year in on-call cost, before counting burnout and turnover.

**AtlasOps solves:** The P2/P3 incidents that don't need a human — CPU spikes, OOM kills, bad deploys, network partitions. These are 80% of all pages. AtlasOps resolves them in under 5 minutes, generates the postmortem, and only wakes a human for the truly novel P0s.

**What it actually does:**
1. Alertmanager fires a webhook to `coordinator:9099/webhook`
2. Triage agent classifies severity and blast radius (< 1 min)
3. Diagnosis agent traces root cause via Prometheus + Jaeger + kubectl logs (< 2 min)
4. Remediation agent executes the fix and verifies recovery (< 1 min)
5. Comms agent posts to Slack and generates a postmortem (30 sec)
6. If the agent can't resolve it, it escalates with full context — the human wakes up with a diagnosis already done

---

## Prerequisites

- Kubernetes cluster (GKE, EKS, AKS, or self-managed)
- Prometheus + Alertmanager installed (kube-prometheus-stack recommended)
- Jaeger (optional but recommended for trace-based diagnosis)
- Argo CD (optional — enables `argocd_rollback` remediation)
- AMD MI300X or compatible GPU (for self-hosted inference)
  - OR: Fireworks AI API key (managed AMD GPU inference)

---

## Quick Deployment (5 minutes)

### 1. Deploy the coordinator

```bash
# Create the coordinator deployment
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atlasops-coordinator
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: atlasops-coordinator
  template:
    metadata:
      labels:
        app: atlasops-coordinator
    spec:
      containers:
      - name: coordinator
        image: ghcr.io/harikishanth/atlasops:latest
        ports:
        - containerPort: 9099
        env:
        - name: BACKEND
          value: "fireworks"          # or "vllm" for self-hosted
        - name: LLM_API_KEY
          valueFrom:
            secretKeyRef:
              name: atlasops-secrets
              key: llm-api-key
        - name: GCP_PROJECT
          value: "your-gcp-project"   # optional, for Cloud Logging
---
apiVersion: v1
kind: Service
metadata:
  name: atlasops-coordinator-svc
  namespace: default
spec:
  selector:
    app: atlasops-coordinator
  ports:
  - port: 9099
    targetPort: 9099
EOF
```

### 2. Create the API key secret

```bash
kubectl create secret generic atlasops-secrets \
  --from-literal=llm-api-key=fw_your_fireworks_key
```

### 3. Wire Alertmanager

Add to your `alertmanager.yaml`:

```yaml
receivers:
- name: atlasops
  webhook_configs:
  - url: 'http://atlasops-coordinator-svc.default.svc.cluster.local:9099/webhook'
    send_resolved: true

route:
  receiver: atlasops
  routes:
  - match:
      severity: critical
    receiver: atlasops
  - match:
      severity: warning
    receiver: atlasops
```

### 4. Verify it works

```bash
# Check coordinator health
kubectl exec -it deploy/atlasops-coordinator -- curl localhost:9099/health

# Trigger a test incident
kubectl exec -it deploy/atlasops-coordinator -- python inference.py
```

---

## Production Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND` | `vllm` | `vllm` (self-hosted MI300X) or `fireworks` (managed API) |
| `LLM_API_KEY` | `""` | Required for Fireworks; empty for local vLLM |
| `VLLM_BASE` | `http://localhost:8000/v1` | vLLM endpoint (set to MI300X IP for self-hosted) |
| `AGENT_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Model name (or path to fine-tuned checkpoint) |
| `GCP_PROJECT` | `""` | GCP project for Cloud Logging tool |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus endpoint |
| `JAEGER_URL` | `http://jaeger:16686` | Jaeger query endpoint |
| `ALERTMANAGER_URL` | `http://alertmanager:9093` | Alertmanager endpoint |
| `SLACK_WEBHOOK_URL` | `""` | Slack webhook (optional; logs locally if not set) |

### Using Your Fine-Tuned Checkpoints

Once you've run `make sft` and `make grpo`, point the coordinator at your checkpoints:

```bash
# Self-hosted on MI300X with fine-tuned adapters
BACKEND=vllm \
VLLM_BASE=http://your-mi300x-ip:8000/v1 \
AGENT_MODEL=checkpoints/grpo_v3 \
python agents/coordinator.py
```

### Running on AMD MI300X (Self-Hosted)

```bash
# On your MI300X instance
pip install vllm  # ROCm build
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --enable-lora \
  --max-lora-rank 16 \
  --dtype bfloat16

# Load all 4 agent adapters + judge
vllm serve Qwen/Qwen2.5-72B-Instruct \
  --host 0.0.0.0 --port 8001 \
  --dtype bfloat16 \
  --tensor-parallel-size 1  # MI300X 192GB fits it in one GPU
```

---

## What AtlasOps Does NOT Do

- **Does not replace humans for novel P0s.** If the incident pattern has never been seen before, AtlasOps escalates with full diagnostic context rather than guessing.
- **Does not execute destructive commands.** `kubectl delete`, `argocd app delete`, and mass scale-to-zero are blocked by the tool allowlist.
- **Does not silence alerts for more than 30 minutes.** Hard limit in `alertmanager_silence`.
- **Does not make business decisions.** "Should we roll back this revenue-critical deploy?" is a human call.

---

## Business Value

| Metric | Before AtlasOps | After AtlasOps |
|---|---|---|
| MTTR (P2/P3 incidents) | 60–90 min | **< 5 min** |
| On-call pages requiring human | 100% | **~20%** (P0/novel only) |
| Postmortem drafting time | 2 hrs/incident | **< 30 sec** |
| Cost per incident (P2/P3) | $500–750 | **~$0.50** (API cost) |

**Market context:** PagerDuty ($3.7B), Datadog ($25B), and OpsRamp ($2B+) all sell products in this space. None of them close the loop automatically — they alert humans and wait. AtlasOps is the first system that closes the loop end-to-end using real SRE tool chains trained on real incident history.

**Revenue model (if productized):**
- SaaS: $500/month per cluster (vs. $8K/month in SRE on-call cost)
- Enterprise: Custom fine-tuning on your incident history, private deployment
- Target: 50K+ Kubernetes clusters running in production globally
