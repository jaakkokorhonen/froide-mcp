"""Integration tests: MCP tools via mocked Froide API."""
from __future__ import annotations
import json
import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_request_stub(
    id_: int = 1,
    status: str = "awaiting_response",
    subject: str | None = None,
    messages: list | None = None,
) -> dict:
    return {
        "id": id_,
        "title": subject or f"Test request {id_}",
        "subject": subject or f"Test request {id_}",
        "status": status,
        "resolution": None,
        "description": "Please provide all records relating to this matter.",
        "public_body": {"name": "Test Authority"},
        "messages": messages or [
            {"id": 1, "subject": subject or f"Test request {id_}", "message": "Initial body", "is_response": False},
            {"id": 2, "subject": "Re: " + (subject or f"Test request {id_}"), "message": "We received your request.", "is_response": True},
        ],
    }


def _paginated(items: list) -> dict:
    """Wrap items in a Froide-style paginated envelope."""
    return {"count": len(items), "next": None, "previous": None, "results": items}


def _ctx_with_token(token: str):
    """Build a minimal FastMCP Context-like object for tool invocation."""
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.request_context.request.headers = {"x-froide-session": token}
    return ctx


# ---------------------------------------------------------------------------
# FOI Requests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_requests(session_token):
    from froide_mcp.tools import list_requests
    stub = {"objects": [_make_request_stub(1), _make_request_stub(2)], "meta": {"total_count": 2}}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_requests(_ctx_with_token(session_token))
    assert len(result["objects"]) == 2


@pytest.mark.asyncio
async def test_get_request(session_token):
    from froide_mcp.tools import get_request
    stub = _make_request_stub(99)
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/99/").mock(return_value=httpx.Response(200, json=stub))
        result = await get_request(_ctx_with_token(session_token), request_id=99)
    assert result["id"] == 99


@pytest.mark.asyncio
async def test_make_request(session_token):
    from froide_mcp.tools import make_request
    stub = {"id": 42, "subject": "Test FOI", "status": "awaiting_response"}
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.post("/api/v1/request/").mock(return_value=httpx.Response(201, json=stub))
        result = await make_request(
            _ctx_with_token(session_token),
            public_body_id=5,
            subject="Test FOI",
            body="Please provide...",
        )
    assert result["id"] == 42
    body = json.loads(route.calls[0].request.content)
    assert body["publicbody"] == 5
    assert body["public"] is True


@pytest.mark.asyncio
async def test_send_followup(session_token):
    from froide_mcp.tools import send_followup
    stub = {"id": 77, "message": "Hello"}
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.post("/api/v1/message/").mock(return_value=httpx.Response(201, json=stub))
        result = await send_followup(
            _ctx_with_token(session_token),
            request_id=1,
            message="Hello",
        )
    assert result["id"] == 77
    body = json.loads(route.calls[0].request.content)
    assert body["request"] == 1


@pytest.mark.asyncio
async def test_set_request_status(session_token):
    from froide_mcp.tools import set_request_status
    stub = {"id": 10, "status": "successful"}
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.patch("/api/v1/request/10/").mock(return_value=httpx.Response(200, json=stub))
        result = await set_request_status(
            _ctx_with_token(session_token),
            request_id=10,
            status="successful",
            resolution="Documents received in full.",
        )
    assert result["status"] == "successful"
    body = json.loads(route.calls[0].request.content)
    assert body["status"] == "successful"
    assert "resolution" in body


