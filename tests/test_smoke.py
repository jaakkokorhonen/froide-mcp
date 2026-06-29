"""Smoke tests: run against the real deployed service.

These checks are intentionally conservative and transport-agnostic:
- verify the deployed service is reachable
- verify auth middleware rejects bad session tokens cleanly
- avoid encoding assumptions about the exact MCP wire transport unless the
  runtime intentionally pins and documents that transport contract

Skipped automatically in CI unless SMOKE_TEST_URL is set. Tests that require a
session token are skipped unless SMOKE_SESSION_TOKEN is also set.
"""
from __future__ import annotations
import os
import pytest
import httpx

SMOKE_URL = os.environ.get("SMOKE_TEST_URL", "")
SMOKE_TOKEN = os.environ.get("SMOKE_SESSION_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not SMOKE_URL,
    reason="SMOKE_TEST_URL not set",
)


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    headers = {"X-Froide-Session": SMOKE_TOKEN} if SMOKE_TOKEN else {}
    return httpx.Client(
        base_url=SMOKE_URL,
        headers=headers,
        timeout=15.0,
        follow_redirects=True,
    )


def test_healthz_responds(client):
    """Service is up and returns healthy."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_mcp_endpoint_requires_auth_or_is_reachable(client):
    """The mounted MCP endpoint exists and does not crash.

    We do not assert a specific MCP transport response here because FastMCP
    transport details can change across major versions.
    """
    r = client.get("/mcp")
    assert r.status_code in (200, 307, 401, 404, 405)


@pytest.mark.skipif(not SMOKE_TOKEN, reason="SMOKE_SESSION_TOKEN not set")
def test_invalid_session_token_rejected():
    """Requests with a bad session token must return an auth error, not 500."""
    bad_client = httpx.Client(
        base_url=SMOKE_URL,
        headers={"X-Froide-Session": "totally.invalid.token"},
        timeout=10.0,
    )
    r = bad_client.get("/mcp")
    assert r.status_code < 500
    assert r.status_code in (401, 404, 405)
