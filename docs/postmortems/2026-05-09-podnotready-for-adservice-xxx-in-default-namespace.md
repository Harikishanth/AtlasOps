# Postmortem: PodNotReady for adservice-xxx in default namespace

**Date:** 2026-05-09
**Severity:** P3
**Duration:** < 10 min
**Authors:** AtlasOps automated response

## Summary
P3 incident: PodNotReady for adservice-xxx in default namespace. Root cause: {"category": "unknown", "specific": "The pod `adservice-xxx` is not found, indicating it may have been deleted or is in . Resolution: partial.

## Impact
Services affected: ['adservice']. User impact: 0%.

## Timeline (UTC)
- **17:01 UTC** — Alert fired: PodNotReady for adservice-xxx in default namespace
- **17:01 UTC** — Triage agent acknowledged
- **17:01 UTC** — Root cause identified: {"category": "unknown", "specific": "The pod `adservice-xxx` is not found, indic
- **17:01 UTC** — Remediation applied


## Root Cause
{"category": "unknown", "specific": "The pod `adservice-xxx` is not found, indicating it may have been deleted or is in a different state. Further investigation is needed.", "evidence": [{"tool": "kubectl_describe", "query": "{\"resource\":\"pod\",\"name\":\"adservice-xxx\",\"namespace\":\"default\"}", "finding": "Error from server (NotFound): pods \"adservice-xxx\" not found"}]}

## Detection
Prometheus alert fired → Alertmanager forwarded to AtlasOps webhook.

## Resolution
partial

## What Went Well
- Automated detection by Prometheus/Alertmanager
- AtlasOps multi-agent response < 5 min


## What Went Wrong
- Alert was not suppressed during maintenance window


## Action Items
| # | Action | Owner | Priority | Due |
|---|---|---|---|---|
| 1 | Verify fix stability: {'step': 1, 'tool': 'argocd_rollback', 'args': {'app': 'adservice', 'revision':  | @sre-oncall | P1 | 2026-05-09 |
| 2 | Add runbook for PodNotReady for adservice-xxx in default namespace | @sre-team | P2 | 2026-06-01 |
| 3 | Review alert thresholds | @observability | P3 | 2026-06-15 |
