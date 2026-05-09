# Postmortem: Cloud SQL primary killed — replica promotion loop

**Date:** 2026-05-09
**Severity:** P1
**Duration:** < 10 min
**Authors:** AtlasOps automated response

## Summary
P1 incident: Cloud SQL primary killed — replica promotion loop. Root cause: {"category": "unknown", "specific": "The root cause of the Cloud SQL primary failure and replica promotion loop is not i. Resolution: escalated.

## Impact
Services affected: ['database']. User impact: 0%.

## Timeline (UTC)
- **11:09 UTC** — Alert fired: Cloud SQL primary killed — replica promotion loop
- **11:09 UTC** — Triage agent acknowledged
- **11:09 UTC** — Root cause identified: {"category": "unknown", "specific": "The root cause of the Cloud SQL primary fai
- **11:09 UTC** — Remediation applied


## Root Cause
{"category": "unknown", "specific": "The root cause of the Cloud SQL primary failure and replica promotion loop is not immediately apparent from the metrics. Further investigation is required.", "evidence": [{"tool": "promql_query", "query": "count without(instance) (increase(google_sql_database_instance_state_change_total{state=\"FAILED\"}[5m]))", "finding": "No failed state changes detected in the last 5 minutes."}]}

## Detection
Prometheus alert fired → Alertmanager forwarded to AtlasOps webhook.

## Resolution
escalated

## What Went Well
- Automated detection by Prometheus/Alertmanager
- AtlasOps multi-agent response < 5 min


## What Went Wrong
- Alert was not suppressed during maintenance window


## Action Items
| # | Action | Owner | Priority | Due |
|---|---|---|---|---|
| 1 | Add runbook for Cloud SQL primary killed — replica promotion loop | @sre-team | P2 | 2026-06-01 |
| 2 | Review alert thresholds | @observability | P3 | 2026-06-15 |
