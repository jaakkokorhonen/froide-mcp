# froide-mcp

MCP server for the [Froide](https://github.com/okfde/froide) FOI platform.

Runs as a standalone Cloud Run Service alongside a Froide installation. Authenticates users via **Google OAuth2 SSO** (same as Froide admin) and exposes Froide's REST API as MCP tools consumable by Claude and other MCP clients.

All requests to `/mcp/*` require a valid session token obtained via `/auth/login`. No anonymous tool access.

## Architecture

```
Claude / MCP client
      │  HTTP + SSE  +  X-Froide-Session header
      ▼
froide-mcp  (Cloud Run Service, FastMCP)
  └─ RequireSessionMiddleware  ← enforces Google SSO on every /mcp/* request
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

## Authentication flow

1. Visit `GET /auth/login` → redirected to Google
2. Google redirects to `GET /auth/callback?code=...`
3. Server verifies the ID token, optionally checks `hd` (hosted domain)
4. Exchanges for a Froide OAuth2 bearer token via `client_credentials`
5. Returns a signed session token (HMAC-SHA256, 8 h TTL)
6. Include the token as `X-Froide-Session: <token>` in all MCP requests

## Tools exposed

### FOI Requests

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_requests` | GET | `/api/v1/request/` |
| `get_request` | GET | `/api/v1/request/{id}/` |
| `search_requests` | GET | `/api/v1/request/?q={query}` |
| `make_request` | POST | `/api/v1/request/` |
| `send_followup` | POST | `/api/v1/message/` |
| `set_request_status` | PATCH | `/api/v1/request/{id}/` |

### Public Bodies & Jurisdictions

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_public_bodies` | GET | `/api/v1/publicbody/` |
| `get_public_body` | GET | `/api/v1/publicbody/{id}/` |
| `list_jurisdictions` | GET | `/api/v1/jurisdiction/` |

### Campaigns

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_campaigns` | GET | `/api/v1/campaign/` |
| `get_campaign` | GET | `/api/v1/campaign/{id}/` |

### Laws

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_laws` | GET | `/api/v1/law/` |
| `get_law` | GET | `/api/v1/law/{id}/` |

### Attachments & Profile

| Tool | Method | Froide endpoint |
|---|---|---|
| `list_attachments` | GET | `/api/v1/attachment/?belongs_to={request_id}` |
| `get_my_profile` | GET | `/api/v1/user/` |

## Local development

```bash
cp .env.example .env
# fill in FROIDE_BASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ...
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
