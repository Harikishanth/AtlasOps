"""Communication tool wrappers — Slack updates + postmortem generation."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jinja2 import Template


SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
POSTMORTEM_DIR = Path(os.getenv("POSTMORTEM_DIR", "docs/postmortems"))

_SEV_COLOR_HEX = {"P0": "ff0000", "P1": "ff8800", "P2": "ffcc00"}
_LOG_PATH = Path("data/slack_posts.jsonl")


def _build_slack_payload(channel: str, severity: str, title: str,
                         summary: str, action_items: list[str]) -> dict:
    return {
        "channel": channel,
        "username": "atlasops-bot",
        "icon_emoji": ":rotating_light:" if severity in ("P0", "P1") else ":warning:",
        "attachments": [{
            "color": "#" + _SEV_COLOR_HEX.get(severity, "888888"),
            "title": f"[{severity}] {title}",
            "text": summary,
            "fields": (
                [{"title": "Action Items",
                  "value": "\n".join(f"• {a}" for a in action_items)}]
                if action_items else []
            ),
            "ts": int(datetime.now(timezone.utc).timestamp()),
        }],
    }


def _post_to_discord(slack_payload: dict) -> None:
    """Convert Slack payload to Discord embed and POST."""
    att = slack_payload["attachments"][0]
    color_int = int(_SEV_COLOR_HEX.get(
        att["title"].split("]")[0].lstrip("["), "888888"), 16)
    fields = [
        {"name": f["title"], "value": f["value"], "inline": False}
        for f in att.get("fields", []) if f.get("value")
    ]
    discord_payload = {
        "username": slack_payload.get("username", "atlasops-bot"),
        "embeds": [{
            "title": att["title"],
            "description": att.get("text", ""),
            "color": color_int,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "AtlasOps · AMD MI300X"},
        }],
    }
    requests.post(DISCORD_WEBHOOK, json=discord_payload, timeout=10).raise_for_status()


def slack_post_update(channel: str, severity: str, title: str, summary: str,
                      action_items: list[str] | None = None) -> dict[str, Any]:
    """Post an incident update.

    Always writes to local log (powers the UI feed).
    Also delivers to Slack if SLACK_WEBHOOK_URL is set.
    Also delivers to Discord if DISCORD_WEBHOOK_URL is set.
    """
    payload = _build_slack_payload(channel, severity, title, summary, action_items or [])

    # Always persist locally — powers /slack/feed in the UI
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

    # Preserve a stable mode label for downstream tests/integrations that
    # differentiate "logged locally only" from external webhook delivery.
    modes: list[str] = ["logged_locally"]
    errors: list[str] = []

    if SLACK_WEBHOOK:
        try:
            r = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
            r.raise_for_status()
            modes.append("slack")
        except requests.RequestException as e:
            errors.append(f"slack: {e}")

    if DISCORD_WEBHOOK:
        try:
            _post_to_discord(payload)
            modes.append("discord")
        except requests.RequestException as e:
            errors.append(f"discord: {e}")

    return {
        "success": True,
        "mode": "+".join(modes),
        **({"errors": errors} if errors else {}),
    }


POSTMORTEM_TEMPLATE = """# Postmortem: {{ title }}

**Date:** {{ date }}
**Severity:** {{ severity }}
**Duration:** {{ duration }}
**Authors:** {{ authors }}

## Summary
{{ summary }}

## Impact
{{ impact }}

## Timeline (UTC)
{% for entry in timeline -%}
- **{{ entry.time }}** — {{ entry.event }}
{% endfor %}

## Root Cause
{{ root_cause }}

## Detection
{{ detection }}

## Resolution
{{ resolution }}

## What Went Well
{% for item in went_well -%}
- {{ item }}
{% endfor %}

## What Went Wrong
{% for item in went_wrong -%}
- {{ item }}
{% endfor %}

