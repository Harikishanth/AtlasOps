"""Tests for agents/_http_retry.py async retry logic."""

import asyncio
import pytest
import httpx


def test_immediate_success():
    from agents._http_retry import post_with_retry

    call_count = 0

    async def mock_handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as c:
            r = await post_with_retry(c, "http://test/v1", {}, context="test")
            assert r.status_code == 200

    asyncio.run(run())
    assert call_count == 1


def test_retry_on_429():
    from agents._http_retry import post_with_retry

    call_count = 0

    async def mock_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as c:
            r = await post_with_retry(c, "http://test/v1", {}, context="test429", base_backoff=0.1)
            assert r.status_code == 200

    asyncio.run(run())
    assert call_count == 3


def test_retry_on_503():
    from agents._http_retry import post_with_retry

    call_count = 0

    async def mock_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as c:
            r = await post_with_retry(c, "http://test/v1", {}, context="test503", base_backoff=0.1)
            assert r.status_code == 200

    asyncio.run(run())
    assert call_count == 2


def test_non_retryable_error_returns_immediately():
    from agents._http_retry import post_with_retry

    call_count = 0

    async def mock_handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, json={"error": "bad request"})

    transport = httpx.MockTransport(mock_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as c:
            r = await post_with_retry(c, "http://test/v1", {}, context="test400", base_backoff=0.1)
            assert r.status_code == 400

    asyncio.run(run())
    assert call_count == 1
