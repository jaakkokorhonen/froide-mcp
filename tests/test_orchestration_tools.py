"""Tests for the orchestration tools layer.

Covers all eight orchestration tools:
  - triage_my_requests
  - find_requests_needing_action
  - summarize_request_thread
  - draft_followup_for_request
  - preflight_request_submission
  - get_request_analytics
  - draft_request
  - followup_after_deadline

All Froide API calls are intercepted with respx; no live server is needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _ctx(session_token: str):
    ctx = MagicMock()
    ctx.request_context.request.headers = {"x-froide-session": session_token}
    return ctx


def _req(
    id_: int = 1,
    status: str = "awaiting_response",
    subject: str = "Test FOI request",
    messages: list | None = None,
) -> dict:
    return {
        "id": id_,
        "subject": subject,
        "title": subject,
        "status": status,
        "resolution": None,
        "description": "Test description",
        "messages": messages
        or [
            {
                "id": 10,
                "subject": f"Re: {subject}",
                "message": "Latest message body.",
            }
        ],
    }


def _page(items: list) -> dict:
    return {"count": len(items), "results": items}


def _pb(id_: int = 5) -> dict:
    return {"id": id_, "name": "Ministry of Testing", "title": "Ministry of Testing"}


def _law(id_: int = 1) -> dict:
    return {"id": id_, "name": "Freedom of Information Act"}


# ---------------------------------------------------------------------------
# triage_my_requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_returns_sorted_items(session_token: str):
    from froide_mcp.tools import triage_my_requests

    stubs = [
        _req(1, "awaiting_response"),
        _req(2, "requires_user_action"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page(stubs))
        )
        result = await triage_my_requests(_ctx(session_token))

    assert "items" in result
    assert "count" in result
    assert "statuses_queried" in result
    priorities = [i["priority"] for i in result["items"]]
    assert priorities == sorted(priorities, reverse=True)


@pytest.mark.asyncio
async def test_triage_deduplicates_by_id(session_token: str):
    """Same request appearing under two statuses must appear only once."""
    from froide_mcp.tools import triage_my_requests

    stub = _req(42, "requires_user_action")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([stub]))
        )
        result = await triage_my_requests(_ctx(session_token))

    ids = [i["request_id"] for i in result["items"]]
    assert ids.count(42) == 1


@pytest.mark.asyncio
async def test_triage_custom_statuses(session_token: str):
    from froide_mcp.tools import triage_my_requests

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([_req(1, "successful")]))
        )
        result = await triage_my_requests(
            _ctx(session_token), statuses=["successful"]
        )

    assert result["statuses_queried"] == ["successful"]


@pytest.mark.asyncio
async def test_triage_empty_results(session_token: str):
    from froide_mcp.tools import triage_my_requests

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([]))
        )
        result = await triage_my_requests(_ctx(session_token))

    assert result["count"] == 0
    assert result["items"] == []


# ---------------------------------------------------------------------------
# find_requests_needing_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_needing_action_filters_urgent(session_token: str):
    from froide_mcp.tools import find_requests_needing_action

    stubs = [
        _req(1, "requires_user_action"),
        _req(2, "awaiting_response"),  # priority 70 — below threshold
        _req(3, "has_fee"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page(stubs))
        )
        result = await find_requests_needing_action(_ctx(session_token))

    urgent_ids = {i["request_id"] for i in result["items"]}
    # id 1 (requires_user_action, p=100) and id 3 (has_fee, p=100) must appear
    assert 1 in urgent_ids
    assert 3 in urgent_ids
    # id 2 (awaiting_response, p=70) must NOT appear
    assert 2 not in urgent_ids


@pytest.mark.asyncio
async def test_find_needing_action_guidance_key(session_token: str):
    from froide_mcp.tools import find_requests_needing_action

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([]))
        )
        result = await find_requests_needing_action(_ctx(session_token))

    assert "guidance" in result
    assert isinstance(result["guidance"], str)


# ---------------------------------------------------------------------------
# summarize_request_thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_counts_messages_and_attachments(session_token: str):
    from froide_mcp.tools import summarize_request_thread

    req_stub = _req(10, "awaiting_response", messages=[{"id": 1}, {"id": 2}, {"id": 3}])
    att_stub = {"count": 2, "results": [{"id": 101}, {"id": 102}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/10/").mock(
            return_value=httpx.Response(200, json=req_stub)
        )
        mock.get("/api/v1/attachment/").mock(
            return_value=httpx.Response(200, json=att_stub)
        )
        result = await summarize_request_thread(_ctx(session_token), request_id=10)

    assert result["message_count"] == 3
    assert result["attachment_count"] == 2
    assert result["request_id"] == 10
    assert "priority" in result
    assert "next_step" in result


@pytest.mark.asyncio
async def test_summarize_no_messages(session_token: str):
    from froide_mcp.tools import summarize_request_thread

    req_stub = _req(11, "successful", messages=[])
    att_stub = {"count": 0, "results": []}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/11/").mock(
            return_value=httpx.Response(200, json=req_stub)
        )
        mock.get("/api/v1/attachment/").mock(
            return_value=httpx.Response(200, json=att_stub)
        )
        result = await summarize_request_thread(_ctx(session_token), request_id=11)

    assert result["message_count"] == 0
    assert result["attachment_count"] == 0


# ---------------------------------------------------------------------------
# draft_followup_for_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_followup_awaiting_response(session_token: str):
    from froide_mcp.tools import draft_followup_for_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/1/").mock(
            return_value=httpx.Response(200, json=_req(1, "awaiting_response"))
        )
        result = await draft_followup_for_request(_ctx(session_token), request_id=1)

    assert result["status"] == "awaiting_response"
    assert len(result["draft_message"]) > 30
    assert result["subject"] != ""


@pytest.mark.asyncio
async def test_draft_followup_refused(session_token: str):
    from froide_mcp.tools import draft_followup_for_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/2/").mock(
            return_value=httpx.Response(200, json=_req(2, "refused", "Budget 2025"))
        )
        result = await draft_followup_for_request(_ctx(session_token), request_id=2)

    draft = result["draft_message"].lower()
    assert any(w in draft for w in ("clarif", "legal", "basis", "partial", "refusal"))


@pytest.mark.asyncio
async def test_draft_followup_excerpt_capped(session_token: str):
    from froide_mcp.tools import draft_followup_for_request

    stub = _req(9, messages=[{"id": 1, "subject": "S", "message": "x" * 1000}])
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/9/").mock(
            return_value=httpx.Response(200, json=stub)
        )
        result = await draft_followup_for_request(_ctx(session_token), request_id=9)

    assert len(result["latest_message_excerpt"]) <= 280


# ---------------------------------------------------------------------------
# preflight_request_submission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_valid(session_token: str):
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for procurement contracts 2024",
            body=(
                "Please provide all procurement contracts signed in fiscal year 2024. "
                "I am specifically interested in contracts exceeding 50 000 EUR, "
                "including all annexes and tender documents."
            ),
        )

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["request_preview"]["public_body_name"] == "Ministry of Testing"


@pytest.mark.asyncio
async def test_preflight_empty_subject_blocks(session_token: str):
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="",
            body="A body with enough content to pass length checks, including a question?",
        )

    assert result["ok"] is False
    assert any("subject" in i.lower() for i in result["issues"])


@pytest.mark.asyncio
async def test_preflight_short_body_warns(session_token: str):
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for records",
            body="Please send me the files?",
        )

    assert result["issues"] == []
    assert len(result["warnings"]) > 0


@pytest.mark.asyncio
async def test_preflight_law_and_campaign_names(session_token: str):
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        mock.get("/api/v1/law/1/").mock(
            return_value=httpx.Response(200, json=_law(1))
        )
        mock.get("/api/v1/campaign/3/").mock(
            return_value=httpx.Response(200, json={"id": 3, "title": "Open Contracts"})
        )
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for procurement contracts 2024",
            body=(
                "Please provide all procurement contracts from 2024 exceeding 50 000 EUR, "
                "including annexes and tender documents."
            ),
            law_id=1,
            campaign_id=3,
        )

    assert result["request_preview"]["law_name"] == "Freedom of Information Act"
    assert result["request_preview"]["campaign_name"] == "Open Contracts"


# ---------------------------------------------------------------------------
# get_request_analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_basic_counts(session_token: str):
    from froide_mcp.tools import get_request_analytics

    stubs = [
        _req(1, "awaiting_response"),
        _req(2, "requires_user_action"),
        _req(3, "successful"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page(stubs))
        )
        result = await get_request_analytics(_ctx(session_token))

    assert "count" in result
    assert "status_counts" in result
    assert "priority_bands" in result
    assert isinstance(result["top_requests"], list)


@pytest.mark.asyncio
async def test_analytics_empty(session_token: str):
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([]))
        )
        result = await get_request_analytics(_ctx(session_token))

    assert result["count"] == 0
    assert result["top_requests"] == []
    assert all(v == 0 for v in result["priority_bands"].values())


@pytest.mark.asyncio
async def test_analytics_priority_bands_non_negative(session_token: str):
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_page([_req(1)]))
        )
        result = await get_request_analytics(_ctx(session_token))

    for band, count in result["priority_bands"].items():
        assert isinstance(count, int), f"{band} not int"
        assert count >= 0, f"{band} is negative"


# ---------------------------------------------------------------------------
# draft_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_request_basic(session_token: str):
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Understand IT budget spending",
            records_description="IT procurement invoices FY2024",
        )

    assert "draft_body" in result
    assert "Ministry of Testing" in result["draft_body"]
    assert "IT procurement invoices FY2024" in result["draft_body"]
    assert result["public_body_name"] == "Ministry of Testing"
    assert "subject" in result


@pytest.mark.asyncio
async def test_draft_request_law_name(session_token: str):
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        mock.get("/api/v1/law/1/").mock(
            return_value=httpx.Response(200, json=_law(1))
        )
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Compliance check",
            records_description="Inspection reports 2023",
            law_id=1,
        )

    assert result["law_name"] == "Freedom of Information Act"


@pytest.mark.asyncio
async def test_draft_request_next_step(session_token: str):
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(
            return_value=httpx.Response(200, json=_pb(5))
        )
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Transparency check",
            records_description="Meeting minutes",
        )

    assert "next_step" in result
    assert len(result["next_step"]) > 0


# ---------------------------------------------------------------------------
# followup_after_deadline  (single-request variant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_followup_deadline_contains_deadline_language(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/5/").mock(
            return_value=httpx.Response(200, json=_req(5, "awaiting_response", "School budget"))
        )
        result = await followup_after_deadline(_ctx(session_token), request_id=5)

    assert result["request_id"] == 5
    draft = result["draft_message"].lower()
    assert any(w in draft for w in ("deadline", "statutory", "overdue", "days", "follow", "law"))


@pytest.mark.asyncio
async def test_followup_deadline_subject_not_empty(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/6/").mock(
            return_value=httpx.Response(200, json=_req(6, "awaiting_response"))
        )
        result = await followup_after_deadline(_ctx(session_token), request_id=6)

    assert isinstance(result.get("subject"), str)
    assert len(result["subject"]) > 0


@pytest.mark.asyncio
async def test_followup_deadline_does_not_post(session_token: str):
    """followup_after_deadline must never POST to /api/v1/message/."""
    from froide_mcp.tools import followup_after_deadline

    with respx.mock(base_url="http://froide.test", assert_all_called=False) as mock:
        mock.get("/api/v1/request/7/").mock(
            return_value=httpx.Response(200, json=_req(7, "awaiting_response"))
        )
        mock.post("/api/v1/message/").mock(
            return_value=httpx.Response(500, json={"error": "must not be called"})
        )
        result = await followup_after_deadline(_ctx(session_token), request_id=7)

    post_calls = [
        c for c in mock.calls if c.request.method == "POST"
    ]
    assert post_calls == []
    assert "draft_message" in result


@pytest.mark.asyncio
async def test_followup_deadline_refused_status(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/8/").mock(
            return_value=httpx.Response(200, json=_req(8, "refused", "Hospital staffing"))
        )
        result = await followup_after_deadline(_ctx(session_token), request_id=8)

    assert result["status"] == "refused"
    assert len(result["draft_message"]) > 30
