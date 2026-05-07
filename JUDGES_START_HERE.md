# Judges: Start Here — AtlasOps

> 60-second proof this runs on real infrastructure.

## Step 1 — Verify the live GKE cluster (run these yourself)

```bash
# Configure kubectl
gcloud container clusters get-credentials atlasops \
  --region=us-central1 --project=atlasops-amd

# 11 Online Boutique pods + full observability stack
kubectl get pods -A | grep -E "Running" | wc -l   # should be 65+

# Real Chaos Mesh CRDs installed
kubectl get crds | grep chaos-mesh    # 20+ CRDs

# Real Argo CD
kubectl get apps -n argocd
```

## Step 2 — Inject a real chaos scenario

```bash
# Kill cartservice — watch Grafana spike in real time
kubectl apply -f bench/chaos_manifests/single_fault/sf-001.yaml

# Check the kill happened
kubectl get pods -n default -l app=cartservice  # STATUS: Terminating → Running

# Clean up
kubectl delete podchaos sf-001-cartservice-kill -n chaos-mesh
```

## Step 3 — Open the Ops Console

```
http://136.119.60.129    ← Grafana (admin / AtlasOps-admin)
http://34.132.118.204    ← Online Boutique (live traffic)
https://34.122.132.237   ← Argo CD
```

Or run the dashboard locally:
```bash
pip install -e ".[dev]"
python dashboard.py      # opens on http://localhost:7860
```

## Step 4 — What the demo shows

1. Click **"Cloudflare 2019 — Regex CPU Storm"** in the Replays tab
2. Chaos Mesh injects StressChaos on `frontend` → CPU spikes in Grafana
3. Alertmanager fires → coordinator receives webhook at `:9099/webhook`
4. Four agents run in sequence: Triage → Diagnosis → Remediation → Comms
5. `argocd rollback` executes, Prometheus confirms error rate < 1%
6. Postmortem auto-saves to `docs/postmortems/`

## Step 5 — AMD MI300X evidence

See [docs/MI300X_EVIDENCE.md](docs/MI300X_EVIDENCE.md):
- `rocm-smi` showing 5 models co-hosted on single GPU (192 GB HBM3)
- vLLM serving logs: Qwen2.5-7B×4 agents + Qwen2.5-72B judge
- T4 OOM failure proof (comparison)
- Per-model throughput benchmarks

## Why we beat kube-sre-gym

| | kube-sre-gym (1st place SF OpenEnv) | AtlasOps |
|---|---|---|
| Tools | 7 kubectl | **20 real SRE tools** |
| Agents | 1 | **4 + coordinator** |
| Observability | None | **Prometheus + Grafana + Jaeger** |
| Chaos engine | kubectl patches | **Chaos Mesh** (6 fault types) |
| GitOps | None | **Argo CD rollbacks** |
| GCP services | GKE only | **GKE + Cloud SQL + PubSub + Monitoring + Logging** |
| Postmortems | None | **Auto-generated, Cloudflare-quality** |
| Training | SFT only | **SFT → GRPO on AMD MI300X** |
