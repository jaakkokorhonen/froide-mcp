"""Main entry point: mounts FastMCP HTTP app and Google OAuth2 auth routes.

All requests to /mcp/* MUST carry a valid X-Froide-Session header obtained
via the Google SSO flow at /auth/login.  The RequireSessionMiddleware
enforces this at the Starlette layer so no individual tool needs to worry
about missing tokens.
"""
from __future__ import annotations

import secrets
from typing import Awaitable, Callable

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from froide_mcp.auth import (
    create_session_token,
    decode_session_token,
    exchange_google_code,
    get_froide_token,
    google_auth_url,
    verify_hd,
)
from froide_mcp.config import config
from froide_mcp.tools import mcp  # registers all @mcp.tool() decorators


# ── Middleware: enforce Google SSO on every /mcp/* request ────────────────


class RequireSessionMiddleware(BaseHTTPMiddleware):
    """Block any /mcp/* request that lacks a valid, non-expired session token.

    Returns 401 JSON so MCP clients (Claude, Cursor…) can surface the error
    cleanly.  Requests to /auth/* and /healthz pass through unconditionally.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if path.startswith("/auth/") or path == "/healthz":
            return await call_next(request)

        if path.startswith("/mcp"):
            raw = request.headers.get("x-froide-session", "")
            if not raw:
                return JSONResponse(
                    {
                        "error": "Unauthenticated",
                        "detail": (
                            "Visit /auth/login to authenticate with Google SSO, "
                            "then include the returned token as X-Froide-Session header."
                        ),
                    },
                    status_code=401,
                )
            try:
                decode_session_token(raw)
            except ValueError as exc:
                return JSONResponse(
                    {"error": "Invalid or expired session token", "detail": str(exc)},
                    status_code=401,
                )

        return await call_next(request)


# ── Auth routes ──────────────────────────────────────────────────


async def login(request: Request) -> Response:
    """Redirect the user to Google for authentication."""
    state = secrets.token_urlsafe(16)
    url = google_auth_url(state=state)
    response: Response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=300)
    return response


async def callback(request: Request) -> Response:
    """Handle Google OAuth2 callback, issue a session token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    stored_state = request.cookies.get("oauth_state")

    if not code or state != stored_state:
        return JSONResponse({"error": "Invalid OAuth2 callback"}, status_code=400)

    try:
        claims = exchange_google_code(code)
        verify_hd(claims)
        froide_token = get_froide_token()
        session_token = create_session_token(
            email=claims["email"],
            froide_token=froide_token,
        )
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"error": f"Auth failed: {e}"}, status_code=500)

    return HTMLResponse(
        f"""<!doctype html><html><body>
        <h2>Authenticated ✓</h2>
        <p>Email: {claims['email']}</p>
        <p>Include this header in all MCP requests:</p>
        <pre>X-Froide-Session: {session_token}</pre>
        <p>Token expires in 8 hours.</p>
        </body></html>"""
    )


async def healthz(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


# ── Application assembly ──────────────────────────────────────────────────

auth_routes = [
    Route("/auth/login", login),
    Route("/auth/callback", callback),
    Route("/healthz", healthz),
]

# fastmcp 3.x: http_app() replaces the removed sse_app()
mcp_app = mcp.http_app()

app = Starlette(
    routes=auth_routes,
    middleware=[Middleware(RequireSessionMiddleware)],
)

app.mount("/mcp", mcp_app)


def main() -> None:
    uvicorn.run(
        "froide_mcp.server:app",
        host="0.0.0.0",
        port=config.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
