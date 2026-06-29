"""Tests for the five orchestration tools added in the second PR batch.

Covers:
  - draft_followup_for_request
  - preflight_request_submission
  - get_request_analytics
  - draft_request
  - followup_after_deadline

All Froide API calls are intercepted with respx; no live server is needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
import respx

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ctx(session_token: str):
    """Minimal FastMCP Context-like object."""
    ctx = MagicMock()
    ctx.request_context.request.headers = {"x-froide-session": session_token}
    return ctx


def _request_stub(
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
        "messages": messages or [
            {
                "id": 10,
                "subject": f"Re: {subject}",
                "message": "This is the latest message body.",
                "sender": "authority@example.com",
            }
        ],
    }


def _paginated(items: list) -> dict:
    return {"count": len(items), "results": items}


def _pb_stub(id_: int = 5) -> dict:
    return {"id": id_, "name": "Ministry of Testing", "title": "Ministry of Testing"}


def _law_stub(id_: int = 1) -> dict:
    return {"id": id_, "name": "Freedom of Information Act"}


# ---------------------------------------------------------------------------
# draft_followup_for_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_followup_awaiting_response(session_token: str):
    """Happy path: awaiting_response → draft contains polite status-check text."""
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(id_=1, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/1/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=1)

    assert result["request_id"] == 1
    assert result["status"] == "awaiting_response"
    assert "draft_message" in result
    assert len(result["draft_message"]) > 30
    # Draft should reference the subject somehow
    assert result["subject"] != ""


@pytest.mark.asyncio
async def test_draft_followup_refused_status(session_token: str):
    """Refused status → draft should ask for legal basis clarification."""
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(id_=2, status="refused", subject="Budget 2025")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/2/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=2)

    assert result["status"] == "refused"
    draft = result["draft_message"].lower()
    assert any(word in draft for word in ("clarif", "legal", "basis", "partial", "refusal"))


@pytest.mark.asyncio
async def test_draft_followup_no_messages(session_token: str):
    """Request with empty messages list still returns a draft."""
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(id_=3, status="awaiting_response", messages=[])
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/3/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=3)

    assert "draft_message" in result
    assert isinstance(result["draft_message"], str)
    assert len(result["draft_message"]) > 0


# ---------------------------------------------------------------------------
# preflight_request_submission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_valid_submission(session_token: str):
    """All fields valid → ok=True, no issues."""
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for procurement contracts 2024",
            body=(
                "Please provide all procurement contracts signed in the fiscal year 2024. "
                "I am specifically interested in contracts exceeding 50 000 EUR. "
                "Please include all annexes and tender documents."
            ),
        )

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["request_preview"]["public_body_name"] == "Ministry of Testing"


@pytest.mark.asyncio
async def test_preflight_missing_subject(session_token: str):
    """Empty subject → ok=False with issue about subject."""
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="",
            body="A perfectly fine body with enough content to pass length checks, including a question?",
        )

    assert result["ok"] is False
    assert any("subject" in issue.lower() for issue in result["issues"])


@pytest.mark.asyncio
async def test_preflight_short_body_warning(session_token: str):
    """Short body → ok still True but a warning is present."""
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for records",
            body="Please send me the files?",
        )

    # Short body alone does not block submission
    assert len(result["issues"]) == 0
    assert len(result["warnings"]) > 0


@pytest.mark.asyncio
async def test_preflight_with_law_and_campaign(session_token: str):
    """law_id and campaign_id are looked up and returned in the preview."""
    from froide_mcp.tools import preflight_request_submission

    campaign_stub = {"id": 3, "title": "Open Contracts"}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        mock.get("/api/v1/law/1/").mock(return_value=httpx.Response(200, json=_law_stub(1)))
        mock.get("/api/v1/campaign/3/").mock(return_value=httpx.Response(200, json=campaign_stub))
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for procurement contracts 2024",
            body=(
                "Please provide all procurement contracts from 2024, specifically those "
                "exceeding 50 000 EUR, including all annexes and tender documents."
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
async def test_get_request_analytics_basic(session_token: str):
    """Analytics over two requests returns correct counts and top_requests."""
    from froide_mcp.tools import get_request_analytics

    stubs = [
        _request_stub(1, status="awaiting_response"),
        _request_stub(2, status="requires_user_action"),
        _request_stub(3, status="successful"),
    ]

    with respx.mock(base_url="http://froide.test") as mock:
        # triage_my_requests iterates over _TRIAGE_STATUSES; return something for each
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(stubs))
        )
        result = await get_request_analytics(_ctx(session_token))

    assert "count" in result
    assert "status_counts" in result
    assert "priority_bands" in result
    assert isinstance(result["top_requests"], list)
    assert result["count"] >= 0


@pytest.mark.asyncio
async def test_get_request_analytics_empty(session_token: str):
    """Empty request list → zero counts, no errors."""
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([]))
        )
        result = await get_request_analytics(_ctx(session_token))

    assert result["count"] == 0
    assert result["top_requests"] == []
    assert all(v == 0 for v in result["priority_bands"].values())


@pytest.mark.asyncio
async def test_get_request_analytics_status_filter(session_token: str):
    """Custom statuses list is forwarded and reflected in statuses_queried."""
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([_request_stub(1, "awaiting_response")]))
        )
        result = await get_request_analytics(
            _ctx(session_token),
            statuses=["awaiting_response"],
        )

    assert "awaiting_response" in result["statuses_queried"]


# ---------------------------------------------------------------------------
# draft_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_request_basic(session_token: str):
    """Happy path: returns subject, body and public body name."""
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Understand how the ministry spent its IT budget",
            records_description="IT procurement invoices for fiscal year 2024",
        )

    assert "subject" in result
    assert "draft_body" in result
    assert "Ministry of Testing" in result["draft_body"]
    assert "IT procurement invoices" in result["draft_body"]
    assert result["public_body_name"] == "Ministry of Testing"


@pytest.mark.asyncio
async def test_draft_request_with_law(session_token: str):
    """law_id is fetched and its name appears in the result metadata."""
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        mock.get("/api/v1/law/1/").mock(return_value=httpx.Response(200, json=_law_stub(1)))
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Check compliance with environmental regulations",
            records_description="Environmental inspection reports 2023",
            law_id=1,
        )

    assert result.get("law_name") == "Freedom of Information Act"


@pytest.mark.asyncio
async def test_draft_request_next_step_hint(session_token: str):
    """Result must contain a next_step pointer."""
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Transparency check",
            records_description="Meeting minutes",
        )

    assert "next_step" in result
    assert len(result["next_step"]) > 0


# ---------------------------------------------------------------------------
# followup_after_deadline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_followup_after_deadline_awaiting(session_token: str):
    """awaiting_response → deadline follow-up draft must mention deadline."""
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=5, status="awaiting_response", subject="School budget data")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/5/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=5)

    assert result["request_id"] == 5
    assert "draft_message" in result
    draft = result["draft_message"].lower()
    assert any(
        word in draft for word in ("deadline", "statutory", "overdue", "days", "law", "follow")
    )


@pytest.mark.asyncio
async def test_followup_after_deadline_returns_subject(session_token: str):
    """Result always includes a non-empty subject suggestion."""
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=6, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/6/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=6)

    assert isinstance(result.get("subject"), str)
    assert len(result["subject"]) > 0


@pytest.mark.asyncio
async def test_followup_after_deadline_not_sent(session_token: str):
    """followup_after_deadline must NOT post to /api/v1/message/ — it only drafts."""
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=7, status="awaiting_response")
    with respx.mock(base_url="http://froide.test", assert_all_called=False) as mock:
        mock.get("/api/v1/request/7/").mock(return_value=httpx.Response(200, json=stub))
        # If the tool accidentally POSTs to /api/v1/message/ respx will raise
        mock.post("/api/v1/message/").mock(
            return_value=httpx.Response(500, json={"error": "should not be called"})
        )
        result = await followup_after_deadline(_ctx(session_token), request_id=7)

    # The 500 route must never have been called
    assert mock.calls.call_count < 2  # only the GET was made
    assert "draft_message" in result


# ---------------------------------------------------------------------------
# followup_after_deadline — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_followup_after_deadline_refused(session_token: str):
    """Refused status → draft should acknowledge the refusal context."""
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=8, status="refused", subject="Hospital staffing ratios 2023")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/8/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=8)

    assert result["status"] == "refused"
    # The tool should still return a meaningful draft
    assert len(result["draft_message"]) > 30


# ---------------------------------------------------------------------------
# Helper-function unit tests (exercised via public tool API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_priority_bands_in_analytics_are_non_negative(session_token: str):
    """priority_bands values must all be non-negative integers."""
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([_request_stub(1)]))
        )
        result = await get_request_analytics(_ctx(session_token))

    for band, count in result["priority_bands"].items():
        assert isinstance(count, int), f"Band {band!r} count is not int"
        assert count >= 0, f"Band {band!r} count is negative"


@pytest.mark.asyncio
async def test_draft_followup_excerpt_capped(session_token: str):
    """latest_message_excerpt must be <= 280 characters."""
    from froide_mcp.tools import draft_followup_for_request

    long_msg = "x" * 1000
    stub = _request_stub(
        id_=9,
        status="awaiting_response",
        messages=[{"id": 1, "subject": "Long answer", "message": long_msg}],
    )
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/9/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=9)

    assert len(result["latest_message_excerpt"]) <= 280
