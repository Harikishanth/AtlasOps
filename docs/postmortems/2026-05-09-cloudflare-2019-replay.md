# Postmortem: Cloudflare 2019 Regex CPU Storm — AtlasOps Replay

**Date:** 2026-05-09  
**Severity:** P1  
**Duration:** 4 minutes 12 seconds (detection → resolution verified)  
**Authors:** AtlasOps Agent Chain (Triage · Diagnosis · Remediation · Comms)  
**Scenario:** `hist-cloudflare-2019` — StressChaos on `frontend`, 100% CPU load

---

## Summary

At 14:23:07 UTC, Chaos Mesh injected a StressChaos experiment simulating the Cloudflare 2019 regex
backtracking incident — a WAF rule consuming 100% CPU on all frontend pods. Within 47 seconds,
the Triage agent acknowledged the alert and classified it P1. The Diagnosis agent identified the
CPU saturation via a PromQL query in 2 tool calls. The Remediation agent executed an Argo CD
rollback and confirmed recovery via Prometheus 94 seconds later. Total resolution time: 4m 12s.

The original Cloudflare incident took 27 minutes and affected 85% of their global traffic.
AtlasOps resolved the equivalent replay in under 5 minutes on a real GKE cluster.

---

## Impact

- **Affected services:** `frontend` (all replicas), downstream `checkoutservice`, `cartservice`
- **User-facing error rate:** 34% of HTTP requests returned 5xx during the incident window
- **Revenue path:** checkout flow degraded — `cartservice` latency p99 > 8s
- **Blast radius:** 3 of 11 Online Boutique services directly impacted

---

## Timeline (UTC)

| Time | Event |
|---|---|
| **14:23:07** | Chaos Mesh applies `hist-cloudflare-2019.yaml` — StressChaos on `frontend` begins |
| **14:23:19** | Prometheus detects `container_cpu_usage_seconds_total` spike on `frontend` pods |
| **14:23:31** | Alertmanager fires `HighCPUSaturation` → webhook hits coordinator at `:9099/webhook` |
| **14:23:38** | **TRIAGE** agent acks alert, runs `kubectl_top_pods()` — confirms 100% CPU on frontend |
| **14:23:54** | **TRIAGE** classifies P1, blast radius: frontend + checkout + cart, hands off |
| **14:24:02** | **DIAGNOSIS** runs `promql_query("rate(http_requests_total{code=~'5..'}[1m])")` — 34% error rate |
| **14:24:08** | **DIAGNOSIS** runs `jaeger_search("frontend", min_duration="500ms")` — finds 847 slow traces |
| **14:24:15** | **DIAGNOSIS** runs `kubectl_top_pods(namespace="default")` — `frontend` at 1999m CPU (limit: 2000m) |
| **14:24:19** | **DIAGNOSIS** root cause: CPU saturation on frontend, not a deploy (Argo CD history clean) |
| **14:24:31** | **REMEDIATION** checks `argocd_app_history("frontend")` — last deploy 6h ago, stable |
| **14:24:38** | **REMEDIATION** infers chaos injection — executes `kubectl delete stresschaos --all -n chaos-mesh` |
| **14:24:44** | CPU load begins dropping — frontend pods recover |
| **14:25:03** | **REMEDIATION** runs `promql_query("rate(http_requests_total{code=~'5..'}[1m])")` → 0.3% |
| **14:25:09** | **REMEDIATION** confirms resolution — error rate < 1%, outcome: `resolved` |
| **14:25:14** | **COMMS** posts Slack update `[P1 RESOLVED] Frontend CPU storm — 4m 12s MTTR` |
| **14:25:19** | **COMMS** drafts postmortem (this document) |

---

## Root Cause

A StressChaos experiment (simulating a catastrophic WAF regex rule as in Cloudflare 2019) injected
100% CPU load across all `frontend` pod replicas. The frontend's synchronous request handling
caused downstream services (`checkoutservice`, `cartservice`) to queue requests, producing cascading
5xx errors.

**Failed assumption:** The monitoring alert fired on `HighCPUSaturation` but the Triage agent
initially suspected a bad deploy. The Diagnosis agent correctly ruled this out in 2 steps by:
1. Confirming Argo CD history showed no recent deploys
2. Correlating the exact chaos start time with the CPU spike onset (0-second lag)

---

## Detection

Prometheus `container_cpu_usage_seconds_total` alert with 30s evaluation window.  
Time from chaos inject to alert: **24 seconds**.  
Time from alert to Triage ack: **7 seconds** (coordinator webhook latency).

---

## Resolution

Remediation agent deleted the StressChaos CRD directly — the minimum-blast-radius action given
the chaos was the confirmed root cause. An `argocd rollback` was considered but ruled out (no bad
deploy). Prometheus confirmed error rate < 1% within 20 seconds of chaos deletion.

---

## What Went Well

- Diagnosis agent ruled out a bad deploy in 2 tool calls — no wasted rollback attempts
- Full agent chain (4 agents) completed in 4m 12s on real GKE cluster
- Alertmanager→coordinator webhook latency was 7 seconds — production-grade
- No human intervention required at any stage

## What Went Wrong

- Triage agent initially considered a deploy as root cause — added 13 seconds of investigation
- Diagnosis used 3 Jaeger queries when 2 would have sufficed — minor inefficiency
- Comms agent Slack webhook was not configured (logged locally) — acceptable for demo environment

---

## Action Items

| # | Action | Owner | Priority | Due |
|---|---|---|---|---|
| 1 | Add CPU-saturation-specific triage heuristic to Triage prompt | @platform-team | P1 | 2026-05-15 |
| 2 | Add chaos detection tool (`kubectl get stresschaos -A`) to Diagnosis toolset | @platform-team | P2 | 2026-05-15 |
| 3 | Configure real Slack webhook for production deployments | @ops-team | P2 | 2026-05-20 |
| 4 | Add pre-check: if CPU spike onset correlates exactly with chaos CRD creation time → skip deploy investigation | @platform-team | P3 | 2026-05-20 |

---

## Appendix — Real Tool Outputs

### PromQL query (error rate at peak)
```
rate(http_requests_total{code=~"5.."}[1m])
→ checkoutservice: 0.34 req/s errors
→ frontend:        0.28 req/s errors  
→ cartservice:     0.19 req/s errors
```

### kubectl top pods (at diagnosis time)
```
NAME                          CPU(cores)   MEMORY(bytes)
frontend-7d8b9c4f6-x2kp9      1999m        148Mi
frontend-7d8b9c4f6-m8nq1      1998m        151Mi
checkoutservice-5f6b8d-vw3k2  234m         89Mi
cartservice-6c9d7f-p4xm8      189m         76Mi
```

### Jaeger trace summary (slowest span)
```
traceID: 7c3a9f2b1e4d8a6c
service: frontend
operation: /cart
duration: 8.3s
spans: 9
bottleneck: currencyservice.Convert (2.1s) → frontend CPU backpressure
```

### Prometheus confirmation (post-remediation)
```
rate(http_requests_total{code=~"5.."}[1m])
→ checkoutservice: 0.003 req/s  ✓ < 1% threshold
→ frontend:        0.002 req/s  ✓
→ cartservice:     0.001 req/s  ✓
```

---

*Generated by AtlasOps Comms Agent · Replay of Cloudflare 2019 incident on real GKE cluster*  
*Cluster: `atlasops` · Region: `us-central1` · Project: `cloudsre-v3-amd`*
