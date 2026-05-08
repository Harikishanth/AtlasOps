# AtlasOps — How We Built a Real-Cloud Multi-Agent SRE System on AMD MI300X

*AMD Developer Hackathon 2026 | May 7–10, 2026*

---

## The Problem We Were Actually Trying to Solve

Every existing "AI SRE" project simulates the cloud. They fake Kubernetes with subprocess meshes, fake AWS with MiniStack, fake metrics with random number generators. Then they claim their agent "resolves real incidents."

We wanted to know: **what happens when the cloud is actually real?**

Not Docker Compose pretending to be cloud. Not a local Python process with service names like "frontend." An actual GKE cluster in `us-central1`, running Google's Open Source Online Boutique (11 microservices, gRPC, protobuf, the real thing), with real Prometheus scraping real pods, real Jaeger collecting real distributed traces, real Chaos Mesh injecting real kernel-level faults.

---

## Day 0: The Infrastructure Problem

The first thing we discovered: **GKE Autopilot blocks everything Chaos Mesh needs.**

Chaos Mesh requires privileged pods, `hostPID`, and `hostPath` mounts to inject faults at the kernel level. Autopilot denies all three. We found this out after deploying the full stack and running `helm install chaos-mesh` — every pod admission was blocked by GKE Warden.

We deleted the cluster and created a Standard cluster. Lesson: don't use Autopilot for chaos engineering.

The second discovery: `spec.scheduler` was removed in Chaos Mesh v2. Our first 3 chaos manifests failed with `unknown field "spec.scheduler"`. Fixed by removing the field — in v2, you just apply the manifest and it runs once.

**What went wrong that day:**
- Autopilot → Standard migration cost 40 minutes
- Helm values had `nodeExporter` (which requires `hostPath`) in the default config — caused kube-prometheus-stack to fail on first deploy
- The `coreDns` service also tries to patch `kube-system`, which is managed-namespace locked even on Standard

By the end of Day 0: all 65+ pods Running. Grafana at a public IP. Chaos Mesh working. sf-001 (pod-kill on cartservice) confirmed the pod killed and restarted within 8 seconds.

---

## Why 4 Agents Instead of 1

Every other project uses one agent. Give it a pager alert, let it figure everything out.

The problem: SRE work has distinct *phases* with different cognitive modes:
- **Triage** needs to be fast and opinionated — severity NOW, blast radius NOW
- **Diagnosis** needs to be systematic and evidence-based — follow the trace, not the assumption
- **Remediation** needs to be conservative and verified — never execute without checking first
- **Comms** needs to be human — translate technical findings into plain English

A single agent trying to do all four simultaneously gets confused about which mode it's in. It triages when it should diagnose, or remediates when it should still be investigating.

We separated the roles. Each agent has a single job, a strict output format, and a maximum tool call budget. The coordinator routes between them. This isn't just architectural cleanliness — it produces measurably better incident narratives because each agent's reasoning is constrained to what matters for its phase.

---

## The 72B Judge Running on the Same GPU as the Agents

The most interesting design decision: **Qwen2.5-72B as the adversarial designer AND evaluator, co-hosted on the MI300X alongside the 4 × 7B agents.**

External API baselines incur API cost on every episode design and every judgment call.

We co-host everything on one AMD MI300X (192 GB HBM3). The 7B agents in 4-bit are ~4 GB each. The 72B judge in 4-bit is ~37 GB. Total: ~53 GB. The MI300X has 192 GB. We're not even using a third of the memory.

This means:
1. **No external API dependency during inference** — the system is self-contained
2. **The 72B model sees real cluster state** — it reads actual Prometheus data and Jaeger traces when designing adversarial scenarios, not hypothetical ones
3. **Infinite novel scenarios** — the designer generates real Chaos Mesh YAML targeting the agent's specific weakness history, applies it to the cluster, and the agent faces something it has never seen before

---

## What The Adversarial Designer Actually Does

When the benchmark runner calls `design_batch(failure_history, count=10)`:

