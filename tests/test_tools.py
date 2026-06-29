"""Integration tests: MCP tools via mocked Froide API."""
from __future__ import annotations
import pytest
import respx
import httpx

# --- helpers ----------------------------------------------------------------

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


# --- tests ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_requests(session_token, froide_token):
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
    import json
    body = json.loads(route.calls[0].request.content)
    assert body["request"] == 1


@pytest.mark.asyncio
async def test_list_public_bodies(session_token):
    from froide_mcp.tools import list_public_bodies
    stub = {"objects": [{"id": 5, "name": "Ministry of Truth"}]}
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/publicbody/").mock(return_value=httpx.Response(200, json=stub))
        result = await list_public_bodies(_ctx_with_token(session_token), q="Truth")
    assert result["objects"][0]["name"] == "Ministry of Truth"


@pytest.mark.asyncio
async def test_tool_rejects_missing_session_header():
    """Tool must raise PermissionError when X-Froide-Session header is absent."""
    from unittest.mock import MagicMock
    from froide_mcp.tools import list_requests
    ctx = MagicMock()
    ctx.request_context.request.headers = {}  # no session header
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
