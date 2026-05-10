# Judges: Start Here — AtlasOps

> 60-second proof it's real. Everything below hits a live GKE cluster.

---

## Live console (Hugging Face Space)

Hackathon deployment (correct slug uses a hyphen: **`atlas-ops`**):

- **Space:** [lablab-ai-amd-developer-hackathon / atlas-ops](https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/atlas-ops)
- **App URL:** `https://lablab-ai-amd-developer-hackathon-atlas-ops.hf.space` — open that in the browser, then **`/health`** on the same host for a JSON readiness check.

If you see **404** on `…/spaces/…/atlasops` (no hyphen), use **`atlas-ops`** instead or the URL your team submitted after duplicating the Space.

---

## 1. Confirm the cluster is real

```bash
gcloud container clusters get-credentials atlasops \
  --region=us-central1 --project=cloudsre-v3-amd

kubectl get nodes                          # 3× e2-standard-4 in us-central1
kubectl get pods -A | grep -c Running      # should be 40+
kubectl get crds | grep chaos-mesh         # Chaos Mesh CRDs installed
kubectl get applications -n argocd         # ArgoCD managing Online Boutique
```

---

## 2. Fire a real chaos scenario + watch agents respond

```bash
# Apply a real Chaos Mesh fault
kubectl apply -f bench/chaos_manifests/named_replays/hist-cloudflare-2019.yaml

# Watch Alertmanager fire within ~60s
curl http://<ALERTMANAGER_IP>/api/v2/alerts | python -m json.tool

# Watch agents work in real time (SSE stream)
curl http://localhost:7860/stream

# Reset
kubectl delete stresschaos --all -n chaos-mesh
```

Or just click **Cloudflare 2019** in the ops console — it does all of the above.

---

## 3. Start the ops console

```bash
pip install -e ".[dev]"
python app.py          # http://localhost:7860
```

**What judges should see:**
1. Service topology grid (11 boxes) — boxes turn red as chaos fires
2. Grafana iframe shows real cluster metrics spiking
3. Agent Chain panel fills with live thoughts (Triage → Diagnosis → Remediation → Comms)
4. `# incident-response` Slack feed shows the comms agent's update
5. MTTR counter turns green on resolution
6. Postmortem saved to `docs/postmortems/`

---

## 4. Run all tests

```bash
# Tools + coordinator + bench reward contract
python -m pytest tests/test_tools.py tests/test_coordinator.py \
                 tests/test_bench_runner.py tests/test_chaos_manifests.py -q

# Safety guardrails (approval gate, circuit breaker, correlator, audit)
python -m pytest tests/test_approval.py tests/test_circuit_breaker.py \
                 tests/test_correlator.py tests/test_audit.py -q

# App endpoint smoke tests (no cluster needed)
python -m pytest tests/test_app_endpoints.py -q
```

---

## 5. Verify every production safety endpoint

```bash
# Human approval gate — shows pending P1 approvals
curl http://localhost:7860/approval/pending

# Circuit breaker — shows tool call counts, mutating action rate, tripped state
curl http://localhost:7860/circuit-breaker/status

# Correlated incidents — deduped active incident list
curl http://localhost:7860/incidents/active

# Live cluster service health — 11 Online Boutique services
curl http://localhost:7860/cluster/health

# Comms feed — last 30 Slack posts from agents
curl http://localhost:7860/slack/feed

# Runtime config — Grafana/ArgoCD URLs loaded dynamically
curl http://localhost:7860/config
```

---

## 6. Training evidence

```bash
# Release readiness gate — generates docs/RELEASE_READINESS.md
python scripts/release_gate.py --strict

# Compare model performance (run after training)
python leaderboard.py

# Benchmark table (auto-updates on each run)
cat bench/results/comparison_table.md
```

Full MI300X evidence (rocm-smi, memory breakdown, vLLM co-hosting logs):
→ `docs/MI300X_EVIDENCE.md`

Full delivery scorecard:
→ `docs/AMD_FINAL_DELIVERY_SCORECARD_AND_REWARD_SPEC.md`

---

## 7. Why AtlasOps over every other SRE submission

| Dimension | Typical competitor | AtlasOps |
|---|---|---|
| Infrastructure | Docker Compose / MiniStack simulator | **Real GKE cluster on GCP** |
| Fault injection | Scripted mock | **Chaos Mesh CRDs — 6 fault types** |
| Observability | None / stubbed | **Prometheus + Grafana + Jaeger + OTel** |
| Agents | 1 generic agent | **4 specialized + coordinator** |
| Tools | `kubectl` only (7 cmds) | **20 real SRE tools** |
| Scenarios | Static list | **38 frozen + ∞ adversarial (72B judge)** |
| Training RL | Offline / pre-collected | **Online GRPO — live GKE rollouts** |
| Reward | Simple success/fail | **Anti-gaming contract: 5 components, 5 penalties, tier-weighted** |
| Safety | None | **Approval gate + circuit breaker + audit log** |
| GPU | NVIDIA (A10/H100) | **AMD MI300X 192GB — 5 models co-hosted** |
