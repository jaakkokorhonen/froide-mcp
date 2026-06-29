"""Configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    froide_base_url: str
    google_client_id: str
    google_client_secret: str
    # Secret used to sign session tokens (generate with: openssl rand -hex 32)
    session_secret: str
    # Restrict SSO login to this Google Workspace domain (e.g. "yourdomain.fi").
    # Leave empty to allow any Google account.
    allowed_hd: str
    # Froide OAuth2 application credentials for machine-to-machine calls
    froide_client_id: str
    froide_client_secret: str
    # Cloud Run service URL of this MCP server (used as OAuth2 redirect URI)
    mcp_base_url: str
    port: int = 8080

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            froide_base_url=os.environ["FROIDE_BASE_URL"].rstrip("/"),
            google_client_id=os.environ["GOOGLE_CLIENT_ID"],
            google_client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            session_secret=os.environ["SESSION_SECRET"],
            allowed_hd=os.environ.get("ALLOWED_HD", ""),
            froide_client_id=os.environ["FROIDE_CLIENT_ID"],
            froide_client_secret=os.environ["FROIDE_CLIENT_SECRET"],
            mcp_base_url=os.environ["MCP_BASE_URL"].rstrip("/"),
            port=int(os.environ.get("PORT", "8080")),
        )


config = Config.from_env()