# ---------------------------------------------------------------------------
# Public bodies & jurisdictions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_public_bodies(session_token):
    from froide_mcp.tools import list_public_bodies
    stub = {"objects": [{"id": 5, "name": "Ministry of Truth"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_public_bodies(_ctx_with_token(session_token), q="Truth")
    assert result["objects"][0]["name"] == "Ministry of Truth"


@pytest.mark.asyncio
async def test_get_public_body(session_token):
    from froide_mcp.tools import get_public_body
    stub = {"id": 5, "name": "Ministry of Truth", "jurisdiction": {"id": 1}}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=stub))
        result = await get_public_body(_ctx_with_token(session_token), public_body_id=5)
    assert result["id"] == 5


@pytest.mark.asyncio
async def test_list_jurisdictions(session_token):
    from froide_mcp.tools import list_jurisdictions
    stub = {"objects": [{"id": 1, "name": "Federal"}, {"id": 2, "name": "Municipal"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/jurisdiction/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_jurisdictions(_ctx_with_token(session_token))
    assert len(result["objects"]) == 2


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_campaigns(session_token):
    from froide_mcp.tools import list_campaigns
    stub = {"objects": [{"id": 1, "name": "Open Budget 2026"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/campaign/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_campaigns(_ctx_with_token(session_token))
    assert result["objects"][0]["name"] == "Open Budget 2026"


@pytest.mark.asyncio
async def test_get_campaign(session_token):
    from froide_mcp.tools import get_campaign
    stub = {"id": 1, "name": "Open Budget 2026", "description": "Transparency campaign"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/campaign/1/").mock(return_value=httpx.Response(200, json=stub))
        result = await get_campaign(_ctx_with_token(session_token), campaign_id=1)
    assert result["id"] == 1


# ---------------------------------------------------------------------------
# Laws
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_laws(session_token):
    from froide_mcp.tools import list_laws
    stub = {"objects": [{"id": 1, "name": "Freedom of Information Act"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/law/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_laws(_ctx_with_token(session_token))
    assert result["objects"][0]["id"] == 1


@pytest.mark.asyncio
async def test_get_law(session_token):
    from froide_mcp.tools import get_law
    stub = {"id": 1, "name": "Freedom of Information Act", "jurisdiction": {"id": 1}}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/law/1/").mock(return_value=httpx.Response(200, json=stub))
        result = await get_law(_ctx_with_token(session_token), law_id=1)
    assert result["id"] == 1


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_attachments(session_token):
    from froide_mcp.tools import list_attachments
    stub = {"objects": [{"id": 3, "name": "response.pdf"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/attachment/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_attachments(_ctx_with_token(session_token), request_id=10)
    assert result["objects"][0]["name"] == "response.pdf"


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_my_profile(session_token):
    from froide_mcp.tools import get_my_profile
    stub = {"id": 1, "email": "user@example.com", "private": False}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/user/").mock(return_value=httpx.Response(200, json=stub))
        result = await get_my_profile(_ctx_with_token(session_token))
    assert result["email"] == "user@example.com"


# ---------------------------------------------------------------------------
# Auth guards (tool-level)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_rejects_missing_session_header():
    """Tool must raise PermissionError when X-Froide-Session header is absent."""
    from unittest.mock import MagicMock
    from froide_mcp.tools import list_requests
    ctx = MagicMock()
    ctx.request_context.request.headers = {}
    with pytest.raises(PermissionError, match="Missing X-Froide-Session"):
        await list_requests(ctx)


@pytest.mark.asyncio
async def test_tool_rejects_tampered_token():
    from unittest.mock import MagicMock
    from froide_mcp.tools import list_requests
    ctx = MagicMock()
    ctx.request_context.request.headers = {"x-froide-session": "bad.token.here"}
    with pytest.raises(ValueError):
        await list_requests(ctx)


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_triage_my_requests(session_token):
    """triage_my_requests returns prioritised items with required keys."""
    from froide_mcp.tools import triage_my_requests
    urgent = _make_request_stub(1, status="requires_user_action")
    waiting = _make_request_stub(2, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([urgent, waiting]))
        )
        result = await triage_my_requests(
            _ctx_with_token(session_token),
            statuses=["requires_user_action", "awaiting_response"],
        )
    assert result["count"] >= 1
    first = result["items"][0]
    assert "request_id" in first
    assert "priority" in first
    assert "next_step" in first
    # highest priority request should come first
    assert first["priority"] >= result["items"][-1]["priority"]


@pytest.mark.asyncio
async def test_find_requests_needing_action(session_token):
    """find_requests_needing_action returns only urgent items."""
    from froide_mcp.tools import find_requests_needing_action
    urgent = _make_request_stub(1, status="requires_user_action")
    low = _make_request_stub(2, status="successful")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([urgent, low]))
        )
        result = await find_requests_needing_action(_ctx_with_token(session_token))
    # must contain guidance key
    assert "guidance" in result
    # all returned items must be either in urgent statuses or priority >= 80
    for item in result["items"]:
        assert item["status"] in {
            "requires_user_action",
            "awaiting_user_confirmation",
            "has_fee",
            "awaiting_classification",
            "classification_needed",
            "publicbody_needed",
            "awaiting_publicbody_confirmation",
        } or item["priority"] >= 80


@pytest.mark.asyncio
async def test_summarize_request_thread(session_token):
    """summarize_request_thread returns compact briefing for a single request."""
    from froide_mcp.tools import summarize_request_thread
    req = _make_request_stub(5, status="awaiting_response")
    attachments = _paginated([{"id": 1, "name": "doc.pdf"}, {"id": 2, "name": "annex.pdf"}])
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/5/").mock(return_value=httpx.Response(200, json=req))
        mock.get("/api/v1/attachment/").mock(return_value=httpx.Response(200, json=attachments))
        result = await summarize_request_thread(_ctx_with_token(session_token), request_id=5)
    assert result["request_id"] == 5
    assert result["message_count"] == 2
    assert result["attachment_count"] == 2
    assert "next_step" in result
    assert "priority" in result


@pytest.mark.asyncio
async def test_draft_followup_for_request_awaiting_response(session_token):
    """draft_followup_for_request produces a draft with expected keys."""
    from froide_mcp.tools import draft_followup_for_request
    req = _make_request_stub(7, status="awaiting_response", subject="Budget records 2025")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/7/").mock(return_value=httpx.Response(200, json=req))
        result = await draft_followup_for_request(_ctx_with_token(session_token), request_id=7)
    assert result["request_id"] == 7
    assert result["status"] == "awaiting_response"
    assert "draft_message" in result
    assert "subject" in result
    assert "Budget records 2025" in result["subject"] or "Budget records 2025" in result["draft_message"]
    # draft should mention follow-up intent
    assert "following up" in result["draft_message"].lower() or "follow" in result["draft_message"].lower()


@pytest.mark.asyncio
async def test_draft_followup_for_request_refused(session_token):
    """Refused requests get a clarification-oriented draft."""
    from froide_mcp.tools import draft_followup_for_request
    req = _make_request_stub(8, status="refused", subject="Procurement records")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/8/").mock(return_value=httpx.Response(200, json=req))
        result = await draft_followup_for_request(_ctx_with_token(session_token), request_id=8)
    assert result["status"] == "refused"
    assert "clarif" in result["draft_message"].lower() or "basis" in result["draft_message"].lower()


@pytest.mark.asyncio
async def test_preflight_request_submission_ok(session_token):
    """preflight_request_submission passes a well-formed request."""
    from froide_mcp.tools import preflight_request_submission
    pb_stub = {"id": 3, "name": "Ministry of Finance"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/3/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await preflight_request_submission(
            _ctx_with_token(session_token),
            public_body_id=3,
            subject="Request for budget allocation documents",
            body="Please provide all budget allocation documents for fiscal year 2025. "
                 "This is to understand how public funds were distributed across ministries.",
        )
    assert result["ok"] is True
    assert result["issues"] == []
    assert result["request_preview"]["public_body_name"] == "Ministry of Finance"


@pytest.mark.asyncio
async def test_preflight_request_submission_missing_subject(session_token):
    """preflight_request_submission flags an empty subject."""
    from froide_mcp.tools import preflight_request_submission
    pb_stub = {"id": 3, "name": "Ministry of Finance"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/3/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await preflight_request_submission(
            _ctx_with_token(session_token),
            public_body_id=3,
            subject="",
            body="Some body text that is sufficiently long to avoid that warning. Adding more context here.",
        )
    assert result["ok"] is False
    assert any("subject" in issue.lower() for issue in result["issues"])


@pytest.mark.asyncio
async def test_get_request_analytics(session_token):
    """get_request_analytics returns status counts and priority bands."""
    from froide_mcp.tools import get_request_analytics
    items = [
        _make_request_stub(1, status="requires_user_action"),
        _make_request_stub(2, status="awaiting_response"),
        _make_request_stub(3, status="awaiting_response"),
        _make_request_stub(4, status="successful"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(items))
        )
        result = await get_request_analytics(
            _ctx_with_token(session_token),
            statuses=["requires_user_action", "awaiting_response", "successful"],
        )
    assert "status_counts" in result
    assert "priority_bands" in result
    bands = result["priority_bands"]
    assert set(bands.keys()) == {"critical", "high", "medium", "low"}
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_draft_request(session_token):
    """draft_request returns a usable subject and body without submitting."""
    from froide_mcp.tools import draft_request
    pb_stub = {"id": 4, "name": "City Planning Office"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/4/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await draft_request(
            _ctx_with_token(session_token),
            public_body_id=4,
            goal="understand urban zoning decisions",
            records_description="zoning decision records from 2023",
        )
    assert result["public_body_name"] == "City Planning Office"
    assert "zoning decision records" in result["suggested_subject"].lower() or \
           "zoning decision records" in result["draft_body"].lower()
    assert "next_step" in result
    assert "preflight" in result["next_step"].lower()


@pytest.mark.asyncio
async def test_followup_after_deadline(session_token):
    """followup_after_deadline pairs awaiting_response requests with follow-up drafts."""
    from froide_mcp.tools import followup_after_deadline
    req1 = _make_request_stub(10, status="awaiting_response", subject="Road maintenance contracts")
    req2 = _make_request_stub(11, status="awaiting_response", subject="Environmental permits 2024")
    with respx.mock(base_url="http://froide.test") as mock:
        # triage_my_requests calls list with status=awaiting_response
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([req1, req2]))
        )
        # draft_followup_for_request calls get_request for each
        mock.get("/api/v1/request/10/").mock(return_value=httpx.Response(200, json=req1))
        mock.get("/api/v1/request/11/").mock(return_value=httpx.Response(200, json=req2))
        result = await followup_after_deadline(_ctx_with_token(session_token))
    assert result["count"] == 2
    assert "guidance" in result
    for item in result["items"]:
        assert "draft_message" in item
        assert "draft_subject" in item
        assert item["status"] == "awaiting_response"
        # draft message should reference the request subject
        assert len(item["draft_message"]) > 50


@pytest.mark.asyncio
async def test_followup_after_deadline_empty(session_token):
    """followup_after_deadline returns empty list when no requests are awaiting response."""
    from froide_mcp.tools import followup_after_deadline
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([]))
        )
        result = await followup_after_deadline(_ctx_with_token(session_token))
    assert result["count"] == 0
    assert result["items"] == []
    assert "guidance" in result
