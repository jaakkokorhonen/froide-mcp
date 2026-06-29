"""Unit tests: FroideClient HTTP wrapper."""
from __future__ import annotations
import pytest
import respx
import httpx
from froide_mcp.client import FroideClient


@pytest.mark.asyncio
async def test_get_passes_bearer_token():
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json={"objects": []})
        )
        async with FroideClient("my-token") as c:
            result = await c.get("/api/v1/request/")
        assert result == {"objects": []}
        assert route.called
        assert "Bearer my-token" in route.calls[0].request.headers["authorization"]


@pytest.mark.asyncio
async def test_get_passes_query_params():
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json={"objects": []})
        )
        async with FroideClient("tok") as c:
            await c.get("/api/v1/request/", status="awaiting_response", page=2)
        req = route.calls[0].request
        assert "status=awaiting_response" in str(req.url)
        assert "page=2" in str(req.url)


@pytest.mark.asyncio
async def test_get_none_params_excluded():
    """None-valued kwargs must NOT appear in the query string."""
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.get("/api/v1/request/").mock(
            return_value=httpx.Response(200, json={})
        )
        async with FroideClient("tok") as c:
            await c.get("/api/v1/request/", q=None)
        assert "q=" not in str(route.calls[0].request.url)


@pytest.mark.asyncio
async def test_post_sends_json_body():
    with respx.mock(base_url="http://froide.test") as mock:
        route = mock.post("/api/v1/message/").mock(
            return_value=httpx.Response(201, json={"id": 42})
        )
        async with FroideClient("tok") as c:
            result = await c.post("/api/v1/message/", {"request": 1, "message": "Hi"})
        assert result == {"id": 42}
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["message"] == "Hi"


@pytest.mark.asyncio
async def test_http_error_raises():
    with respx.mock(base_url="http://froide.test") as mock:
        mock.get("/api/v1/request/").mock(return_value=httpx.Response(403))
        with pytest.raises(httpx.HTTPStatusError):
            async with FroideClient("bad-token") as c:
                await c.get("/api/v1/request/")