1. It reads the agent's failure history — which scenarios failed, what the judge's reasoning scores were, what tools were over-used
2. It identifies weakness patterns: "this agent struggles with DNS failures," "this agent confuses network latency with CPU saturation"
3. It generates a JSON spec describing a new scenario with 2-4 fault primitives, at least one red herring, and a clear root cause chain
4. It renders that spec as real Chaos Mesh YAML and saves it to `bench/chaos_manifests/adversarial/`
5. The runner applies it to the real GKE cluster

The generated scenarios are never stored across runs — each benchmark run generates a fresh set. The test set is infinite and you can never memorize it.

---

## The Self-Explaining Agents Feature

One thing we observed watching other demos: you see a button click, a loading spinner, then "incident resolved." The judges have no idea what happened.

We added live thought streaming. Every tool call, result, and conclusion the agents produce is emitted as a Server-Sent Event via `/stream`. The Gradio dashboard subscribes and updates every 3 seconds.

This means during the demo:
- Left side: Grafana showing the real CPU spike happening in real time
- Right side: agents narrating in English what they're doing and why

```
🔴 TRIAGE      → Checking CPU/memory pressure across all pods...
🔴 TRIAGE      ✓ Got cluster state.
🔴 TRIAGE      → Querying Prometheus: rate(http_requests_total{code=~"5.."}[1m])
🔴 TRIAGE      ★ P1 — blast radius mapped, handing to Diagnosis.
🔍 DIAGNOSIS   → Searching Jaeger traces for frontend (last 15m)...
🔍 DIAGNOSIS   ✓ Found 847 slow traces — checking for bottleneck span.
🔍 DIAGNOSIS   ★ Root cause: CPU saturation on frontend. Not a deploy.
🔧 REMEDIATION → Scaling currencyservice to 3 replicas...
🔧 REMEDIATION ✓ Scale applied.
🔧 REMEDIATION ★ Resolution verified — error rate 0.2% < 1% threshold.
📣 COMMS       ★ Postmortem saved.
```

The judges watch this happen live against a real cluster.

---

## Training: SFT → GRPO on AMD MI300X

### Why QLoRA per-agent adapters

We don't train one model that does everything. We train **four separate LoRA adapters** on top of a shared Qwen2.5-7B base:
- `checkpoints/triage_adapter/` — trained on triage trajectories only
- `checkpoints/diagnosis_adapter/` — trained on diagnosis trajectories only
- etc.

On the MI300X, we load the 4-bit base model once (~4 GB) and hot-swap the adapters per agent role. Total memory: base + 4 adapters ≈ 6 GB. We have 186 GB left for the 72B judge.

This is only possible on the MI300X. An A100 (80 GB) could fit the judge OR the 4 agents but not both. A T4 (16 GB) can barely fit the 7B base.

### The reward contract

GRPO requires a reward signal. Ours is multi-component and tier-aware:

```
reward = 0.35 × resolve + 0.20 × evidence + 0.20 × safety + 0.15 × speed + 0.10 × comms
       - penalties(command_spam, false_resolution, hallucinated_evidence, over_silence)
```

Cascade scenarios weight evidence higher (0.25) because the bottleneck is usually diagnosis, not remediation. Named replays weight safety higher (0.25) because historical incidents tend to involve risky fixes.

The penalties are the important part. Without them, agents learn to:
- Spam `kubectl_get` 15 times (command spam)
- Claim resolution without checking Prometheus (false resolution)
- Cite tool outputs they didn't actually read (hallucinated evidence)

We track all of these in the benchmark output as anti-gaming diagnostics.

### Honest GRPO note

We ran SFT first, then GRPO on top. The SFT→GRPO delta is real — the benchmark comparison table shows it. But we also observed something consistent with netweaver_sre's findings: **GRPO helps most at intermediate difficulty, not expert.** Single-fault resolution is already near-perfect after SFT. Named replays (expert tier) remain the hardest, and GRPO's improvement there is smaller.

The agent that can't reliably identify a GitHub 2018 Redis failover loop is the most interesting training target for future work.

---

## The Real Numbers

See [bench/results/comparison_table.md](bench/results/comparison_table.md) for the full table.

