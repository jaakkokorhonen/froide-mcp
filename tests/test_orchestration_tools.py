"""Tests for orchestration tools.

Covers all eight tools in the orchestration helpers section:
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
# helpers
# ---------------------------------------------------------------------------


def _ctx(session_token: str):
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


def _attachment_stub() -> dict:
    return {"results": [{"id": 1, "name": "response.pdf"}], "count": 1}


# ---------------------------------------------------------------------------
# triage_my_requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_returns_sorted_items(session_token: str):
    """triage_my_requests returns items sorted by descending priority."""
    from froide_mcp.tools import triage_my_requests

    stubs = [
        _request_stub(1, status="awaiting_response"),
        _request_stub(2, status="requires_user_action"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(stubs))
        )
        result = await triage_my_requests(_ctx(session_token))

    assert "items" in result
    assert "count" in result
    assert "statuses_queried" in result
    priorities = [item["priority"] for item in result["items"]]
    assert priorities == sorted(priorities, reverse=True)


@pytest.mark.asyncio
async def test_triage_deduplicates_requests(session_token: str):
    """Same request ID appearing in multiple status queries is deduplicated."""
    from froide_mcp.tools import triage_my_requests

    stub = _request_stub(42, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([stub]))
        )
        result = await triage_my_requests(_ctx(session_token))

    ids = [item["request_id"] for item in result["items"]]
    assert len(ids) == len(set(ids)), "Duplicate request IDs found in triage output"


@pytest.mark.asyncio
async def test_triage_custom_statuses(session_token: str):
    """Custom statuses list limits the queries made."""
    from froide_mcp.tools import triage_my_requests

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([]))
        )
        result = await triage_my_requests(
            _ctx(session_token), statuses=["awaiting_response"]
        )

    assert result["statuses_queried"] == ["awaiting_response"]


@pytest.mark.asyncio
async def test_triage_empty_queue(session_token: str):
    """Empty result set returns count=0 and empty items list."""
    from froide_mcp.tools import triage_my_requests

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([]))
        )
        result = await triage_my_requests(_ctx(session_token))

    assert result["count"] == 0
    assert result["items"] == []


# ---------------------------------------------------------------------------
# find_requests_needing_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_needing_action_filters_urgent(session_token: str):
    """Only urgent-status requests appear in the output."""
    from froide_mcp.tools import find_requests_needing_action

    stubs = [
        _request_stub(1, status="awaiting_response"),     # priority 70 — not urgent
        _request_stub(2, status="requires_user_action"),  # priority 100 — urgent
        _request_stub(3, status="successful"),             # priority 30 — not urgent
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(stubs))
        )
        result = await find_requests_needing_action(_ctx(session_token))

    statuses = {item["status"] for item in result["items"]}
    assert "requires_user_action" in statuses
    assert "awaiting_response" not in statuses
    assert "guidance" in result


@pytest.mark.asyncio
async def test_find_needing_action_empty(session_token: str):
    """No urgent requests returns count=0 with guidance."""
    from froide_mcp.tools import find_requests_needing_action

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([]))
        )
        result = await find_requests_needing_action(_ctx(session_token))

    assert result["count"] == 0
    assert isinstance(result["guidance"], str)


# ---------------------------------------------------------------------------
# summarize_request_thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_thread_basic(session_token: str):
    """summarize_request_thread returns all expected fields."""
    from froide_mcp.tools import summarize_request_thread

    stub = _request_stub(id_=10, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/10/").mock(return_value=httpx.Response(200, json=stub))
        mock.get("/api/v1/attachment/").mock(return_value=httpx.Response(200, json=_attachment_stub()))
        result = await summarize_request_thread(_ctx(session_token), request_id=10)

    assert result["request_id"] == 10
    assert result["status"] == "awaiting_response"
    assert isinstance(result["message_count"], int)
    assert isinstance(result["attachment_count"], int)
    assert "priority" in result
    assert "next_step" in result


@pytest.mark.asyncio
async def test_summarize_thread_counts_messages(session_token: str):
    """message_count reflects the actual messages list length."""
    from froide_mcp.tools import summarize_request_thread

    stub = _request_stub(
        id_=11,
        status="awaiting_response",
        messages=[
            {"id": 1, "subject": "Original request", "message": "Body 1"},
            {"id": 2, "subject": "Authority reply", "message": "Body 2"},
            {"id": 3, "subject": "Follow-up", "message": "Body 3"},
        ],
    )
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/11/").mock(return_value=httpx.Response(200, json=stub))
        mock.get("/api/v1/attachment/").mock(return_value=httpx.Response(200, json=_paginated([])))
        result = await summarize_request_thread(_ctx(session_token), request_id=11)

    assert result["message_count"] == 3


# ---------------------------------------------------------------------------
# draft_followup_for_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_followup_awaiting_response(session_token: str):
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(id_=1, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/1/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=1)

    assert result["request_id"] == 1
    assert result["status"] == "awaiting_response"
    assert len(result["draft_message"]) > 30
    assert result["subject"] != ""


@pytest.mark.asyncio
async def test_draft_followup_refused_status(session_token: str):
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
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(id_=3, status="awaiting_response", messages=[])
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/3/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=3)

    assert len(result["draft_message"]) > 0


@pytest.mark.asyncio
async def test_draft_followup_excerpt_capped(session_token: str):
    from froide_mcp.tools import draft_followup_for_request

    stub = _request_stub(
        id_=9,
        status="awaiting_response",
        messages=[{"id": 1, "subject": "Long answer", "message": "x" * 1000}],
    )
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/9/").mock(return_value=httpx.Response(200, json=stub))
        result = await draft_followup_for_request(_ctx(session_token), request_id=9)

    assert len(result["latest_message_excerpt"]) <= 280


# ---------------------------------------------------------------------------
# preflight_request_submission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_valid_submission(session_token: str):
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
    from froide_mcp.tools import preflight_request_submission

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await preflight_request_submission(
            _ctx(session_token),
            public_body_id=5,
            subject="Request for records",
            body="Please send me the files?",
        )

    assert len(result["issues"]) == 0
    assert len(result["warnings"]) > 0


@pytest.mark.asyncio
async def test_preflight_with_law_and_campaign(session_token: str):
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
    from froide_mcp.tools import get_request_analytics

    stubs = [
        _request_stub(1, status="awaiting_response"),
        _request_stub(2, status="requires_user_action"),
        _request_stub(3, status="successful"),
    ]
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated(stubs))
        )
        result = await get_request_analytics(_ctx(session_token))

    assert "count" in result
    assert "status_counts" in result
    assert "priority_bands" in result
    assert isinstance(result["top_requests"], list)


@pytest.mark.asyncio
async def test_get_request_analytics_empty(session_token: str):
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
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([_request_stub(1)]))
        )
        result = await get_request_analytics(
            _ctx(session_token), statuses=["awaiting_response"]
        )

    assert "awaiting_response" in result["statuses_queried"]


@pytest.mark.asyncio
async def test_priority_bands_non_negative(session_token: str):
    from froide_mcp.tools import get_request_analytics

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json=_paginated([_request_stub(1)]))
        )
        result = await get_request_analytics(_ctx(session_token))

    for band, count in result["priority_bands"].items():
        assert isinstance(count, int)
        assert count >= 0


# ---------------------------------------------------------------------------
# draft_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_request_basic(session_token: str):
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
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        mock.get("/api/v1/law/1/").mock(return_value=httpx.Response(200, json=_law_stub(1)))
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Check environmental compliance",
            records_description="Environmental inspection reports 2023",
            law_id=1,
        )

    assert result.get("law_name") == "Freedom of Information Act"


@pytest.mark.asyncio
async def test_draft_request_next_step(session_token: str):
    from froide_mcp.tools import draft_request

    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/5/").mock(return_value=httpx.Response(200, json=_pb_stub(5)))
        result = await draft_request(
            _ctx(session_token),
            public_body_id=5,
            goal="Transparency check",
            records_description="Meeting minutes",
        )

    assert len(result["next_step"]) > 0


# ---------------------------------------------------------------------------
# followup_after_deadline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_followup_after_deadline_awaiting(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=5, status="awaiting_response", subject="School budget data")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/5/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=5)

    assert result["request_id"] == 5
    draft = result["draft_message"].lower()
    assert any(
        word in draft for word in ("deadline", "statutory", "overdue", "days", "law", "exceeded")
    )


@pytest.mark.asyncio
async def test_followup_after_deadline_subject(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=6, status="awaiting_response")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/6/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=6)

    assert isinstance(result.get("subject"), str)
    assert len(result["subject"]) > 0


@pytest.mark.asyncio
async def test_followup_after_deadline_does_not_send(session_token: str):
    """followup_after_deadline must NOT POST to /api/v1/message/ — draft only."""
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=7, status="awaiting_response")
    post_called = False

    with respx.mock(base_url="http://froide.test", assert_all_called=False) as mock:
        mock.get("/api/v1/request/7/").mock(return_value=httpx.Response(200, json=stub))

        def _fail_if_called(request):
            nonlocal post_called
            post_called = True
            return httpx.Response(500, json={"error": "should not be called"})

        mock.post("/api/v1/message/").mock(side_effect=_fail_if_called)
        result = await followup_after_deadline(_ctx(session_token), request_id=7)

    assert not post_called, "followup_after_deadline made an unexpected POST request"
    assert "draft_message" in result


@pytest.mark.asyncio
async def test_followup_after_deadline_refused(session_token: str):
    from froide_mcp.tools import followup_after_deadline

    stub = _request_stub(id_=8, status="refused", subject="Hospital staffing ratios 2023")
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/8/").mock(return_value=httpx.Response(200, json=stub))
        result = await followup_after_deadline(_ctx(session_token), request_id=8)

    assert result["status"] == "refused"
    assert len(result["draft_message"]) > 30
    assert "note" in result
