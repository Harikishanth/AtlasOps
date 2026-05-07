# AtlasOps — Architecture

## System Overview

```mermaid
graph TB
    subgraph GCP["Google Cloud Platform — us-central1"]
        subgraph GKE["GKE Standard Cluster (atlasops)"]
            OB["Online Boutique<br/>11 microservices<br/>gRPC + protobuf"]
            CM["Chaos Mesh<br/>PodChaos · NetworkChaos<br/>StressChaos · DNSChaos<br/>IOChaos · TimeChaos"]
            PROM["Prometheus + Grafana<br/>kube-prometheus-stack"]
            JAEGER["Jaeger + OTel Collector<br/>Distributed tracing"]
            ARGO["Argo CD<br/>GitOps rollbacks"]
            AM["Alertmanager<br/>Webhook → coordinator"]
        end
        CSQL["Cloud SQL<br/>Postgres 15"]
        PS["Cloud PubSub<br/>cloudsre-checkout-events"]
        CMON["Cloud Monitoring API<br/>GCP-native metrics"]
        CLOG["Cloud Logging<br/>Structured logs"]
    end

    subgraph MI300X["AMD MI300X — 192 GB HBM3"]
        COORD["Coordinator<br/>FastAPI :9099"]
        subgraph AGENTS["4 Specialized Agents (Qwen2.5-7B + QLoRA)"]
            T["🔴 Triage"]
            D["🔍 Diagnosis"]
            R["🔧 Remediation"]
            C["📣 Comms"]
        end
        JUDGE["72B Judge<br/>Qwen2.5-72B<br/>Adversarial designer<br/>+ Evaluator"]
        DASH["Gradio Dashboard<br/>:7860"]
    end

    CM -->|injects faults| OB
    OB -->|metrics| PROM
    OB -->|traces| JAEGER
    PROM -->|alert fires| AM
    AM -->|webhook| COORD
    COORD --> T --> D --> R --> C
    T & D & R & C <-->|"20 real SRE tools<br/>(kubectl · promql · jaeger<br/>argocd · gcloud · alertmanager)"| GKE
    T & D & R & C <-->|Cloud APIs| CSQL & PS & CMON & CLOG
    JUDGE -->|generates scenarios| CM
    JUDGE -->|scores actions| COORD
    DASH -->|live thoughts SSE| COORD
```

---

## Agent Chain

```mermaid
sequenceDiagram
    participant AM as Alertmanager
    participant CO as Coordinator
    participant TR as Triage Agent
    participant DG as Diagnosis Agent
    participant RM as Remediation Agent
    participant CM as Comms Agent
    participant GKE as Real GKE Cluster

    AM->>CO: POST /webhook (alert fired)
    CO->>TR: {incident_id, alert}
    TR->>GKE: kubectl_top_pods()
    TR->>GKE: promql_query("rate(5xx[1m])")
    TR-->>CO: {severity: P1, blast_radius: [...]}

    CO->>DG: {triage_output}
    DG->>GKE: jaeger_search(service, min_duration=500ms)
    DG->>GKE: promql_query_range(query, last_15m)
    DG->>GKE: kubectl_logs(bottleneck_pod)
    DG->>GKE: argocd_app_history(app)
    DG-->>CO: {root_cause: {...}, recommended_actions: [...]}

    CO->>RM: {triage, diagnosis}
    RM->>GKE: argocd_rollback(app, revision)
    RM->>GKE: promql_query("rate(5xx[1m])")
    Note over RM: verify error_rate < 1%
    RM-->>CO: {outcome: resolved, ttr: 187s}

    CO->>CM: {full incident chain}
    CM->>CM: slack_post_update(...)
    CM->>CM: postmortem_draft(incident)
    CM-->>CO: {postmortem_path: docs/postmortems/...}
```

---

## AMD MI300X Co-hosting

```
AMD MI300X (192 GB HBM3)
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Qwen2.5-7B base (4-bit NF4)           ~4 GB           │
│  ├─ triage_adapter    (LoRA r=16)      ~40 MB           │
│  ├─ diagnosis_adapter (LoRA r=16)      ~40 MB           │
│  ├─ remediation_adapter (LoRA r=16)    ~40 MB           │
│  └─ comms_adapter     (LoRA r=16)      ~40 MB           │
│                                                         │
│  Qwen2.5-72B (4-bit NF4)               ~37 GB           │
│  └─ Adversarial designer + judge                        │
│                                                         │
│  Total used: ~41 GB    Available: ~151 GB               │
│                                                         │
│  ❌ A100 (80 GB): can fit judge OR agents, not both     │
│  ❌ T4   (16 GB): can't fit even the 7B base            │
│  ✅ MI300X: all 5 models + room to spare                │
└─────────────────────────────────────────────────────────┘
```

---

## Training Pipeline

```mermaid
flowchart LR
    A["Real GKE Cluster<br/>11 live microservices"] -->|Chaos Mesh injects faults| B
    B["Alertmanager fires<br/>real webhook"] --> C
    C["4 agents run<br/>against live cluster"] --> D
    D["72B judge scores<br/>tool calls + outcomes"] --> E
    E["5k trajectory corpus<br/>data/sft_corpus.jsonl<br/>reward_contract included"]

    E --> F["Stage 1: QLoRA SFT<br/>Qwen2.5-7B + LoRA r=16<br/>4-bit NF4 on MI300X"]
    F --> G["Stage 2: GRPO<br/>Optuna HP search (6 trials)<br/>num_gen=8, cosine LR<br/>tier-aware reward contract"]
    G --> H["4 role adapters<br/>~40 MB each<br/>checkpoints/grpo_v3/"]

    H -->|"hot-swap adapters<br/>per agent call"| I["Production serving<br/>vLLM on MI300X"]
```

---

## 20 Real SRE Tools

```
kubectl (7)          promql (2)          jaeger (2)
─────────────        ──────────          ──────────
kubectl_get          promql_query        jaeger_search
kubectl_describe     promql_query_range  jaeger_get_trace
kubectl_logs
kubectl_top_pods     argocd (3)          gcloud (2)
kubectl_top_nodes    ─────────           ──────────
kubectl_rollout      argocd_list_apps    gcloud_logs_read
kubectl_scale        argocd_app_history  cloud_monitoring_query
kubectl_exec         argocd_rollback

alertmanager (2)     comms (2)
────────────────     ──────────
alertmanager_silence slack_post_update
alertmanager_list    postmortem_draft
```

kube-sre-gym has 7 (kubectl only). AtlasOps has 20.

---

## Reward Contract (Anti-Gaming)

```
reward = 0.35 × resolve                    # did the incident get fixed?
       + 0.20 × evidence                   # was the root cause proven with data?
       + 0.20 × safety                     # was the action minimum-blast-radius?
       + 0.15 × speed                      # logistic decay — fast is good, race-to-zero is penalised
       + 0.10 × comms                      # was a postmortem generated?

       - 0.10  if turns > 40              # command spam
       - 0.25  if claimed resolved but wasn't  # false resolution
       - 0.20  if efficiency < 0.3        # unsafe shortcut
       - 0.20  if reasoning AND correctness both low  # hallucinated evidence
       - 0.10  if silenced an alert without resolving # over-silencing

tier adjustments:
  cascade:      r_evidence weight ↑ (tracing the chain matters more)
  multi_fault:  r_safety weight ↑   (conservative action matters more)
  adversarial:  all penalties × 1.25 (harder tier, stricter scoring)
```
