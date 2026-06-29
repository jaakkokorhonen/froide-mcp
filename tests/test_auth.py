"""Unit tests for session token signing."""
import os
import time
import pytest

os.environ.setdefault("FROIDE_BASE_URL", "http://localhost:8000")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("SESSION_SECRET", "a" * 64)
os.environ.setdefault("ALLOWED_HD", "")
os.environ.setdefault("FROIDE_CLIENT_ID", "test")
os.environ.setdefault("FROIDE_CLIENT_SECRET", "test")
os.environ.setdefault("MCP_BASE_URL", "http://localhost:8080")

from froide_mcp.auth import create_session_token, decode_session_token


def test_roundtrip():
    token = create_session_token(email="test@example.com", froide_token="abc123")
    payload = decode_session_token(token)
    assert payload["email"] == "test@example.com"
    assert payload["froide_token"] == "abc123"
    assert payload["exp"] > time.time()


def test_tampered_token_rejected():
    token = create_session_token(email="test@example.com", froide_token="abc123")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(ValueError, match="Invalid token signature"):
        decode_session_token(tampered)


def test_hd_verification():
    from froide_mcp.auth import verify_hd
    from unittest.mock import patch
    with patch("froide_mcp.auth.config") as mock_cfg:
        mock_cfg.allowed_hd = "company.fi"
        with pytest.raises(PermissionError):
            verify_hd({"hd": "other.com", "email": "user@other.com"})
        verify_hd({"hd": "company.fi", "email": "user@company.fi"})  # should not raise
