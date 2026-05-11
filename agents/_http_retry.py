"""Async HTTP POST with retry for HF Inference Router 429/5xx and transient errors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("atlasops.http_retry")


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json: dict[str, Any],
    *,
    context: str = "",
    max_attempts: int = 5,
    base_backoff: float = 1.5,
) -> httpx.Response:
    """POST with retry on 429, 5xx, and transient connection errors.

    Returns the first successful response or raises the last exception.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            r = await client.post(url, json=json)
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                try:
                    wait = float(ra) if ra is not None else base_backoff * (attempt + 1)
                except (TypeError, ValueError):
                    wait = base_backoff * (attempt + 1)
                wait = min(max(wait, 0.5), 60.0)
                log.warning(
                    "HF 429 (%s); retry %d/%d after %.1fs",
                    context, attempt + 1, max_attempts, wait,
                )
                await asyncio.sleep(wait)
                continue
            if 500 <= r.status_code < 600 and attempt < max_attempts - 1:
                wait = base_backoff * (attempt + 1)
                log.warning(
                    "HF %d (%s); retry %d/%d after %.1fs",
                    r.status_code, context, attempt + 1, max_attempts, wait,
                )
                await asyncio.sleep(wait)
                continue
            return r
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exc = e
            if attempt < max_attempts - 1:
                wait = base_backoff * (attempt + 1)
                log.warning(
                    "HF transient %s (%s); retry %d/%d after %.1fs",
                    type(e).__name__, context, attempt + 1, max_attempts, wait,
                )
                await asyncio.sleep(wait)
                continue
            raise
    if last_exc:
        raise last_exc
    raise httpx.HTTPError(f"post_with_retry exhausted {max_attempts} attempts ({context})")
