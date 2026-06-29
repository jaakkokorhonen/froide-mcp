"""Integration tests: MCP tools via mocked Froide API."""
from __future__ import annotations
import json
import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_request_stub(id_: int = 1, status: str = "awaiting_response") -> dict:
    return {
        "id": id_,
        "subject": f"Test request {id_}",
        "title": f"Test request {id_}",
        "status": status,
        "messages": [],
        "public_body": {"name": "Test Authority"},
    }


def _paginated(items: list) -> dict:
    """Wrap a list of stubs in a Froide-style paginated envelope."""
    return {
        "count": len(items),
        "next": None,
        "previous": None,
        "results": items,
    }


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
# Orchestration: triage_my_requests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_triage_my_requests_returns_ranked_items(session_token):
    from froide_mcp.tools import triage_my_requests
    urgent = _make_request_stub(1, status="requires_user_action")
    waiting = _make_request_stub(2, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            side_effect=lambda req, **kw: httpx.Response(
                200,
                json=_paginated(
                    [urgent] if "requires_user_action" in str(req.url)
                    else [waiting] if "awaiting_response" in str(req.url)
                    else []
                ),
            )
        )
        result = await triage_my_requests(_ctx_with_token(session_token))
    assert result["count"] >= 1
    assert "items" in result
    priorities = [item["priority"] for item in result["items"]]
    assert priorities == sorted(priorities, reverse=True)


@pytest.mark.asyncio
async def test_triage_my_requests_deduplicates(session_token):
    """Same request returned by two status queries must appear only once."""
    from froide_mcp.tools import triage_my_requests
    stub = _make_request_stub(99, status="requires_user_action")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([stub]))
        )
        result = await triage_my_requests(
            _ctx_with_token(session_token),
            statuses=["requires_user_action", "awaiting_user_confirmation"],
        )
    ids = [item["request_id"] for item in result["items"]]
    assert ids.count(99) == 1


# ---------------------------------------------------------------------------
# Orchestration: find_requests_needing_action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_requests_needing_action_filters_low_priority(session_token):
    from froide_mcp.tools import find_requests_needing_action
    urgent = _make_request_stub(1, status="requires_user_action")
    resolved = _make_request_stub(2, status="resolved")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            side_effect=lambda req, **kw: httpx.Response(
                200,
                json=_paginated(
                    [urgent] if "requires_user_action" in str(req.url) else [resolved]
                ),
            )
        )
        result = await find_requests_needing_action(_ctx_with_token(session_token))
    for item in result["items"]:
        assert item["priority"] >= 80 or item["status"] in {
            "requires_user_action", "awaiting_user_confirmation", "has_fee",
            "awaiting_classification", "classification_needed",
            "publicbody_needed", "awaiting_publicbody_confirmation",
        }


# ---------------------------------------------------------------------------
# Orchestration: summarize_request_thread
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_request_thread(session_token):
    from froide_mcp.tools import summarize_request_thread
    req_stub = _make_request_stub(5, status="awaiting_response")
    req_stub["messages"] = [
        {"id": 1, "subject": "Initial request", "message": "Please send records."},
        {"id": 2, "subject": "Re: Initial request", "message": "We received your request."},
    ]
    att_stub = _paginated([{"id": 10, "name": "letter.pdf"}])
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/5/").mock(return_value=httpx.Response(200, json=req_stub))
        mock.get("/api/v1/attachment/").mock(return_value=httpx.Response(200, json=att_stub))
        result = await summarize_request_thread(_ctx_with_token(session_token), request_id=5)
    assert result["request_id"] == 5
    assert result["message_count"] == 2
    assert result["attachment_count"] == 1
    assert "next_step" in result
    assert "priority" in result


# ---------------------------------------------------------------------------
# Orchestration: draft_followup_for_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_followup_for_request_awaiting(session_token):
    from froide_mcp.tools import draft_followup_for_request
    stub = _make_request_stub(7, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/7/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx_with_token(session_token), request_id=7)
    assert result["request_id"] == 7
    assert "draft_message" in result
    assert len(result["draft_message"]) > 20
    assert "subject" in result


@pytest.mark.asyncio
async def test_draft_followup_for_request_refused(session_token):
    from froide_mcp.tools import draft_followup_for_request
    stub = _make_request_stub(8, status="refused")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/8/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx_with_token(session_token), request_id=8)
    assert "clarif" in result["draft_message"].lower() or "legal" in result["draft_message"].lower()


# ---------------------------------------------------------------------------
# Orchestration: preflight_request_submission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preflight_passes_valid_input(session_token):
    from froide_mcp.tools import preflight_request_submission
    pb_stub = {"id": 5, "name": "Ministry of Truth"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await preflight_request_submission(
            _ctx_with_token(session_token),
            public_body_id=5,
            subject="Request for environmental impact assessments",
            body="Please provide all environmental impact assessments published since 2020. "
                 "I need these records to understand the authority's decision-making process.",
        )
    assert result["ok"] is True
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_preflight_blocks_empty_subject(session_token):
    from froide_mcp.tools import preflight_request_submission
    pb_stub = {"id": 5, "name": "Ministry of Truth"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await preflight_request_submission(
            _ctx_with_token(session_token),
            public_body_id=5,
            subject="",
            body="Some body text that is long enough to pass validation checks here.",
        )
    assert result["ok"] is False
    assert any("Subject" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# Orchestration: get_request_analytics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_request_analytics_structure(session_token):
    from froide_mcp.tools import get_request_analytics
    stubs = [
        _make_request_stub(1, status="requires_user_action"),
        _make_request_stub(2, status="awaiting_response"),
        _make_request_stub(3, status="successful"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(stubs))
        )
        result = await get_request_analytics(
            _ctx_with_token(session_token),
            statuses=["requires_user_action", "awaiting_response", "successful"],
        )
    assert "count" in result
    assert "status_counts" in result
    assert "priority_bands" in result
    assert set(result["priority_bands"].keys()) == {"critical", "high", "medium", "low"}


# ---------------------------------------------------------------------------
# Orchestration: draft_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_request_produces_template(session_token):
    from froide_mcp.tools import draft_request
    pb_stub = {"id": 3, "name": "Environmental Agency"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/3/").mock(return_value=httpx.Response(200, json=pb_stub))
        result = await draft_request(
            _ctx_with_token(session_token),
            public_body_id=3,
            goal="Understand air quality monitoring practices",
            records_description="air quality measurement reports from 2022 to 2024",
        )
    assert result["public_body_name"] == "Environmental Agency"
    assert "air quality" in result["draft_body"].lower()
    assert "subject" in result
    assert "next_step" in result


# ---------------------------------------------------------------------------
# Orchestration: followup_after_deadline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_followup_after_deadline_awaiting(session_token):
    from froide_mcp.tools import followup_after_deadline
    stub = _make_request_stub(20, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/20/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx_with_token(session_token), request_id=20)
    assert result["request_id"] == 20
    assert "deadline" in result["draft_message"].lower()
    assert result["subject"].startswith("Deadline follow-up:")
    assert "note" in result


@pytest.mark.asyncio
async def test_followup_after_deadline_refused(session_token):
    from froide_mcp.tools import followup_after_deadline
    stub = _make_request_stub(21, status="refused")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/21/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx_with_token(session_token), request_id=21)
    assert "refusal" in result["draft_message"].lower() or "refused" in result["draft_message"].lower() or "remaining" in result["draft_message"].lower()
