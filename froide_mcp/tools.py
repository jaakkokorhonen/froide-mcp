"""MCP tool definitions for the Froide FOI platform.

All tools require a valid Google-SSO session (enforced by RequireSessionMiddleware
in server.py).  Individual tools call _token_from_ctx() to extract the Froide
bearer token from the already-validated session.
"""
from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from froide_mcp.auth import decode_session_token
from froide_mcp.client import FroideClient

mcp: FastMCP = FastMCP("froide")


# ── Private helpers ───────────────────────────────────────────────────────


def _token_from_ctx(ctx: Context) -> str:
    """Extract the Froide bearer token from the MCP session context.

    The token is guaranteed to be valid here because RequireSessionMiddleware
    already rejected any request with a missing or expired session token.
    """
    rc = ctx.request_context
    raw: str = (
        rc.request.headers.get("x-froide-session", "")
        if rc is not None and rc.request is not None
        else ""
    )
    if not raw:
        # Should never reach this branch — middleware guards the /mcp prefix.
        raise PermissionError(
            "Missing X-Froide-Session header. Authenticate via Google SSO at /auth/login."
        )
    return decode_session_token(raw)["froide_token"]  # type: ignore[no-any-return]


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the 'results' list from a paginated Froide API payload."""
    results = payload.get("results")
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    return []


def _request_identifier(req: dict[str, Any]) -> str:
    rid = req.get("id")
    title = req.get("subject") or req.get("title") or "Untitled request"
    return f"#{rid} {title}" if rid is not None else str(title)


def _request_status(req: dict[str, Any]) -> str:
    return str(req.get("status") or "unknown")


def _contains_user_action_hint(req: dict[str, Any]) -> bool:
    """Heuristic: check free-text fields for keywords that suggest pending action."""
    haystack = " ".join(
        str(v).lower()
        for v in [
            req.get("resolution"),
            req.get("subject"),
            req.get("title"),
            req.get("description"),
        ]
        if v
    )
    return any(
        m in haystack
        for m in ("fee", "clarif", "user action", "requires action", "postal", "confirmation")
    )


_URGENT_STATUSES = {
    "requires_user_action",
    "awaiting_user_confirmation",
    "has_fee",
    "awaiting_classification",
    "classification_needed",
    "publicbody_needed",
    "awaiting_publicbody_confirmation",
}

_TRIAGE_STATUSES = list(_URGENT_STATUSES) + ["awaiting_response"]


def _priority_for_request(req: dict[str, Any]) -> tuple[int, str]:
    """Return (priority_score, human_rationale) for a request object."""
    status = _request_status(req)
    if status in {"requires_user_action", "awaiting_user_confirmation", "has_fee"}:
        return 100, "requires explicit user action"
    if status in {"awaiting_classification", "classification_needed"}:
        return 90, "needs user classification"
    if status in {"publicbody_needed", "awaiting_publicbody_confirmation"}:
        return 80, "public body selection or confirmation pending"
    if status == "awaiting_response":
        return 70, "waiting for authority response"
    if status in {"partially_successful", "successful"}:
        return 30, "request appears materially resolved"
    if status in {"refused", "not_held", "gone_postal", "user_withdrew", "resolved"}:
        return 20, "request appears closed or blocked"
    if _contains_user_action_hint(req):
        return 60, "metadata hints that follow-up may be needed"
    return 50, "general review queue"


def _derive_next_step(req: dict[str, Any]) -> str:
    """Return a plain-language suggested next action for the given request."""
    status = _request_status(req)
    if status in {"requires_user_action", "awaiting_user_confirmation", "has_fee"}:
        return "Open the request in the Froide UI and decide the requested user action before anything else."
    if status in {"awaiting_classification", "classification_needed"}:
        return "Review the latest response and classify the outcome in the Froide UI."
    if status in {"publicbody_needed", "awaiting_publicbody_confirmation"}:
        return "Confirm or correct the target public body in the Froide UI."
    if status == "awaiting_response":
        return "Check whether the statutory deadline is near or exceeded, then prepare a follow-up if needed."
    if status in {"partially_successful", "successful"}:
        return "Review attachments and confirm whether the request can be marked fully resolved."
    if status in {"refused", "not_held"}:
        return "Review the refusal reasoning and decide whether a clarification or appeal-style follow-up is needed."
    return "Review the request thread in the Froide UI and decide the next manual step."


# ── FOI Requests ──────────────────────────────────────────────────────────


@mcp.tool()
async def list_requests(
    ctx: Context,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
) -> dict[str, Any]:
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
async def get_request(ctx: Context, request_id: int) -> dict[str, Any]:
    """Get a single FOI request with all its messages and metadata."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/request/{request_id}/")


@mcp.tool()
async def search_requests(ctx: Context, q: str, page: int = 1) -> dict[str, Any]:
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
    law_id: int | None = None,
    campaign_id: int | None = None,
    public: bool = True,
) -> dict[str, Any]:
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
    payload: dict[str, Any] = {
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
    subject: str | None = None,
) -> dict[str, Any]:
    """Send a follow-up message on an existing FOI request."""
    token = _token_from_ctx(ctx)
    body: dict[str, Any] = {"request": request_id, "message": message}
    if subject:
        body["subject"] = subject
    async with FroideClient(token) as c:
        return await c.post("/api/v1/message/", body)


@mcp.tool()
async def set_request_status(
    ctx: Context,
    request_id: int,
    status: str,
    resolution: str | None = None,
) -> dict[str, Any]:
    """Update the status of a FOI request you own.

    status options: awaiting_response, awaiting_classification, successful,
    partially_successful, refused, not_held, gone_postal, user_withdrew.
    resolution is an optional free-text explanation.
    """
    token = _token_from_ctx(ctx)
    payload: dict[str, Any] = {"status": status}
    if resolution:
        payload["resolution"] = resolution
    async with FroideClient(token) as c:
        return await c.patch(f"/api/v1/request/{request_id}/", payload)


