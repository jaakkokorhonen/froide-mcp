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

### Orchestration Helpers

Read-only tools that compose existing API calls into higher-level operator
workflows. They never modify Froide data and require no backend changes.

| Tool | Description |
|---|---|
| `triage_my_requests` | Fetches requests across actionable statuses, scores each by urgency and returns a ranked list with a plain-language suggested next step. Accepts optional `statuses` override and free-text `query`. |
| `find_requests_needing_action` | Focused subset of `triage_my_requests` — returns only requests in urgent statuses or with priority ≥ 80. Use this for a short, immediately actionable list. |
| `summarize_request_thread` | Compact operator briefing for a single request: message count, attachment count, current priority and suggested next step. |
| `draft_followup_for_request` | Drafts a follow-up message based on the request's current status and latest thread state. Does not send anything. Pass the result to `send_followup` after review. |
| `preflight_request_submission` | Validates a prospective request locally before calling `make_request`. Returns blocking issues, warnings and a preview of the resolved public body and law names. |
| `get_request_analytics` | Computes status counts and priority bands (critical / high / medium / low) from visible requests using only existing API endpoints. No backend aggregation required. |
| `draft_request` | Drafts a FOI request body from a user goal and a target public body. Does not submit. Designed to feed into `preflight_request_submission`. |
| `followup_after_deadline` | Finds requests in `awaiting_response` status — the most likely deadline-overdue candidates — and pairs each with a ready-to-use follow-up draft. Does not send anything. |

**Priority scoring** used by `triage_my_requests`, `find_requests_needing_action` and `get_request_analytics`:

| Score | Meaning |
|---|---|
| 100 | `requires_user_action`, `awaiting_user_confirmation`, `has_fee` |
| 90 | `awaiting_classification`, `classification_needed` |
| 80 | `publicbody_needed`, `awaiting_publicbody_confirmation` |
| 70 | `awaiting_response` |
| 50 | General review / unknown status |
| 30 | `partially_successful`, `successful` |
| 20 | `refused`, `not_held`, `gone_postal`, `user_withdrew`, `resolved` |

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

## Changelog

### feature/planned-tools

- Added `triage_my_requests` — prioritised work queue across actionable statuses
- Added `find_requests_needing_action` — urgent-only subset of triage
- Added `summarize_request_thread` — compact briefing for a single request
- Added `draft_followup_for_request` — status-aware follow-up draft generator
- Added `preflight_request_submission` — local validation before `make_request`
- Added `get_request_analytics` — status counts and priority bands from existing API
- Added `draft_request` — goal-driven FOI request body drafter
- Added `followup_after_deadline` — deadline follow-up queue with ready drafts
