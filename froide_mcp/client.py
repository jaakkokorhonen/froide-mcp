"""Thin async HTTP client around the Froide REST API."""
from __future__ import annotations

import httpx
from froide_mcp.config import config


class FroideClient:
    """Async HTTPX client authenticated with a Froide bearer token."""

    def __init__(self, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=config.froide_base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )

    async def __aenter__(self) -> "FroideClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self._http.aclose()

    async def get(self, path: str, **params) -> dict:
        r = await self._http.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, body: dict) -> dict:
        r = await self._http.post(path, json=body)
        r.raise_for_status()
        return r.json()
