"""Smoke tests: run against the real deployed service.

Skipped automatically in CI unless SMOKE_TEST_URL and SMOKE_SESSION_TOKEN
are set as environment variables. Intended for:
  - post-deploy verification in deploy.yml
  - nightly monitoring in monitor.yml
"""
from __future__ import annotations
import os
import pytest
import httpx

SMOKE_URL = os.environ.get("SMOKE_TEST_URL", "")
SMOKE_TOKEN = os.environ.get("SMOKE_SESSION_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not SMOKE_URL or not SMOKE_TOKEN,
    reason="SMOKE_TEST_URL and SMOKE_SESSION_TOKEN not set",
)


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    return httpx.Client(
        base_url=SMOKE_URL,
        headers={"X-Froide-Session": SMOKE_TOKEN},
        timeout=15.0,
        follow_redirects=True,
    )


def test_healthz_responds(client):
    """Service is up and returns healthy."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_mcp_sse_endpoint_reachable(client):
    """MCP SSE endpoint accepts connections."""
    # HEAD or GET /mcp — FastMCP returns 200 on GET with SSE headers
    r = client.get("/mcp", headers={"Accept": "text/event-stream"})
    assert r.status_code in (200, 405)  # 405 = wrong method but service alive


def test_list_requests_tool_responds(client):
    """list_requests tool returns a valid Froide API response shape."""
    # Call the tool via MCP JSON-RPC over HTTP
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_requests",
                "arguments": {"status": "awaiting_response"},
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "result" in body or "error" in body  # valid JSON-RPC envelope


def test_list_public_bodies_tool_responds(client):
    """list_public_bodies tool returns results without crashing."""
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "list_public_bodies",
                "arguments": {"q": "test"},
            },
        },
    )
    assert r.status_code == 200


def test_invalid_session_token_rejected(client):
    """Requests with a bad session token must return an error, not 500."""
    bad_client = httpx.Client(
        base_url=SMOKE_URL,
        headers={"X-Froide-Session": "totally.invalid.token"},
        timeout=10.0,
    )
    r = bad_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_requests", "arguments": {}},
        },
    )
    # Must not be a 5xx server crash
    assert r.status_code < 500
