# froide-mcp

MCP server for the [Froide](https://github.com/okfde/froide) FOI platform.

Runs as a standalone Cloud Run Service alongside a Froide installation. Authenticates users via **Google OAuth2 SSO** (same as Froide admin) and exposes Froide's REST API as MCP tools consumable by Claude and other MCP clients.

All requests to `/mcp/*` require a valid session token obtained via `/auth/login`. No anonymous tool access.

## Operational invariants

A few pieces must stay aligned across code, Terraform, and docs:

- `MCP_BASE_URL` is required at runtime for the Google OAuth callback URI and must be managed by Terraform so later applies do not silently remove it.
- Smoke tests are intentionally conservative. They check deploy health and auth error handling without pinning FastMCP wire-transport details unless that protocol is explicitly documented and version-locked.
- End-user session tokens expire after 8 hours, so they are fine for interactive use and short post-deploy checks but not for long-lived unattended monitoring.

## Architecture

```
Claude / MCP client
      │  Streamable HTTP  +  X-Froide-Session header
      ▼
froide-mcp  (Cloud Run Service, FastMCP 3.x)
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

### Orchestration helpers

These tools compose existing API calls into higher-level workflows. They do **not** modify any Froide data and require no Django/backend changes. Their purpose is to help operators work more efficiently inside the existing Froide UI.

| Tool | What it does |
|---|---|
| `triage_my_requests` | Builds a prioritised work queue across actionable statuses with a suggested next step per request |
| `find_requests_needing_action` | Filters the triage queue to only requests that likely need an immediate human decision |
| `summarize_request_thread` | Returns a compact operator briefing for one request: status, message count, attachment count, priority |
| `draft_followup_for_request` | Drafts a status-aware follow-up message; does not send anything |
| `draft_request` | Drafts a FOI request body from a goal and records description; does not submit anything |
| `preflight_request_submission` | Validates a prospective request (subject, body, public body) before calling `make_request` |
| `get_request_analytics` | Aggregates visible requests into status counts and priority bands |
| `followup_after_deadline` | Drafts a statutory-deadline follow-up for a request that has exceeded its legal response period; does not send anything |

## Development history

The orchestration helper layer was built iteratively. The initial design and implementation draft were produced without direct repository access: a local patch-level proposal was written that added documentation and the first three orchestration tools (`triage_my_requests`, `find_requests_needing_action`, `summarize_request_thread`) on top of the existing API layer.

That first version was deliberately scoped to UI-level orchestration with no Django changes required — the three tools compose `list_requests`, `get_request` and `list_attachments` calls that already existed. The README update described the new "Orchestration helpers" section and established the principle that these tools guide operators inside the existing Froide UI rather than replicating backend logic.

The remaining five tools (`draft_followup_for_request`, `preflight_request_submission`, `get_request_analytics`, `draft_request`, `followup_after_deadline`) and their tests were added in subsequent PRs once repository access was available, completing the orchestration layer. All tools follow the same bearer-token authentication pattern as the core API tools and build exclusively on `/api/v1/` endpoints.

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
