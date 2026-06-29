"""MCP tool definitions for the Froide FOI platform.

All tools require a valid Google-SSO session (enforced by RequireSessionMiddleware
in server.py).  Individual tools call _token_from_ctx() to extract the Froide
bearer token from the already-validated session.
"""
from __future__ import annotations

from typing import Optional
from fastmcp import FastMCP, Context
from froide_mcp.client import FroideClient
from froide_mcp.auth import decode_session_token

mcp = FastMCP("froide")


def _token_from_ctx(ctx: Context) -> str:
    """Extract the Froide bearer token from the MCP session context.

    The token is guaranteed to be valid here because RequireSessionMiddleware
    already rejected any request with a missing or expired session token.
    """
    raw = ctx.request_context.request.headers.get("x-froide-session", "")
    if not raw:
        # Should never reach this branch — middleware guards the /mcp prefix.
        raise PermissionError(
            "Missing X-Froide-Session header. Authenticate via Google SSO at /auth/login."
        )
    return decode_session_token(raw)["froide_token"]


# ── FOI Requests ──────────────────────────────────────────────────────────

@mcp.tool()
async def list_requests(
    ctx: Context,
    status: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
) -> dict:
    """List FOI requests. Filter by status (e.g. 'awaiting_response', 'successful') or search query.

    status options: awaiting_user_confirmation, publicbody_needed, awaiting_publicbody_confirmation,
    awaiting_response, awaiting_classification, classification_needed, has_fee, refused,
    partially_successful, successful, not_held, gone_postal, user_withdrew_costs,
    user_withdrew, resolved, requires_user_action.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/request/", status=status, q=q, page=page)


@mcp.tool()
async def get_request(ctx: Context, request_id: int) -> dict:
    """Get a single FOI request with all its messages and metadata."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/request/{request_id}/")


@mcp.tool()
async def search_requests(ctx: Context, q: str, page: int = 1) -> dict:
    """Full-text search across FOI requests."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/request/", q=q, page=page)


@mcp.tool()
async def make_request(
    ctx: Context,
    public_body_id: int,
    subject: str,
    body: str,
    law_id: Optional[int] = None,
    campaign_id: Optional[int] = None,
    public: bool = True,
) -> dict:
    """Submit a new FOI request to a public body.

    Args:
        public_body_id: ID of the authority to send the request to.
        subject: Subject line of the request.
        body: Body text of the request.
        law_id: Optional Froide law ID. If omitted Froide picks the default law
                for the public body's jurisdiction.
        campaign_id: Optional campaign to attach the request to.
        public: Whether the request should be publicly visible (default True).
    """
    token = _token_from_ctx(ctx)
    payload: dict = {
        "publicbody": public_body_id,
        "subject": subject,
        "body": body,
        "public": public,
    }
    if law_id:
        payload["law"] = law_id
    if campaign_id:
        payload["campaign"] = campaign_id
    async with FroideClient(token) as c:
        return await c.post("/api/v1/request/", payload)


@mcp.tool()
async def send_followup(
    ctx: Context,
    request_id: int,
    message: str,
    subject: Optional[str] = None,
) -> dict:
    """Send a follow-up message on an existing FOI request."""
    token = _token_from_ctx(ctx)
    body: dict = {"request": request_id, "message": message}
    if subject:
        body["subject"] = subject
    async with FroideClient(token) as c:
        return await c.post("/api/v1/message/", body)


@mcp.tool()
async def set_request_status(
    ctx: Context,
    request_id: int,
    status: str,
    resolution: Optional[str] = None,
) -> dict:
    """Update the status of a FOI request you own.

    status options: awaiting_response, awaiting_classification, successful,
    partially_successful, refused, not_held, gone_postal, user_withdrew.
    resolution is an optional free-text explanation.
    """
    token = _token_from_ctx(ctx)
    payload: dict = {"status": status}
    if resolution:
        payload["resolution"] = resolution
    async with FroideClient(token) as c:
        return await c.patch(f"/api/v1/request/{request_id}/", payload)


# ── Public bodies ─────────────────────────────────────────────────────────

@mcp.tool()
async def list_public_bodies(
    ctx: Context,
    q: Optional[str] = None,
    jurisdiction: Optional[int] = None,
    page: int = 1,
) -> dict:
    """List or search public bodies (authorities). Filter by name or jurisdiction ID."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/publicbody/", q=q, jurisdiction=jurisdiction, page=page)


@mcp.tool()
async def get_public_body(ctx: Context, public_body_id: int) -> dict:
    """Get detailed information about a single public body."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/publicbody/{public_body_id}/")


# ── Jurisdictions ─────────────────────────────────────────────────────────

@mcp.tool()
async def list_jurisdictions(ctx: Context, page: int = 1) -> dict:
    """List all jurisdictions (e.g. national, regional) available in Froide."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/jurisdiction/", page=page)


# ── Campaigns ─────────────────────────────────────────────────────────────

@mcp.tool()
async def list_campaigns(ctx: Context, page: int = 1) -> dict:
    """List all FOI campaigns."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/campaign/", page=page)


@mcp.tool()
async def get_campaign(ctx: Context, campaign_id: int) -> dict:
    """Get a single campaign including its description and participating public bodies."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/campaign/{campaign_id}/")


# ── Attachments ───────────────────────────────────────────────────────────

@mcp.tool()
async def list_attachments(ctx: Context, request_id: int) -> dict:
    """List all attachments (documents) for a FOI request."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/attachment/", belongs_to=request_id)


# ── Laws ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_law(ctx: Context, law_id: int) -> dict:
    """Get information about a FOI law (e.g. which authorities it applies to)."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/law/{law_id}/")


@mcp.tool()
async def list_laws(
    ctx: Context,
    jurisdiction: Optional[int] = None,
    page: int = 1,
) -> dict:
    """List FOI laws. Optionally filter by jurisdiction ID."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/law/", jurisdiction=jurisdiction, page=page)


# ── User profile ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_my_profile(ctx: Context) -> dict:
    """Get the authenticated user's Froide profile (name, email, request stats)."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/user/")
