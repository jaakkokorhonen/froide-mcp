"""Unit tests: session token signing and Google OAuth2 helpers."""
from __future__ import annotations
import dataclasses
import time
import pytest
import froide_mcp.auth as auth_mod
from froide_mcp.auth import (
    create_session_token,
    decode_session_token,
    google_auth_url,
    verify_hd,
)


class TestSessionToken:
    def test_roundtrip(self):
        token = create_session_token(email="u@example.com", froide_token="tok")
        p = decode_session_token(token)
        assert p["email"] == "u@example.com"
        assert p["froide_token"] == "tok"
        assert p["exp"] > time.time()

    def test_tampered_rejected(self):
        token = create_session_token(email="u@example.com", froide_token="tok")
        with pytest.raises(ValueError, match="Invalid token signature"):
            decode_session_token(token[:-4] + "XXXX")

    def test_malformed_rejected(self):
        with pytest.raises(ValueError, match="Malformed"):
            decode_session_token("notavalidtoken")

    def test_expired_rejected(self, monkeypatch):
        monkeypatch.setattr(auth_mod, "TOKEN_TTL", -1)
        token = create_session_token(email="u@example.com", froide_token="tok")
        with pytest.raises(ValueError, match="expired"):
            decode_session_token(token)


class TestGoogleHelpers:
    def test_auth_url_contains_client_id(self):
        url = google_auth_url(state="abc")
        assert "test-google-client-id" in url
        assert "response_type=code" in url

    def test_auth_url_includes_hd_when_set(self, monkeypatch):
        monkeypatch.setattr(
            auth_mod, "config", dataclasses.replace(auth_mod.config, allowed_hd="company.fi")
        )
        url = google_auth_url(state="s")
        assert "hd=company.fi" in url

    def test_verify_hd_passes_matching(self, monkeypatch):
        monkeypatch.setattr(
            auth_mod, "config", dataclasses.replace(auth_mod.config, allowed_hd="company.fi")
        )
        verify_hd({"hd": "company.fi"})  # must not raise

    def test_verify_hd_rejects_other_domain(self, monkeypatch):
        monkeypatch.setattr(
            auth_mod, "config", dataclasses.replace(auth_mod.config, allowed_hd="company.fi")
        )
        with pytest.raises(PermissionError):
            verify_hd({"hd": "evil.com"})

    def test_verify_hd_skipped_when_empty(self, monkeypatch):
        monkeypatch.setattr(
            auth_mod, "config", dataclasses.replace(auth_mod.config, allowed_hd="")
        )
        verify_hd({"hd": "anyone.com"})  # must not raise
