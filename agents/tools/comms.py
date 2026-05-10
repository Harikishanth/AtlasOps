"""Communication tool wrappers — Slack updates + postmortem generation."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jinja2 import Template

log = logging.getLogger("atlasops.comms")


SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
POSTMORTEM_DIR = Path(os.getenv("POSTMORTEM_DIR", "docs/postmortems"))

_SEV_COLOR_HEX = {"P0": "ff0000", "P1": "ff8800", "P2": "ffcc00"}
_LOG_PATH = Path("data/slack_posts.jsonl")


def _discord_webhook_post_with_retry(url: str, json_body: dict[str, Any], *, context: str) -> tuple[bool, str | None]:
    """POST to a Discord Incoming Webhook; retry on 429 (burst limit) and transient 5xx.

    Incoming webhooks are easy to saturate: one scenario can emit approval embed + closure embed
    + every-run ping within seconds → Discord returns 429 with Retry-After.
    """
    last_err: str | None = None
    max_attempts = 8
    for attempt in range(max_attempts):
        try:
            r = requests.post(url, json=json_body, timeout=20)
            if r.status_code == 429:
                ra_raw = r.headers.get("Retry-After")
                try:
                    wait = float(ra_raw) if ra_raw is not None else 2.0
                except (TypeError, ValueError):
                    wait = 2.0
                wait = min(max(wait, 0.5), 60.0)
                log.warning(
                    "Discord 429 (%s); sleeping %.1fs then retry (%d/%d)",
                    context, wait, attempt + 1, max_attempts,
                )
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600 and attempt < max_attempts - 1:
                time.sleep(1.0 + attempt * 0.5)
                continue
            r.raise_for_status()
            return True, None
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < max_attempts - 1:
                time.sleep(1.0 + attempt * 0.75)
                continue
    log.warning("Discord webhook failed after retries (%s): %s", context, last_err)
    return False, last_err


def discord_scenario_run_ping(
    incident_id: str,
    alert: dict[str, Any],
    *,
    resolved: bool,
    triage_title: str,
    triage_severity: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Always send **one** short Discord embed per incident run when `DISCORD_WEBHOOK_URL` is set.

    Separate from agent `slack_post_update` calls — survives LLM skips and shows up every scenario.
    Set `ATLASOPS_DISCORD_EVERY_RUN_PING=0` to disable.

    Returns a small dict for logging/tests; failures are swallowed after logging except in strict flows.
    """
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    disabled = os.getenv("ATLASOPS_DISCORD_EVERY_RUN_PING", "1").strip().lower() in ("0", "false", "no", "off")
    if not url or disabled:
        return {"ok": False, "skipped": True, "reason": "no webhook or disabled"}

    scenario_id = _trunc(str(alert.get("scenario_id") or alert.get("commonLabels", {}).get("scenario_id") or ""), 200)
    alertname = _trunc(str(alert.get("commonLabels", {}).get("alertname") or "live-alert"), 200)
    triage_title = _trunc(str(triage_title or ""), 200) or "(no title yet)"
    sev_disp = _trunc(str(triage_severity or "—"), 8)

    if error:
        color = int("ED4245", 16)
        footer = "AtlasOps · scenario run ended with exception"
        status_line = "**Run ended with error** (see coordinator logs)."
    elif resolved:
        color = int("57F287", 16)
        footer = "AtlasOps · scenario run finished"
        status_line = "**Pipeline completed** (remediation outcome: resolved)."
    else:
        color = int("FEE75C", 16)
        footer = "AtlasOps · scenario run finished"
        status_line = "**Pipeline finished** — not flagged resolved (manual / partial / escalation)."

    scenario_display = scenario_id if scenario_id.strip() else "—"
    desc_lines = [
        f"**{status_line}**",
        f"**Incident** `{incident_id}`",
        f"**Alert** {alertname}",
        f"**Scenario / inject** `{scenario_display}`",
        f"**Triage severity** `{sev_disp}` — **topic** {_trunc(triage_title, 300)}",
    ]
    if error:
        desc_lines.append("")
        desc_lines.append("```")
        desc_lines.append(_trunc(error, 900))
        desc_lines.append("```")

    body = {
        "username": _trunc(os.getenv("DISCORD_BOT_USERNAME", "atlasops-bot"), 80),
        "embeds": [{
            "title": _trunc(f"Scenario run complete · [{sev_disp}]", 256),
            "description": _trunc("\n".join(desc_lines), 3900),
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": _trunc(footer, 2048)},
        }],
    }

    ok, err = _discord_webhook_post_with_retry(url, body, context=f"every-run ping {incident_id}")
    if ok:
        log.info("Discord every-run ping sent for incident %s", incident_id)
        return {"ok": True, "sent": True, "mode": "discord_ping"}
    return {"ok": False, "error": err or "unknown"}


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


def _trunc(s: str, max_len: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _post_to_discord(slack_payload: dict) -> None:
    """Convert Slack payload to Discord embed and POST."""
    att = slack_payload["attachments"][0]
    raw_title = att.get("title") or "[P3] Incident"
    sev_key = raw_title.split("]")[0].lstrip("[").strip() if "]" in raw_title else "P3"
    try:
        color_int = int(_SEV_COLOR_HEX.get(sev_key, "888888"), 16)
    except ValueError:
        color_int = int("888888", 16)
    fields_raw = []
    for f in att.get("fields", []) or []:
        if not f.get("value"):
            continue
        fields_raw.append({
            "name": _trunc(str(f.get("title", "")), 256),
            "value": _trunc(str(f["value"]), 1024),
            "inline": False,
        })
    discord_payload = {
        "username": _trunc(slack_payload.get("username", "atlasops-bot"), 80),
        "embeds": [{
            "title": _trunc(raw_title, 256),
            "description": _trunc(att.get("text", ""), 4000),
            "color": color_int,
            "fields": fields_raw[:25],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "AtlasOps · AMD MI300X"},
        }],
    }
    ok, err = _discord_webhook_post_with_retry(DISCORD_WEBHOOK, discord_payload, context="slack-style embed")
    if not ok:
        log.warning("Discord webhook (embed) failed: %s", err)
        raise requests.RequestException(err or "Discord webhook failed")


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
            log.info("Discord embed delivered for [%s]", (payload["attachments"][0].get("title") or "")[:80])
        except requests.RequestException as e:
            err = f"discord: {e}"
            errors.append(err)
            log.warning(err)

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
