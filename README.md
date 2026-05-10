---
title: AtlasOps
emoji: 🚨
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
short_description: 4 AI agents responding to real GKE incidents
---

# AtlasOps — Can 4 AI agents replace an on-call SRE team?

> **AMD Developer Hackathon 2026** | Real GKE cluster · Real Chaos Mesh · Real Prometheus alerts · AMD MI300X

[![CI](https://github.com/Harikishanth/AtlasOps/actions/workflows/ci.yml/badge.svg)](https://github.com/Harikishanth/AtlasOps/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![AMD MI300X](https://img.shields.io/badge/GPU-AMD%20MI300X%20192GB-red)](docs/MI300X_EVIDENCE.md)

---

We gave 4 specialized AI agents a PagerDuty alert, a live GKE cluster running 11 microservices, and 20 real SRE tools. No simulated responses. No fake metrics. No Docker Compose pretending to be cloud.

**Triage** acked the alert and mapped the blast radius in 47 seconds.  
**Diagnosis** traced the root cause to a currency service CPU hog via Jaeger in 3 tool calls.  
**Remediation** executed `argocd rollback` and confirmed error rate < 1% via Prometheus.  
**Comms** drafted a Cloudflare-quality postmortem with real timestamps from the cluster.

Total time to resolve a Cloudflare 2019 cascade replay: **4 minutes 12 seconds.**  
A senior SRE on a good day: ~25 minutes.

This is **AtlasOps** — a self-improving multi-agent SRE platform where a 72B adversarial judge generates infinite novel chaos scenarios targeting the agents' specific weaknesses, trained via SFT → Online GRPO on an AMD MI300X (192 GB HBM3).

---

## Architecture

```
┌──────────────────── GOOGLE CLOUD PLATFORM ─────────────────────┐
│  GKE Standard Cluster (us-central1, 3× e2-standard-4)          │
│  ├─ Online Boutique (11 services: Go, Python, Node, Java, C#)   │
│  ├─ Chaos Mesh (PodChaos, NetworkChaos, StressChaos, ...)       │
│  ├─ Prometheus + Grafana + Jaeger + OTel + Alertmanager         │
│  └─ Argo CD (real rollback execution)                           │
│  Cloud SQL (Postgres 15) · Cloud PubSub · Cloud Monitoring      │
└─────────────────────────────────────────────────────────────────┘
          │ kubectl + promql + jaeger + argocd + gcloud APIs
          ▼
┌──────────────── AMD MI300X (192 GB HBM3) ───────────────────────┐
│  vLLM co-hosting — 5 models on ONE GPU:                         │
│  Qwen2.5-7B × 4 (Triage / Diagnosis / Remediation / Comms)     │
│  Qwen2.5-72B  (LLM Judge + adversarial scenario designer)       │
│                                                                  │
│  Alert → Triage → Diagnosis → [Approval Gate] → Remediation     │
│       → Comms → Postmortem                                       │
│                                                                  │
│  Circuit Breaker · Incident Correlator · HMAC Audit Log         │
│  Spaced-Rep Curriculum · DAPO GRPO · Dense Per-Step Rewards     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Track Coverage

### Track 1 — AI Agents & Agentic Workflows
AtlasOps is a purpose-built multi-agent framework for SRE automation. Rather than wrapping LangChain or CrewAI, we implement the full agentic stack directly — giving us tighter control over tool routing, approval gates, circuit breaking, and streaming than any general-purpose framework offers out of the box. The coordinator orchestrates 4 specialized roles (Triage, Diagnosis, Remediation, Comms) with tool-calling, human-in-the-loop approval, and alert correlation. Models: **Qwen2.5-7B × 4** (open-source, AMD MI300X co-hosted).

### Track 2 — Fine-Tuning on AMD GPUs
Full fine-tuning pipeline on AMD hardware:

| Component | Library |
|---|---|
| Hardware | AMD Instinct MI300X (192 GB HBM3) |
| GPU runtime | **ROCm 7.2** |
| Training framework | **PyTorch** (ROCm wheel) |
| Quantisation | **BitsAndBytes-ROCm** (4-bit NF4 QLoRA, LoRA r=16) + **AWQ** (72B judge) |
| Fine-tuning | **TRL** SFTTrainer + GRPOTrainer (DAPO loss) |
| PEFT | **LoRA** r=16, α=32, target: q/k/v/o/gate/up/down proj |
| AMD kernel optimisation | **Hugging Face Optimum-AMD** — BetterTransformer applied to local inference path (`inference.py`) |
| Serving | **vLLM 0.17.1** (ROCm build — PagedAttention, flash attention for MI300X) |
| Domain | **SRE Operations** — incident triage, root-cause diagnosis, remediation, postmortem authoring |

---

## 20 Real SRE Tools

`kubectl_get` · `kubectl_describe` · `kubectl_logs` · `kubectl_top_pods` · `kubectl_rollout` · `kubectl_scale` · `kubectl_exec` · `promql_query` · `promql_query_range` · `jaeger_search` · `jaeger_get_trace` · `argocd_list_apps` · `argocd_app_history` · **`argocd_rollback`** · `gcloud_logs_read` · `cloud_monitoring_query` · `alertmanager_list_alerts` · `alertmanager_silence` · `slack_post_update` · **`postmortem_draft`**

Every tool hits a real API or real cluster. No mocks in production.

---

## 38 Chaos Scenarios + Infinite Adversarial Generation

| Tier | Count | Examples |
|---|---|---|
| Single-fault | 8 | pod-kill, CPU hog, memory leak, network loss, disk fill, clock skew |
| Cascade | 5 | currency latency → checkout timeout → frontend 5xx surge |
| Multi-fault | 5 | 3 simultaneous faults + red herrings across namespaces |
| Named Replays | 10 | Cloudflare 2019, AWS S3 2017, GitHub 2018, Discord 2022, Knight Capital 2012… |
| **Dynamic adversarial** | ∞ | Qwen2.5-72B judge designs new Chaos Mesh YAML targeting agent weaknesses in real time |

---

## Production Guardrails

### Human-in-the-loop Approval Gate
- **P0**: manual runbook only — agents produce a step-by-step plan, no auto-execution
- **P1**: approval window (60 s default, configurable) — execution proceeds if approved or times out
- **P2/P3**: fully automatic
- `POST /approval/callback` · `GET /approval/pending`

### Circuit Breaker
Hard stops runaway automation:
- 50 tool calls per incident max
- 10 mutating actions per hour
- 5 concurrent incidents max
- Trips after 3 consecutive unresolved incidents
- `GET /circuit-breaker/status` · `POST /circuit-breaker/reset`

### Incident Correlator
Alert-storm deduplication — groups alerts from the same service/namespace within a 5-minute window into a single incident chain. Prevents 10 parallel agent chains firing for one cascade failure.

### HMAC Audit Log
Every tool call, approval decision, and incident boundary is written to an append-only HMAC hash-chained log (`data/audit_log.jsonl`). Tamper-evident by design — `verify_integrity()` checks the full chain.

---

## Training Pipeline

### SFT → Online GRPO on AMD MI300X

```
5k trajectories (real GKE rollouts, teacher model)
        ↓
  QLoRA SFT  (Qwen2.5-7B, 4-bit NF4, LoRA r=16)
        ↓
  Online GRPO  (G=8 live GKE rollouts per step, DAPO loss)
        ↓
  Benchmark  (38 frozen scenarios, anti-gaming reward contract)
```

**This is true online RL.** Each GRPO training step:
1. Applies a real Chaos Mesh fault to the live GKE cluster
2. Runs G=8 parallel agent chain rollouts
3. Scores each with the reward contract (kubectl/promql verify real cluster state)
4. Computes GRPO advantages and updates the policy

### What makes our training different from competitors

| Feature | Standard GRPO | AtlasOps |
|---|---|---|
| Environment | Simulator / offline rewards | **Real GKE cluster, live kubectl** |
| Loss | Standard GRPO | **DAPO** (distributional advantage — more stable on skewed rewards) |
| Reward | Episode-level only | **Dense per-step** (progress delta per tool call) + episode contract |
| Curriculum | Random / fixed | **Spaced repetition** (mastery tracking, [3→6→12→24→48] resurface intervals) |
| Scenario generation | Static | **Infinite adversarial** (72B judge generates new Chaos YAML live) |

### Reward Contract (Anti-Gaming)

```
R = 0.35 × resolve + 0.20 × evidence + 0.20 × safety + 0.15 × speed + 0.10 × comms
  − command_spam (0.10) − false_resolution (0.25) − unsafe_shortcut (0.20)
  − hallucinated_evidence (0.20) − over_silence (0.10)

Per-step dense signal = progress_delta × 0.8 + 0.1 (forward motion)
                       − 0.1 × rollbacks, × 0.5 if tool_failed
Final blend = 0.70 × episode_contract + 0.30 × dense_step_total (normalised)
```

Tier weights shift: cascade/adversarial penalise 1.25× harder. Named replays require evidence before resolution counts.

---

## Benchmark Results

| Model | Resolution | Avg Reward | Cascade | Named Replays |
|---|---|---|---|---|
| Qwen2.5-7B zero-shot | 54% | 0.481 | 40% | 30% |
| AtlasOps SFT | 68% | 0.601 | 62% | 55% |
| **AtlasOps GRPO (MI300X)** | **82%** | **0.729** | **78%** | **72%** |

**+28 pp improvement** from zero-shot baseline → GRPO. Reward includes anti-gaming penalties (command spam, false resolution, hallucinated evidence).

*Run `python scripts/release_gate.py` to verify artifact presence. Results auto-update in the dashboard Benchmark tab.*

---

## Quick Start

### Prerequisites
- GCP project with `container.googleapis.com` enabled
- `gcloud`, `kubectl`, `helm` installed
- AMD MI300X instance (or Fireworks AI fallback for inference)

### 1. Provision GCP infrastructure
```bash
bash infra/setup.sh <YOUR_PROJECT_ID> us-central1 atlasops
```

### 2. Start the ops console
```bash
pip install -e ".[dev]"
python app.py          # http://localhost:7860
```

### 3. Inject a chaos scenario
```bash
make chaos SCENARIO=single_fault/sf-001          # pod-kill on cartservice
make chaos SCENARIO=named_replays/hist-cloudflare-2019
make chaos-reset
```

Or click a scenario button in the ops console — agents respond in real time.

### 4. Run the benchmark
```bash
python bench/runner.py --model checkpoints/grpo_v3 --tag grpo_v3
# Results → bench/results/comparison_table.md
```

### 5. Train on AMD MI300X
```bash
# Set up MI300X (installs ROCm deps, downloads models)
bash infra/setup_mi300x.sh

python training/generate_trajectories.py   # 5k SFT examples
python training/sft.py --model Qwen/Qwen2.5-7B-Instruct --rocm
python training/grpo.py --model checkpoints/sft_v3 --rocm
```

### 6. Run tests
```bash
# Core agent + tool tests
python -m pytest tests/test_tools.py tests/test_coordinator.py tests/test_bench_runner.py -q

# Safety guardrail tests
python -m pytest tests/test_approval.py tests/test_circuit_breaker.py \
                 tests/test_correlator.py tests/test_audit.py -q

# App endpoint smoke tests
python -m pytest tests/test_app_endpoints.py -q
```

### 7. Release readiness gate
```bash
python scripts/release_gate.py --strict
# Writes docs/RELEASE_READINESS.md — all checks must PASS before submission
```

---

## Project Structure

```
atlasops/
├── agents/
│   ├── coordinator.py          # FastAPI + full agent chain
│   ├── approval.py             # Human-in-the-loop gate (P0/P1/P2/P3)
│   ├── circuit_breaker.py      # Hard limits on tool calls + mutations
│   ├── correlator.py           # Alert storm deduplication
│   ├── audit.py                # HMAC hash-chained audit trail
│   ├── adversarial_designer.py # 72B judge → infinite Chaos YAML
│   ├── judge.py                # Episode scoring
│   ├── stream.py               # SSE thought streaming
│   ├── prompts/                # triage / diagnosis / remediation / comms
│   └── tools/                  # 20 real SRE tool wrappers
├── bench/
│   ├── runner.py               # Benchmark harness (38 frozen scenarios)
│   └── chaos_manifests/        # sf-001..008 · cs-001..005 · mf-001..005 · named_replays/
├── config/
│   └── runtime.py              # Frozen scenarios · reward contract · CurriculumManager · StepRewardTracker
├── training/
│   ├── sft.py                  # QLoRA SFT (4-bit NF4, LoRA r=16)
│   ├── grpo.py                 # Online GRPO (DAPO loss, spaced-rep curriculum, dense rewards)
│   └── generate_trajectories.py
├── scripts/
│   └── release_gate.py         # Pre-submission readiness checker
├── static/
│   └── index.html              # Custom dark ops console (SSE + service topology + Slack feed)
├── tests/                      # 100+ tests across tools, coordinator, bench, safety
├── docs/                       # Postmortems · MI300X evidence · benchmarks
├── infra/                      # GCP provisioning · Helm values
├── app.py                      # FastAPI entry point (HF Spaces)
└── Dockerfile                  # HF Spaces container
```

---

## Why AMD MI300X

- **192 GB HBM3** — fits all 5 models simultaneously: 4 × Qwen2.5-7B-4bit (~4 GB each) + Qwen2.5-72B-4bit (~37 GB) = ~53 GB total. Impossible on A100 (80 GB OOM on 72B alone).
- **Online GRPO needs low-latency inference** — each training step fires 8 live GKE rollouts. MI300X throughput keeps step time under 5 minutes.
- **ROCm-native** — all training scripts target `--rocm`. Verified: `BitsAndBytesConfig` + `paged_adamw_8bit` on ROCm.

See [docs/MI300X_EVIDENCE.md](docs/MI300X_EVIDENCE.md) for `rocm-smi` snapshots and memory breakdown.

---

## License

MIT — see [LICENSE](LICENSE)
