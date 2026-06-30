"""MCP tool definitions for the Froide FOI platform.

All tools require a valid Google-SSO session (enforced by RequireSessionMiddleware
in server.py).  Individual tools call _token_from_ctx() to extract the Froide
bearer token from the already-validated session.

# Pagination note
# ─────────────────────────────────────────────────────────────────────────────
# List tools pass the `page` parameter straight through to the Froide REST API.
# Callers do NOT need to implement their own pagination loop: the MCP server
# exposes each page as a separate tool call result, and the agent/operator can
# request the next page by incrementing `page`.  Froide's standard envelope
# ({count, next, previous, results}) is returned as-is so the caller always
# knows how many items exist in total and whether a next page exists.
"""
from __future__ import annotations

from collections import Counter
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


def _request_messages(req: dict[str, Any]) -> list[dict[str, Any]]:
    messages = req.get("messages")
    if isinstance(messages, list):
        return [m for m in messages if isinstance(m, dict)]
    return []


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
        marker in haystack
        for marker in ("fee", "clarif", "user action", "requires action", "postal", "confirmation")
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


def _latest_message_text(req: dict[str, Any]) -> str:
    messages = _request_messages(req)
    if not messages:
        return ""
    latest = messages[-1]
    return str(
        latest.get("message")
        or latest.get("body")
        or latest.get("content")
        or latest.get("text")
        or ""
    ).strip()


def _latest_message_subject(req: dict[str, Any]) -> str:
    messages = _request_messages(req)
    if not messages:
        return str(req.get("subject") or req.get("title") or "")
    latest = messages[-1]
    return str(latest.get("subject") or req.get("subject") or req.get("title") or "").strip()


def _followup_draft_context(req: dict[str, Any]) -> dict[str, Any]:
    """Return a language-neutral context dict for drafting a follow-up message.

    Intentionally does NOT produce rendered prose in any specific language.
    The caller (LLM or operator) is responsible for composing the final message
    from this context in whichever language is appropriate for the request.

    Keys
    ----
    situation   : machine-readable token describing the current state
    subject     : subject line of the latest message (or request title)
    request_id  : Froide request ID
    label       : human-readable request identifier
    public_body : name of the target authority, if available
    latest_message_excerpt : first 280 chars of the latest thread message
    """
    return {
        "situation": _request_status(req),
        "subject": _latest_message_subject(req) or _request_identifier(req),
        "request_id": req.get("id"),
        "label": _request_identifier(req),
        "public_body": (
            req.get("public_body", {}).get("name")
            if isinstance(req.get("public_body"), dict)
            else None
        ),
        "latest_message_excerpt": _latest_message_text(req)[:280],
    }


def _deadline_followup_draft_context(req: dict[str, Any]) -> dict[str, Any]:
    """Return a language-neutral context dict for a statutory-deadline follow-up.

    Extends _followup_draft_context with a `deadline_exceeded` flag so the
    caller knows to frame the message around the missed statutory deadline.
    """
    ctx = _followup_draft_context(req)
    ctx["deadline_exceeded"] = True
    return ctx


def _summarize_request(req: dict[str, Any]) -> dict[str, Any]:
    priority, rationale = _priority_for_request(req)
    return {
        "request_id": req.get("id"),
        "label": _request_identifier(req),
        "status": _request_status(req),
        "priority": priority,
        "why": rationale,
        "next_step": _derive_next_step(req),
    }


# ── FOI Requests ──────────────────────────────────────────────────────────


