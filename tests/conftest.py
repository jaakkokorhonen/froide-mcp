"""Shared pytest fixtures."""
from __future__ import annotations
import os
import pytest
import respx
import httpx

# Minimal env so config.py imports without real secrets
os.environ.setdefault("FROIDE_BASE_URL", "http://froide.test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-secret")
os.environ.setdefault("SESSION_SECRET", "a" * 64)
os.environ.setdefault("ALLOWED_HD", "")
os.environ.setdefault("FROIDE_CLIENT_ID", "test-froide-client-id")
os.environ.setdefault("FROIDE_CLIENT_SECRET", "test-froide-secret")
os.environ.setdefault("MCP_BASE_URL", "http://localhost:8080")


@pytest.fixture
def froide_token() -> str:
    return "test-bearer-token-abc123"


@pytest.fixture
def session_token(froide_token: str) -> str:
    from froide_mcp.auth import create_session_token
    return create_session_token(email="admin@example.com", froide_token=froide_token)


@pytest.fixture
def mock_froide():
    """respx mock that intercepts all httpx calls to http://froide.test."""
    with respx.mock(base_url="http://froide.test", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def starlette_client(session_token: str):
    """Starlette TestClient with X-Froide-Session pre-set."""
    from starlette.testclient import TestClient
    from froide_mcp.server import app
    return TestClient(app, headers={"X-Froide-Session": session_token})
