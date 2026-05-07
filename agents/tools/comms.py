"""Communication tool wrappers — Slack updates + postmortem generation."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jinja2 import Template


SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
POSTMORTEM_DIR = Path(os.getenv("POSTMORTEM_DIR", "docs/postmortems"))


def slack_post_update(channel: str, severity: str, title: str, summary: str,
                      action_items: list[str] | None = None) -> dict[str, Any]:
    """Post an incident update to Slack. If no webhook is configured, log to local file."""
    payload = {
        "channel": channel,
        "username": "cloudsre-bot",
        "icon_emoji": ":rotating_light:" if severity in ("P0", "P1") else ":warning:",
        "attachments": [
            {
                "color": {"P0": "#ff0000", "P1": "#ff8800", "P2": "#ffcc00"}.get(severity, "#888"),
                "title": f"[{severity}] {title}",
                "text": summary,
                "fields": [{"title": "Action Items", "value": "\n".join(f"• {a}" for a in (action_items or []))}] if action_items else [],
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }
        ],
    }
    if not SLACK_WEBHOOK:
        log_path = Path("data/slack_posts.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        return {"success": True, "mode": "logged_locally", "path": str(log_path)}
    try:
        r = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        r.raise_for_status()
        return {"success": True, "mode": "posted"}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


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

    incident dict shape:
      title, severity, duration, authors, summary, impact,
      timeline: [{time, event}], root_cause, detection, resolution,
      went_well: [str], went_wrong: [str],
      action_items: [{action, owner, priority, due}]
    """
    template = Template(POSTMORTEM_TEMPLATE)
    rendered = template.render(
        date=incident.get("date", datetime.now(timezone.utc).date().isoformat()),
        **incident,
    )
    POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        slug = incident.get("title", "incident").lower().replace(" ", "-")[:60]
        output_path = str(POSTMORTEM_DIR / f"{datetime.now(timezone.utc).date()}-{slug}.md")
    Path(output_path).write_text(rendered, encoding="utf-8")
    return {"success": True, "path": output_path, "bytes": len(rendered)}
