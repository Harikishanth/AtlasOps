# AtlasOps — Can 4 AI agents replace an on-call SRE team?

> **AMD Developer Hackathon 2026** | Real GKE cluster · Real Chaos Mesh · Real Prometheus alerts · AMD MI300X

[![CI](https://github.com/Harikishanth/AtlasOps/actions/workflows/ci.yml/badge.svg)](https://github.com/Harikishanth/AtlasOps/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-100%2B-brightgreen)](tests/)
[![AMD MI300X](https://img.shields.io/badge/GPU-AMD%20MI300X%20192GB-red)](BLOG.md)

---

We gave 4 specialized AI agents a PagerDuty alert, a live GKE cluster running 11 microservices, and 20 real SRE tools. No simulated responses. No fake metrics. No Docker Compose pretending to be cloud.

**Triage** acked the alert and mapped the blast radius in 47 seconds.  
**Diagnosis** traced the root cause to a currency service CPU hog via Jaeger in 3 tool calls.  
**Remediation** executed `argocd rollback` and confirmed error rate < 1% via Prometheus.  
**Comms** drafted a Cloudflare-quality postmortem with real timestamps from the cluster.

Total time to resolve a Cloudflare 2019 cascade replay: **4 minutes 12 seconds**.  
A senior SRE on a good day: ~25 minutes.

This is **AtlasOps** — a self-improving multi-agent SRE platform where a 72B adversarial judge generates infinite novel chaos scenarios targeting the agents' specific weaknesses, trained via SFT → GRPO on an AMD MI300X (192 GB HBM3).

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
└────────────────────────────────────────────────────────────────┘
          │ kubectl + promql + jaeger + argocd + gcloud APIs
          ▼
┌──────────────── AMD MI300X (192 GB HBM3) ──────────────────────┐
│  vLLM co-hosting — 5 models on ONE GPU:                        │
│  Qwen2.5-7B×4 (Triage/Diagnosis/Remediation/Comms agents)      │
│  Qwen2.5-72B (LLM Judge)                                       │
│                                                                 │
│  Coordinator → Triage → Diagnosis → Remediation → Comms        │
│  Gradio Ops Console · Bench Runner · GRPO Trainer              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 20 Real SRE Tools

kubectl (get/describe/logs/top/rollout/scale/exec) · promql_query · promql_query_range · jaeger_search · jaeger_get_trace · argocd_list_apps · argocd_app_history · **argocd_rollback** · gcloud_logs_read · cloud_monitoring_query · alertmanager_silence · slack_post_update · **postmortem_draft**

---

## 38 Chaos Scenarios

| Tier | Count | Examples |
|---|---|---|
| Single-fault | 8 | pod-kill, CPU hog, memory leak, network loss, disk fill, clock skew |
| Cascade | 5 | currency latency → checkout timeout → frontend 5xx |
| Multi-fault | 5 | 3 simultaneous faults + red herrings |
| Adversarial | 10 | LLM-designed by Qwen2.5-72B judge |
| Named Replays | 10 | Cloudflare 2019, AWS S3 2017, GitHub 2018, Discord 2022… |

---

## Quick Start

### Prerequisites
- GCP project with `container.googleapis.com` enabled
- `gcloud`, `kubectl`, `helm` installed
- AMD MI300X instance (or use the pre-trained checkpoint)

### 1. Provision infrastructure
```bash
bash infra/setup.sh <YOUR_PROJECT_ID> us-central1 atlasops
```

### 2. Run a chaos scenario
```bash
make chaos SCENARIO=sf-001          # pod-kill cartservice
make chaos SCENARIO=hist-cloudflare-2019   # Cloudflare 2019 replay
make chaos-reset                    # clean up
```

### 3. Start the ops console
```bash
pip install -e ".[dev]"
python dashboard.py                 # http://localhost:7860
```

### 4. Run the benchmark
```bash
make bench-baseline                 # freeze v2 baseline
make bench MODEL=checkpoints/grpo_v3   # run grpo_v3
# Results at bench/results/comparison_table.md
```

### 5. Train on AMD MI300X
```bash
make trajectories                   # generate 5k SFT examples from real cluster
make sft                            # SFT on Qwen2.5-7B (ROCm)
make grpo                           # GRPO fine-tune (ROCm)
```

---

## Benchmark Results

| Tag | Resolution | Avg Reward | Cascade Res. | Replay Res. |
|---|---|---|---|---|
| baseline_v2 | 54% | 0.481 | 40% | 30% |
| sft_v3 | 68% | 0.601 | 62% | 55% |
| **grpo_v3** | **82%** | **0.729** | **78%** | **72%** |

*+28pp improvement from baseline → GRPO. Reward includes anti-gaming penalties.*

---

## Project Structure

```
atlasops/
├── infra/           # GCP provisioning scripts + Helm values
├── agents/          # Coordinator, 4 agent prompts, 20 tool wrappers, judge
├── bench/           # Runner, 38 chaos manifests, results
├── training/        # SFT, GRPO, trajectory generator (ROCm-compatible)
├── docs/            # Postmortems, MI300X evidence, benchmarks
├── dashboard.py     # Gradio Ops Console
└── pyproject.toml
```

---

## License

MIT — see [LICENSE](LICENSE)
