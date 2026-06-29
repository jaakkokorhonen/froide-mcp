"""Integration tests: HTTP routes and RequireSessionMiddleware."""
from __future__ import annotations
import pytest
from starlette.testclient import TestClient


def test_healthz():
    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_redirects_to_google():
    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True, follow_redirects=False)
    resp = client.get("/auth/login")
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]
    assert "oauth_state" in resp.cookies


def test_callback_rejects_invalid_state():
    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/auth/callback?code=abc&state=wrongstate")
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["error"]


# ---------------------------------------------------------------------------
# RequireSessionMiddleware
# ---------------------------------------------------------------------------

def test_mcp_without_session_returns_401():
    """Any /mcp request without X-Froide-Session must get 401."""
    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/mcp")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"] == "Unauthenticated"
    assert "/auth/login" in data["detail"]


def test_mcp_with_expired_token_returns_401(session_token):
    """A syntactically valid but expired token must be rejected with 401."""
    import time
    import json
    import base64
    import hmac
    import hashlib
    from froide_mcp.config import config

    # Build a token that expired 1 second ago
    payload = json.dumps(
        {"email": "test@example.com", "froide_token": "tok", "exp": int(time.time()) - 1}
    ).encode()
    payload_b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(config.session_secret.encode(), payload_b64, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig)
    expired_token = f"{payload_b64.decode()}.{sig_b64.decode()}"

    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/mcp", headers={"x-froide-session": expired_token})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_auth_login_bypasses_middleware():
    """Auth routes must be reachable without any session token."""
    from froide_mcp.server import app
    client = TestClient(app, raise_server_exceptions=True, follow_redirects=False)
    resp = client.get("/auth/login")
    # Must redirect to Google, not 401
    assert resp.status_code in (302, 307)
