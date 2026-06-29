"""MCP tool definitions for the Froide FOI platform."""
from __future__ import annotations

from typing import Optional
from fastmcp import FastMCP, Context
from froide_mcp.client import FroideClient
from froide_mcp.auth import decode_session_token

mcp = FastMCP("froide")


def _token_from_ctx(ctx: Context) -> str:
    """Extract the Froide bearer token from the MCP session context."""
    raw = ctx.request_context.request.headers.get("x-froide-session", "")
    if not raw:
        raise PermissionError("Missing X-Froide-Session header. Authenticate at /auth/login first.")
    return decode_session_token(raw)["froide_token"]


@mcp.tool()
async def list_requests(
    ctx: Context,
    status: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
) -> dict:
    """List FOI requests. Filter by status (e.g. 'awaiting_response', 'successful') or search query."""
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


@mcp.tool()
async def list_attachments(ctx: Context, request_id: int) -> dict:
    """List all attachments (documents) for a FOI request."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/attachment/", belongs_to=request_id)


@mcp.tool()
async def get_law(ctx: Context, law_id: int) -> dict:
    """Get information about a FOI law (e.g. which authorities it applies to)."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/law/{law_id}/")
