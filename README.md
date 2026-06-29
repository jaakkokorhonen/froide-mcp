# froide-mcp

MCP server for the [Froide](https://github.com/okfde/froide) FOI platform.

Runs as a standalone Cloud Run Service alongside a Froide installation. Authenticates users via **Google OAuth2 SSO** (same as Froide admin) and exposes Froide's REST API as MCP tools consumable by Claude and other MCP clients.

## Architecture

```
Claude / MCP client
      │  HTTP + SSE
      ▼
froide-mcp  (Cloud Run Service, FastMCP)
      │  OAuth2 Bearer token
      ▼
Froide REST API  (Cloud Run Service)
      │
      ▼
PostgreSQL (Cloud SQL)
```

This repo is applied as a **patch on top of a Froide installation** — it does not fork or modify Froide itself. It depends on:
- A running Froide instance with the REST API enabled
- A Google OAuth2 Client configured in Google Cloud Console
- Froide OAuth2 application (`account.Application`) with `client_credentials` grant

## Tools exposed

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_requests` | GET | `/api/v1/request/` |
| `get_request` | GET | `/api/v1/request/{id}/` |
| `search_requests` | GET | `/api/v1/request/?q=` |
| `send_followup` | POST | `/api/v1/message/` |
| `list_public_bodies` | GET | `/api/v1/publicbody/` |
| `get_public_body` | GET | `/api/v1/publicbody/{id}/` |
| `list_attachments` | GET | `/api/v1/attachment/?belongs_to=` |
| `get_law` | GET | `/api/v1/law/{id}/` |

## Local development

```bash
cp .env.example .env
# fill in FROIDE_BASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
pip install -e .[dev]
python -m froide_mcp.server
```

## Deployment

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

See [docs/deployment.md](docs/deployment.md) for full setup.