| Model | Resolution | Avg Reward | Cascade | Named Replays |
|---|---|---|---|---|
| Baseline (Qwen2.5-7B zero-shot) | 54% | 0.481 | 40% | 30% |
| SFT (QLoRA, 5k trajectories) | 68% | 0.601 | 62% | 55% |
| GRPO (SFT→GRPO, 200 steps) | **82%** | **0.729** | **78%** | **72%** |

The +28pp improvement baseline→GRPO is real. The cascade tier improvement (+38pp) is the most meaningful because cascades are what actually page on-call engineers at 3am.

---

## Reproducibility and Judge Workflow

We tightened reproducibility so reviewers can verify quality without running the full
training stack:

```bash
python -m pytest tests/test_app_endpoints.py tests/test_coordinator.py tests/test_tools.py tests/test_bench_runner.py -q
python scripts/release_gate.py --strict --output docs/RELEASE_READINESS.md
```

- The smoke suite validates the core app/coordinator/tools/reward contract path.
- The release gate validates required evidence, scenario inventory, runtime wiring, and benchmark outputs.
- The dashboard benchmark panel reads directly from `bench/results/comparison_table.md` so displayed numbers track generated artifacts.
- New safety layers are now test-covered: approval gates, circuit breaker, incident correlation, and immutable audit trail.

### New production endpoints

The latest build exposes lightweight ops endpoints for verification:

- `GET /approval/pending`
- `POST /approval/callback`
- `GET /circuit-breaker/status`
- `POST /circuit-breaker/reset`
- `GET /incidents/active`
- `GET /audit/log`
- `GET /audit/verify`

For convenience:
- Windows: `scripts/smoke-e2e-local.ps1 -Quiet`
- Mac/Linux: `bash scripts/smoke-e2e-local.sh quiet`

---

## What We'd Do Differently

1. **Start with Standard GKE.** Autopilot is great for production but hostile to chaos engineering. Don't waste time on the Autopilot→Standard migration.

2. **Generate trajectories before SFT, not after.** We generated the SFT corpus *after* setting up the cluster because the trajectory generator needs real tool outputs. Plan for this — it means the cluster needs to be fully operational (all 11 services Running, Prometheus scraping, Alertmanager connected) before you start generating data.

3. **The Alertmanager→coordinator webhook latency matters more than we expected.** A 7-second lag between chaos injection and coordinator receiving the alert means the triage agent already has an old cluster snapshot. Adding a `wait_for_stabilization` step after alert receipt improved accuracy significantly.

4. **The 72B judge is harder to serve than the 7B agents.** The 72B model requires careful vLLM configuration for KV cache sizing. On MI300X this was straightforward, but on smaller GPUs it would require tensor parallelism across multiple cards.

---

## Why AMD MI300X Specifically

Three reasons this specific GPU matters:

1. **The co-hosting story.** 5 models (4×7B agents + 72B judge) on one GPU. Total memory footprint ~53 GB in 4-bit. The MI300X's 192 GB HBM3 is not just "more memory" — it's large enough to make the co-hosting architecture viable without model sharding or cross-device communication overhead.

2. **GRPO training throughput.** GRPO with G=8 parallel rollouts on a 7B model with gradient accumulation requires significant memory during the forward pass of all 8 rollouts simultaneously. On a T4 this OOMs. On an A100 it requires gradient checkpointing that slows things down. On the MI300X it runs cleanly.

3. **HBM3 bandwidth for fast adapter swapping.** Hot-swapping LoRA adapters between agent calls requires reading the adapter weights from memory. HBM3's memory bandwidth makes this fast enough that the per-agent latency overhead is negligible in practice.

---

## The Final Postmortem

See [docs/postmortems/2026-05-09-cloudflare-2019-replay.md](docs/postmortems/2026-05-09-cloudflare-2019-replay.md).

Total resolution time: **4 minutes 12 seconds** on a real GKE cluster.  
Original Cloudflare incident: **27 minutes** with a team of engineers.

That's the number we care about.

---

*Built by Hari Kishanth (Da Big Three) for the AMD Developer Hackathon 2026*  
*GitHub: [github.com/Harikishanth/AtlasOps](https://github.com/Harikishanth/AtlasOps)*
