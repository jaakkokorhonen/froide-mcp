"""Google OAuth2 SSO + Froide token exchange.

Flow:
1. MCP client hits GET /auth/login  → redirected to Google
2. Google redirects to GET /auth/callback?code=...
3. We verify the ID token, check hd (hosted domain) if configured
4. Exchange for a Froide OAuth2 bearer token via client_credentials
5. Return a signed session token to the MCP client
"""
from __future__ import annotations

import time
import json
import base64
import hashlib
import hmac
import httpx
from urllib.parse import urlencode

from froide_mcp.config import config


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"


def _redirect_uri() -> str:
    return f"{config.mcp_base_url}/auth/callback"


def google_auth_url(state: str) -> str:
    """Build the Google OAuth2 authorisation URL."""
    params: dict[str, str] = {
        "client_id": config.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }
    if config.allowed_hd:
        params["hd"] = config.allowed_hd
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_google_code(code: str) -> dict:
    """Exchange authorisation code for Google tokens. Returns the ID token claims.

    Note: this implementation decodes the JWT payload without verifying the
    Google JWKS signature.  The token is received over a direct server-to-server
    HTTPS POST to accounts.google.com so the transport-level trust is high, but
    for stronger security consider validating with google-auth or PyJWT +
    GOOGLE_CERTS_URL before relying on the claims in production.
    """
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    tokens = resp.json()
    # Decode JWT payload (base64url, middle segment)
    id_token = tokens["id_token"]
    payload_b64 = id_token.split(".")[1]
    # Pad base64
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    return claims


def verify_hd(claims: dict) -> None:
    """Raise if the Google account domain doesn't match ALLOWED_HD."""
    if not config.allowed_hd:
        return
    hd = claims.get("hd", "")
    if hd != config.allowed_hd:
        raise PermissionError(
            f"Google account domain '{hd}' is not allowed. "
            f"Expected '{config.allowed_hd}'."
        )


def get_froide_token() -> str:
    """Obtain a Froide OAuth2 bearer token via client_credentials grant."""
    resp = httpx.post(
        f"{config.froide_base_url}/o/token/",
        data={
            "grant_type": "client_credentials",
            "client_id": config.froide_client_id,
            "client_secret": config.froide_client_secret,
            "scope": "read:request read:profile make:request",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Signed session tokens ──────────────────────────────────────────────────
# Simple HMAC-SHA256 signed token: base64(payload) + "." + base64(sig)
# No JWT dependency. TTL: 8 hours.

TOKEN_TTL = 8 * 3600


def _sign(data: bytes) -> bytes:
    return hmac.new(config.session_secret.encode(), data, hashlib.sha256).digest()


def create_session_token(email: str, froide_token: str) -> str:
    payload = json.dumps(
        {"email": email, "froide_token": froide_token, "exp": int(time.time()) + TOKEN_TTL}
    ).encode()
    payload_b64 = base64.urlsafe_b64encode(payload)
    sig_b64 = base64.urlsafe_b64encode(_sign(payload_b64))
    return f"{payload_b64.decode()}.{sig_b64.decode()}"


def decode_session_token(token: str) -> dict:
    """Verify and decode. Raises ValueError on invalid/expired token."""
    try:
        payload_b64_str, sig_b64_str = token.rsplit(".", 1)
    except ValueError:
        raise ValueError("Malformed token")
    payload_b64 = payload_b64_str.encode()
    expected_sig = base64.urlsafe_b64encode(_sign(payload_b64))
    if not hmac.compare_digest(expected_sig, sig_b64_str.encode()):
        raise ValueError("Invalid token signature")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    if payload["exp"] < time.time():
        raise ValueError("Token expired")
    return payload
