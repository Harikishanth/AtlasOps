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
