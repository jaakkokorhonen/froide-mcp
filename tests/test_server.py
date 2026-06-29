"""Integration tests: HTTP routes (/healthz, /auth/login, /auth/callback)."""
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
    # No oauth_state cookie set → state mismatch
    resp = client.get("/auth/callback?code=abc&state=wrongstate")
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["error"]