@mcp.tool()
async def list_requests(
    ctx: Context,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """List FOI requests, optionally filtered by status and/or a free-text search query.

    This is the single entry point for both listing and searching requests.
    Pass `q` for full-text search, `status` to filter by workflow state, or
    combine both.  The raw Froide envelope ({count, next, previous, results})
    is returned so the caller always knows the total count and whether a next
    page exists — increment `page` to fetch it.

    status options: awaiting_user_confirmation, publicbody_needed,
    awaiting_publicbody_confirmation, awaiting_response,
    awaiting_classification, classification_needed, has_fee, refused,
    partially_successful, successful, not_held, gone_postal,
    user_withdrew_costs, user_withdrew, resolved, requires_user_action.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get("/api/v1/request/", status=status, q=q, page=page)


# search_requests was removed: it was an exact duplicate of list_requests(q=...).
# Use list_requests(q="your search terms") instead.


@mcp.tool()
async def get_request(ctx: Context, request_id: int) -> dict[str, Any]:
    """Get a single FOI request with all its messages and metadata."""
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        return await c.get(f"/api/v1/request/{request_id}/")


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
    if law_id is not None:
        payload["law"] = law_id
    if campaign_id is not None:
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


@mcp.tool()
async def draft_followup_for_request(ctx: Context, request_id: int) -> dict[str, Any]:
    """Draft a follow-up message based on a request's current status and latest thread state.

    This tool does not send anything.  It returns a structured `draft_context`
    dict with all the information needed to compose the final message text.
    The caller (LLM or operator) is responsible for rendering the prose in the
    language appropriate for the request — no English template is imposed.

    Use the returned `draft_context` to write the message, then pass the
    finished text to send_followup.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        req = await c.get(f"/api/v1/request/{request_id}/")
    return {
        "request_id": req.get("id", request_id),
        "label": _request_identifier(req),
        "status": _request_status(req),
        "suggested_subject": (
            _latest_message_subject(req) or f"Follow-up on {_request_identifier(req)}"
        ),
        "draft_context": _followup_draft_context(req),
        "why": _derive_next_step(req),
        "instructions": (
            "Compose the follow-up message in the language used in the request thread. "
            "Use draft_context.situation to pick the appropriate framing "
            "(e.g. status check, refusal challenge, public-body confirmation). "
            "Then call send_followup with the finished text."
        ),
    }


@mcp.tool()
async def preflight_request_submission(
    ctx: Context,
    public_body_id: int,
    subject: str,
    body: str,
    law_id: int | None = None,
    campaign_id: int | None = None,
    public: bool = True,
) -> dict[str, Any]:
    """Validate a prospective request before calling make_request.

    This performs local MCP-side checks only. It does not create a request.
    Use it to surface missing fields and basic risks before submission.
    """
    token = _token_from_ctx(ctx)
    issues: list[str] = []
    warnings: list[str] = []

    clean_subject = subject.strip()
    clean_body = body.strip()

    if not clean_subject:
        issues.append("Subject is required.")
    elif len(clean_subject) < 8:
        warnings.append("Subject is very short; consider making it more specific.")

    if not clean_body:
        issues.append("Body is required.")
    elif len(clean_body) < 120:
        warnings.append("Body is short; add more context so the authority can identify the records.")

    if "?" not in clean_body and "please" not in clean_body.lower():
        warnings.append("The body may not contain a clearly phrased request or question.")

    async with FroideClient(token) as c:
        public_body = await c.get(f"/api/v1/publicbody/{public_body_id}/")
        law = await c.get(f"/api/v1/law/{law_id}/") if law_id is not None else None
        campaign = await c.get(f"/api/v1/campaign/{campaign_id}/") if campaign_id is not None else None

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "request_preview": {
            "public_body_id": public_body_id,
            "public_body_name": public_body.get("name") or public_body.get("title"),
            "subject": clean_subject,
            "body_preview": clean_body[:500],
            "law_id": law_id,
            "law_name": law.get("name") if isinstance(law, dict) else None,
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("title") if isinstance(campaign, dict) else None,
            "public": public,
        },
        "next_step": "Call make_request if there are no blocking issues.",
    }