## Action Items
| # | Action | Owner | Priority | Due |
|---|---|---|---|---|
{% for ai in action_items -%}
| {{ loop.index }} | {{ ai.action }} | {{ ai.owner }} | {{ ai.priority }} | {{ ai.due }} |
{% endfor %}
"""


def postmortem_draft(incident: dict[str, Any], output_path: str = "") -> dict[str, Any]:
    """Generate a Cloudflare-blog quality postmortem.

    incident dict shape (all optional — auto-filled from available data):
      title, severity, duration, authors, summary, impact,
      timeline: [{time, event}], root_cause, detection, resolution,
      went_well: [str], went_wrong: [str],
      action_items: [{action, owner, priority, due}]
    """
    now = datetime.now(timezone.utc)

    # Auto-fill missing fields from nested incident data
    def _get(*keys, default=""):
        for key in keys:
            if incident.get(key):
                return incident[key]
        return default

    triage = incident.get("triage", {}) or {}
    diagnosis = incident.get("diagnosis", {}) or {}
    remediation = incident.get("remediation", {}) or {}

    title    = _get("title") or triage.get("title") or "Incident"
    severity = _get("severity") or triage.get("severity") or "Unknown"
    root_cause_raw = _get("root_cause") or diagnosis.get("root_cause") or diagnosis.get("specific") or "Under investigation"
    root_cause = root_cause_raw if isinstance(root_cause_raw, str) else json.dumps(root_cause_raw)
    resolution_raw = _get("resolution") or remediation.get("outcome") or "Resolved by on-call team"
    resolution = resolution_raw if isinstance(resolution_raw, str) else json.dumps(resolution_raw)
    actions_taken = remediation.get("actions_taken", [])

    timeline = incident.get("timeline") or [
        {"time": now.strftime("%H:%M UTC"), "event": f"Alert fired: {title}"},
        {"time": now.strftime("%H:%M UTC"), "event": "Triage agent acknowledged"},
        {"time": now.strftime("%H:%M UTC"), "event": f"Root cause identified: {root_cause[:80]}"},
        {"time": now.strftime("%H:%M UTC"), "event": "Remediation applied"},
    ]
    went_well  = incident.get("went_well") or ["Automated detection by Prometheus/Alertmanager", "AtlasOps multi-agent response < 5 min"]
    went_wrong = incident.get("went_wrong") or ["Alert was not suppressed during maintenance window"]
    action_items = incident.get("action_items") or [
        {"action": f"Add runbook for {title}", "owner": "@sre-team", "priority": "P2", "due": "2026-06-01"},
        {"action": "Review alert thresholds", "owner": "@observability", "priority": "P3", "due": "2026-06-15"},
    ]
    if actions_taken:
        action_items.insert(0, {
            "action": f"Verify fix stability: {str(actions_taken[0])[:80]}",
            "owner": "@sre-oncall", "priority": "P1",
            "due": now.strftime("%Y-%m-%d"),
        })

    data = {
        "title": title, "severity": severity,
        "duration": incident.get("duration", "< 10 min"),
        "authors": incident.get("authors", "AtlasOps automated response"),
        "summary": incident.get("summary") or f"{severity} incident: {title}. Root cause: {root_cause[:120]}. Resolution: {resolution[:120]}.",
        "impact": incident.get("impact") or f"Services affected: {triage.get('blast_radius', {}).get('services', ['unknown'])}. User impact: {triage.get('blast_radius', {}).get('user_impact_pct', 0)}%.",
        "timeline": timeline,
        "root_cause": root_cause,
        "detection": incident.get("detection") or "Prometheus alert fired → Alertmanager forwarded to AtlasOps webhook.",
        "resolution": resolution,
        "went_well": went_well,
        "went_wrong": went_wrong,
        "action_items": action_items,
    }

    template = Template(POSTMORTEM_TEMPLATE)
    rendered = template.render(date=now.date().isoformat(), **data)
    POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        slug = title.lower().replace(" ", "-")[:60]
        output_path = str(POSTMORTEM_DIR / f"{now.date()}-{slug}.md")
    Path(output_path).write_text(rendered, encoding="utf-8")
    return {"success": True, "path": output_path, "postmortem_path": output_path, "bytes": len(rendered)}