# ── Public bodies ─────────────────────────────────────────────────────────


@mcp.tool()
async def list_public_bodies(
    ctx: Context,
    q: str | None = None,
    jurisdiction: int | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """List or search public bodies (authorities). Filter by name or jurisdiction ID."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/publicbody/", q=q, jurisdiction=jurisdiction, page=page)


@mcp.tool()
async def get_public_body(ctx: Context, public_body_id: int) -> dict[str, Any]:
    """Get detailed information about a single public body."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/publicbody/{public_body_id}/")


# ── Jurisdictions ─────────────────────────────────────────────────────────


@mcp.tool()
async def list_jurisdictions(ctx: Context, page: int = 1) -> dict[str, Any]:
    """List all jurisdictions (e.g. national, regional) available in Froide."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/jurisdiction/", page=page)


# ── Campaigns ─────────────────────────────────────────────────────────────


@mcp.tool()
async def list_campaigns(ctx: Context, page: int = 1) -> dict[str, Any]:
    """List all FOI campaigns."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/campaign/", page=page)


@mcp.tool()
async def get_campaign(ctx: Context, campaign_id: int) -> dict[str, Any]:
    """Get a single campaign including its description and participating public bodies."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/campaign/{campaign_id}/")


# ── Attachments ───────────────────────────────────────────────────────────


@mcp.tool()
async def list_attachments(ctx: Context, request_id: int) -> dict[str, Any]:
    """List all attachments (documents) for a FOI request."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/attachment/", belongs_to=request_id)


# ── Laws ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_law(ctx: Context, law_id: int) -> dict[str, Any]:
    """Get information about a FOI law (e.g. which authorities it applies to)."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/law/{law_id}/")


@mcp.tool()
async def list_laws(
    ctx: Context,
    jurisdiction: int | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """List FOI laws. Optionally filter by jurisdiction ID."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/law/", jurisdiction=jurisdiction, page=page)


# ── User profile ──────────────────────────────────────────────────────────


@mcp.tool()
async def get_my_profile(ctx: Context) -> dict[str, Any]:
    """Get the authenticated user's Froide profile (name, email, request stats)."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/user/")


# ── Orchestration helpers ─────────────────────────────────────────────────
#
# These tools do not modify any Froide data. They compose existing API calls
# into higher-level operator workflows that guide work inside the Froide UI.
# No Django/Froide backend changes are required to use them.


@mcp.tool()
async def triage_my_requests(
    ctx: Context,
    statuses: list[str] | None = None,
    query: str | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Build a prioritised work queue from existing FOI requests.

    Queries the Froide API for requests across the most actionable statuses,
    scores each one by urgency and returns a ranked list with a plain-language
    suggested next step for each request.

    This tool does NOT change any request. Use it to decide what to work on
    next inside the Froide UI.

    Args:
        statuses: Override the default set of statuses to query. Defaults to
                  all statuses that typically require attention.
        query:    Optional free-text filter passed to the Froide search.
        page:     Page number for each per-status API call (default 1).
    """
    token = _token_from_ctx(ctx)
    target = statuses or _TRIAGE_STATUSES
    seen: dict[Any, dict[str, Any]] = {}
    async with FroideClient(token) as c:
        for status in target:
            payload = await c.get("/api/v1/request/", status=status, q=query, page=page)
            for req in _extract_results(payload):
                priority, rationale = _priority_for_request(req)
                key = req.get("id") or _request_identifier(req)
                existing = seen.get(key)
                if existing is None or priority > existing["priority"]:
                    seen[key] = {
                        "request_id": req.get("id"),
                        "label": _request_identifier(req),
                        "status": _request_status(req),
                        "priority": priority,
                        "why": rationale,
                        "next_step": _derive_next_step(req),
                    }
    items = sorted(seen.values(), key=lambda x: (-x["priority"], x["label"]))
    return {
        "statuses_queried": target,
        "count": len(items),
        "items": items,
    }


@mcp.tool()
async def find_requests_needing_action(
    ctx: Context,
    query: str | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Return only requests that most likely need a human decision soon.

    A focused subset of triage_my_requests: filters to requests whose status
    is in the urgent group or whose priority score is >= 80.

    Use this when you want a short, actionable list rather than the full queue.
    """
    triage = await triage_my_requests(ctx, query=query, page=page)
    urgent = [
        item
        for item in triage["items"]
        if item["status"] in _URGENT_STATUSES or item["priority"] >= 80
    ]
    return {
        "count": len(urgent),
        "items": urgent,
        "guidance": (
            "Review these requests in the Froide UI first "
            "— they likely need a human decision before they can progress."
        ),
    }


@mcp.tool()
async def summarize_request_thread(ctx: Context, request_id: int) -> dict[str, Any]:
    """Produce a short operator briefing for a single FOI request thread.

    Fetches the request and its attachments, then returns a compact summary
    with message count, attachment count, current priority and the suggested
    next manual step.

    Use this to orient yourself before deciding what to do with a request
    in the Froide UI.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        req = await c.get(f"/api/v1/request/{request_id}/")
        attachments_payload = await c.get("/api/v1/attachment/", belongs_to=request_id)
    messages = req.get("messages")
    priority, rationale = _priority_for_request(req)
    return {
        "request_id": req.get("id", request_id),
        "label": _request_identifier(req),
        "status": _request_status(req),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "attachment_count": len(_extract_results(attachments_payload)),
        "priority": priority,
        "why": rationale,
        "next_step": _derive_next_step(req),
    }
