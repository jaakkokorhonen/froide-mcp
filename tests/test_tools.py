"""Integration tests: MCP tools via mocked Froide API."""
from __future__ import annotations
import json
import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_request_stub(id_: int = 1) -> dict:
    return {
        "id": id_,
        "title": f"Test request {id_}",
        "status": "awaiting_response",
        "public_body": {"name": "Test Authority"},
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
