"""Smoke tests: run against the real deployed service.

These checks verify more than simple liveness:
- the deployed service is reachable
- auth middleware rejects missing or bad session tokens with 401
- with a valid session token, the service can reach Froide and complete at
  least one read-only end-to-end tool path

Skipped automatically unless SMOKE_TEST_URL is set. Tests that require a
session token are skipped unless SMOKE_SESSION_TOKEN is also set.
"""
from __future__ import annotations

import os

import httpx
import pytest

SMOKE_URL = os.environ.get("SMOKE_TEST_URL", "")
SMOKE_TOKEN = os.environ.get("SMOKE_SESSION_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not SMOKE_URL,
    reason="SMOKE_TEST_URL not set",
)


@pytest.fixture(scope="module")
def anonymous_client() -> httpx.Client:
    return httpx.Client(
        base_url=SMOKE_URL,
        timeout=15.0,
        follow_redirects=True,
    )


@pytest.fixture(scope="module")
def authenticated_client() -> httpx.Client:
    headers = {"X-Froide-Session": SMOKE_TOKEN} if SMOKE_TOKEN else {}
    return httpx.Client(
        base_url=SMOKE_URL,
        headers=headers,
        timeout=20.0,
        follow_redirects=True,
    )


# ── Liveness ────────────────────────────────────────────────────────────────


def test_healthz_responds(anonymous_client: httpx.Client) -> None:
    """Service is up and returns healthy."""
    r = anonymous_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Auth middleware behaviour ────────────────────────────────────────────────


def test_mcp_requires_auth_without_session(anonymous_client: httpx.Client) -> None:
    """Unauthenticated requests must be rejected by middleware with 401.

    The response must come from RequireSessionMiddleware and carry the expected
    JSON error structure, not be a generic 404/405 transport artefact.
    """
    r = anonymous_client.get("/mcp")
    assert r.status_code == 401
    data = r.json()
    assert data["error"] == "Unauthenticated"
    assert "/auth/login" in data["detail"]


@pytest.mark.skipif(not SMOKE_TOKEN, reason="SMOKE_SESSION_TOKEN not set")
def test_invalid_session_token_rejected() -> None:
    """Requests with a structurally invalid session token must return 401."""
    bad_client = httpx.Client(
        base_url=SMOKE_URL,
        headers={"X-Froide-Session": "totally.invalid.token"},
        timeout=10.0,
    )
    r = bad_client.get("/mcp")
    assert r.status_code == 401
    error_val = r.json().get("error", "").lower()
    assert "invalid" in error_val or "expired" in error_val


# ── Authenticated path ───────────────────────────────────────────────────────


@pytest.mark.skipif(not SMOKE_TOKEN, reason="SMOKE_SESSION_TOKEN not set")
def test_authenticated_mcp_mount_is_not_rejected(
    authenticated_client: httpx.Client,
) -> None:
    """A valid session token must pass auth middleware on /mcp.

    We do not pin exact FastMCP transport semantics here. The only requirement
    is that the request is no longer rejected as unauthenticated.
    """
    r = authenticated_client.get("/mcp")
    assert r.status_code != 401
    assert r.status_code < 500


@pytest.mark.skipif(not SMOKE_TOKEN, reason="SMOKE_SESSION_TOKEN not set")
def test_authenticated_profile_tool_path_reaches_froide(
    authenticated_client: httpx.Client,
) -> None:
    """Authenticated smoke: prove the deployed service can reach Froide.

    Calls get_my_profile via JSON-RPC. This is a read-only, non-mutating tool
    that is safe to invoke in production. A successful response proves the full
    end-to-end path works:

        Cloud Run -> RequireSessionMiddleware -> token decode
        -> Froide bearer token -> Froide API /api/v1/user/

    We intentionally do NOT use mutating tools (make_request, send_followup,
    etc.) in smoke tests.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": "smoke-get-my-profile",
        "method": "tools/call",
        "params": {
            "name": "get_my_profile",
            "arguments": {},
        },
    }
    r = authenticated_client.post("/mcp", json=payload)
    assert r.status_code < 500, f"Unexpected server error: {r.status_code} {r.text}"
    assert r.status_code != 401, "Valid session token was rejected during E2E smoke"

    body = r.json()
    assert body.get("jsonrpc") == "2.0", body
    assert body.get("id") == "smoke-get-my-profile", body
    assert "error" not in body, f"Tool call returned error: {body}"
    assert "result" in body, f"Tool call returned no result: {body}"