@mcp.tool()
async def get_request_analytics(
    ctx: Context,
    statuses: list[str] | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Compute simple request analytics from visible requests using existing API endpoints.

    Returns counts by status, priority bands and the top actionable requests.
    No backend aggregation endpoints are required.
    """
    triage = await triage_my_requests(ctx, statuses=statuses, page=page)
    items = triage["items"]
    status_counts = Counter(item["status"] for item in items)
    priority_bands = {
        "critical": sum(1 for item in items if item["priority"] >= 90),
        "high": sum(1 for item in items if 80 <= item["priority"] < 90),
        "medium": sum(1 for item in items if 50 <= item["priority"] < 80),
        "low": sum(1 for item in items if item["priority"] < 50),
    }
    return {
        "count": len(items),
        "statuses_queried": triage["statuses_queried"],
        "status_counts": dict(sorted(status_counts.items())),
        "priority_bands": priority_bands,
        "top_requests": items[:10],
    }


@mcp.tool()
async def draft_request(
    ctx: Context,
    public_body_id: int,
    goal: str,
    records_description: str,
    law_id: int | None = None,
    public: bool = True,
) -> dict[str, Any]:
    """Prepare language-neutral drafting context for a new FOI request.

    This tool does not submit anything and does not return hard-coded prose in
    any specific language. Instead, it returns a structured `draft_context`
    object that the caller renders into the final request text in the language
    appropriate for the target authority and request thread.

    Review or render the final request text first, then pass it into
    preflight_request_submission or make_request.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        public_body_payload = await c.get(f"/api/v1/publicbody/{public_body_id}/")
        law_payload = await c.get(f"/api/v1/law/{law_id}/") if law_id is not None else None

    public_body_name = str(
        public_body_payload.get("name") or public_body_payload.get("title") or public_body_id
    )
    clean_goal = goal.strip()
    clean_records = records_description.strip()
    suggested_subject = f"Request for access to {clean_records}"
    draft_context = {
        "request_goal": clean_goal,
        "records_description": clean_records,
        "public_body_id": public_body_id,
        "public_body_name": public_body_name,
        "law_id": law_id,
        "law_name": law_payload.get("name") if isinstance(law_payload, dict) else None,
        "public": public,
        "disclosure_preferences": {
            "allow_partial_disclosure": True,
            "ask_for_redaction_explanations": True,
            "invite_clarification_if_needed": True,
        },
        "drafting_notes": [
            "Write the request in the language appropriate for the authority and request thread.",
            "State the access goal clearly and concretely.",
            "Describe the requested records precisely enough for the authority to identify them.",
            "Ask for partial disclosure if full disclosure is not possible.",
            "Ask the authority to explain any redactions, refusals, or legal limitations.",
            "Invite the authority to request clarification if the scope needs narrowing.",
        ],
    }
    return {
        "public_body_id": public_body_id,
        "public_body_name": public_body_name,
        "law_id": law_id,
        "law_name": law_payload.get("name") if isinstance(law_payload, dict) else None,
        "public": public,
        "suggested_subject": suggested_subject,
        "draft_context": draft_context,
        "instructions": (
            "Compose the request in the language appropriate for the target authority. "
            "Use draft_context to write the final subject and body, then call "
            "preflight_request_submission or make_request with the reviewed text."
        ),
        "next_step": (
            "Render or review the final request text, then call "
            "preflight_request_submission or make_request directly."
        ),
    }


@mcp.tool()
async def followup_after_deadline(ctx: Context, request_id: int) -> dict[str, Any]:
    """Draft a statutory-deadline follow-up message for a FOI request.

    Use this when the legal response deadline has passed and the authority has
    not yet replied (status 'awaiting_response') or when a refusal needs to be
    challenged after the deadline period.

    This tool does NOT send anything.  It returns a structured `draft_context`
    dict with all the information needed to compose the final message text.
    The caller (LLM or operator) is responsible for rendering the prose in the
    language appropriate for the request — no English template is imposed.

    Use the returned `draft_context` (note: deadline_exceeded=True) to write
    the message, then pass the finished text to send_followup.

    Args:
        request_id: ID of the FOI request that has exceeded its deadline.
    """
    token = _token_from_ctx(ctx)
    async with FroideClient(token) as c:
        req = await c.get(f"/api/v1/request/{request_id}/")
    subject_base = _latest_message_subject(req) or _request_identifier(req)
    return {
        "request_id": req.get("id", request_id),
        "label": _request_identifier(req),
        "status": _request_status(req),
        "suggested_subject": f"Deadline follow-up: {subject_base}",
        "draft_context": _deadline_followup_draft_context(req),
        "why": _derive_next_step(req),
        "instructions": (
            "Compose the follow-up message in the language used in the request thread. "
            "draft_context.deadline_exceeded is True — frame the message around the "
            "missed statutory deadline. Then call send_followup with the finished text."
        ),
        "note": (
            "This draft is for statutory-deadline follow-up only. "
            "Review before sending via send_followup."
        ),
    }
