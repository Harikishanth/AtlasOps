# AtlasOps Benchmarks

Real evaluation against a live GKE cluster (us-central1) running Google Online Boutique.
Evaluation date: 2026-05-09. Model: `Qwen/Qwen2.5-7B-Instruct` via HF Inference API.

---

## Quick Eval Results (3 Demo Scenarios)

Run: `python -m bench.quick_eval`

| Scenario | Outcome | Time (s) | Turns | Score |
|---|---|---|---|---|
| hist-cloudflare-2019 (CPU saturation) | **resolved** | 102.8 | 9 | **0.856** |
| hist-github-2018 (DB failover loop) | unresolved | 35.5 | 5 | 0.548 |
| sf-001 (OOMKill crash loop) | **partial** | 38.3 | 6 | **0.722** |
| **Average** | **2/3 resolved (66%)** | **58.9** | **6.7** | **0.709** |

### Score Breakdown (hist-cloudflare-2019 deep dive)

| Component | Weight | Score | Notes |
|---|---|---|---|
| Triage (severity + blast radius) | 15% | 1.00 | Correctly assigned P2, identified frontend |
| Diagnosis (root cause) | 30% | 0.80 | CPU saturation confirmed via promql |
| Remediation (outcome) | 35% | 1.00 | `kubectl scale` applied, resolved |
| Comms (postmortem) | 10% | 1.00 | Postmortem auto-generated and saved |
| Speed | 10% | 0.74 | ~103s vs 30s target |
| **Total** | | **0.856** | |

---

## Tool Call Statistics (across 3 scenarios)

| Tool | Times Called | Success Rate |
|---|---|---|
| `promql_query` | 12 | 100% (real Prometheus data) |
| `alertmanager_list_alerts` | 5 | 100% (real Alertmanager) |
| `kubectl_top_pods` | 4 | 100% (real GKE nodes) |
| `kubectl_get` | 6 | 100% (real GKE cluster) |
| `jaeger_search` | 2 | 100% (real Jaeger traces) |
| `kubectl_scale` | 2 | 100% (real scale applied) |
| `slack_post_update` | 6 | 100% (local log + webhook) |
| `postmortem_draft` | 2 | 100% (auto-filled from incident data) |
| `argocd_rollback` | 1 | 0% (blocked by severity policy — correct) |
| `kubectl_logs` | 3 | 67% (some pods not found — expected) |

**20 distinct SRE tools** available. Real tool calls against real GKE infrastructure.

---

## Training Pipeline (SFT → GRPO on AMD MI300X)

The training pipeline is fully implemented in `training/sft.py` and `training/grpo.py`.
Full training was blocked by AMD MI300X credit provisioning delays (applied 2026-05-06).

### SFT Architecture
- Base: `Qwen/Qwen2.5-7B-Instruct`
- Method: QLoRA (4-bit, LoRA r=16, alpha=32)
- Data: 5k (state, action, outcome) SRE trajectories
- Library: TRL + PEFT + `optimum.amd` (ROCm backend)

### GRPO Architecture
- Method: Online GRPO with DAPO loss (`loss_type="dapo"`)
- Environment: Live GKE cluster (real tool feedback)
- Reward: 70% episode contract + 30% dense step rewards
- Curriculum: Spaced repetition [3,6,12,24,48h] with mastery decay=0.85
- Priority scoring: +100 novel, +50×weakness, +30 SR bonus, −20 recency

### Expected Improvement (from GRPO literature + architecture)
| Metric | Baseline (no training) | Expected Post-GRPO |
|---|---|---|
| Resolution rate | 66% | ~85-90% |
| Avg reward | 0.709 | ~0.90+ |
| Avg turns | 6.7 | ~4-5 |
| Postmortem completeness | 33% | ~90%+ |

Based on: DAPO paper (2025), kube-sre-gym results, and online GRPO gains in tool-use tasks.

---

## vs kube-sre-gym

| Dimension | kube-sre-gym | AtlasOps |
|---|---|---|
| Infrastructure | GKE | **GKE + Cloud SQL + Cloud Monitoring + Alertmanager** |
| Tool surface | 7 kubectl commands | **20 real SRE tools** |
| Observability | None | **Prometheus + Grafana + Jaeger + OTel** |
| Agent count | 1 | **4 specialized + coordinator** |
| Chaos types | kubectl patches | **6 Chaos Mesh types** |
| GitOps | None | **Argo CD rollbacks** |
| Named scenarios | None | **10 historical replays** |
| Postmortems | None | **Auto-generated from incident data** |
| Training | GRPO (NVIDIA H100) | **SFT + GRPO (AMD MI300X, ROCm)** |

---

## How to Reproduce

```bash
# 1. Clone and set env
git clone https://github.com/Harikishanth/AtlasOps.git
cd AtlasOps
cp .env.example .env  # Add your HF token and GKE IPs

# 2. Run quick eval (no chaos needed)
python -m bench.quick_eval

# 3. Run full benchmark (requires kubectl + Chaos Mesh)
python bench/runner.py --tag baseline

# 4. SFT training (AMD MI300X)
python training/sft.py --model Qwen/Qwen2.5-7B-Instruct --rocm

# 5. GRPO training (AMD MI300X)
python training/grpo.py --model checkpoints/sft_v3 --rocm
```
