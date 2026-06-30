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

## Tool naming rules

Tool names intentionally communicate both **shape** and **side effects**:

- `list_*` returns a collection, optionally filtered with query parameters such as `q`, `status`, or `jurisdiction`.
- `get_*` returns one resource by ID.
- `draft_*` returns structured drafting context and **never mutates Froide data**.
- `preflight_*` validates a prospective action and **never mutates Froide data**.
- `send_*`, `make_*`, and `set_*` **mutate Froide data** and should only be called after explicit user or agent confirmation.

This contract reduces ambiguity for MCP clients about which tools are safe to call speculatively and which have irreversible or externally visible effects.

## Tool contract

### FOI Requests

| Tool | Mutates data | Input | Returns | Typical use |
|---|---|---|---|---|
| `list_requests` | No | optional `status`, `q`, `page` | Froide paginated request collection | Browse or search requests by status or keyword |
| `get_request` | No | `request_id` | One request with thread metadata | Inspect one request before manual action |
| `make_request` | **Yes** | `public_body_id`, `subject`, `body`, optional `law_id`, `campaign_id`, `public` | Created Froide request object | Submit a new FOI request |
| `send_followup` | **Yes** | `request_id`, `message`, optional `subject` | Created follow-up message object | Send a reviewed follow-up to an authority |
| `set_request_status` | **Yes** | `request_id`, `status`, optional `resolution` | Updated request object | Mark request outcome after review |

### Public Bodies, Jurisdictions, Campaigns, Laws, Attachments, Profile

| Tool | Mutates data | Input | Returns | Typical use |
|---|---|---|---|---|
| `list_public_bodies` | No | optional `q`, `jurisdiction`, `page` | Froide paginated public body collection | Find target authority by name or jurisdiction |
| `get_public_body` | No | `public_body_id` | One public body | Verify authority identity before drafting |
| `list_jurisdictions` | No | optional `page` | Froide paginated jurisdiction collection | Discover jurisdiction IDs for filtering |
| `list_campaigns` | No | optional `page` | Froide paginated campaign collection | Browse campaigns for request association |
| `get_campaign` | No | `campaign_id` | One campaign | Inspect campaign details |
| `list_laws` | No | optional `jurisdiction`, `page` | Froide paginated law collection | Find applicable FOI laws |
| `get_law` | No | `law_id` | One law | Inspect law before request creation |
| `list_attachments` | No | `request_id` | Froide paginated attachment collection | Review request documents |
| `get_my_profile` | No | none | Authenticated user profile | Confirm current user identity |

### Orchestration helpers

These tools compose existing API calls into higher-level workflows. They do **not** modify any Froide data unless they explicitly redirect the caller to a mutating tool such as `send_followup` or `make_request`.

| Tool | Mutates data | Input | Returns | Typical use |
|---|---|---|---|---|
| `triage_my_requests` | No | optional `statuses`, `query`, `page` | Ranked work queue with status, priority, rationale, next step | Build an operator worklist |
| `find_requests_needing_action` | No | optional `query`, `page` | Urgent subset of the triage queue | Identify requests needing a human decision now |
| `summarize_request_thread` | No | `request_id` | Compact briefing: counts, priority, next step | Orient before opening a request in the Froide UI |
| `draft_followup_for_request` | No | `request_id` | `suggested_subject`, `draft_context`, instructions | Language-aware follow-up drafting context |
| `draft_request` | No | `public_body_id`, `goal`, `records_description`, optional `law_id`, `public` | `suggested_subject`, `draft_context`, instructions | Language-aware request drafting context before review |
| `preflight_request_submission` | No | `public_body_id`, `subject`, `body`, optional `law_id`, `campaign_id`, `public` | Validation issues, warnings, preview | Validate a request before calling `make_request` |
| `get_request_analytics` | No | optional `statuses`, `page` | Status counts, priority bands, top requests | Lightweight dashboards or summaries |
| `followup_after_deadline` | No | `request_id` | `suggested_subject`, `draft_context`, instructions | Language-aware deadline follow-up drafting context |

## Drafting model

Drafting tools are **language-aware but language-neutral in implementation**.

They do not return hard-coded prose in any specific language. Instead, they return a structured `draft_context` object that the MCP client, LLM, or human operator renders into the final message text in the language appropriate for the request thread and target authority.

This applies to all three drafting tools:

- `draft_followup_for_request`
- `followup_after_deadline`
- `draft_request`

A typical `draft_context` from `draft_request` contains fields such as `request_goal`, `records_description`, `public_body_name`, `law_name`, `disclosure_preferences`, and `drafting_notes`. The caller uses this structured context to compose the final subject line and request body in the correct language.

### Drafting safety contract

`draft_*` tools return context, not final prose. A successful draft result means **no message has been sent and no request has been created**.

Recommended safe flow:

1. Call a `draft_*` tool.
2. Render or review the final prose in the target language.
3. Optionally call `preflight_request_submission` for new requests.
4. Only then call a mutating tool such as `send_followup` or `make_request`.

## Pagination model

Collection tools pass the `page` parameter through to the Froide REST API and return Froide's standard paginated envelope. MCP callers inspect `count`, `next`, and `previous` in the response to decide whether to request the next page.

## Triage configuration

Workflow prioritisation is driven by status-based heuristics: status → priority band and status → next-step text. These rules should be treated as **data**, not hidden business logic.

- Keep the canonical status mappings in one place (dictionary constants or a small YAML/JSON config).
- Prefer dictionary lookups with a fallback over long `if/elif` chains — this makes operator policy easier to review, test, and evolve without rewriting control flow.
- Document every workflow status token that influences triage and make it obvious which statuses are considered urgent and why.

## Testing strategy

The most valuable tests protect **decision semantics**, not only HTTP transport. The workflow layer already contains meaningful logic, so tests should cover both layers.

### Unit tests for pure decision logic

These functions are deterministic and should have fast parametrized tests with no network or authentication dependency:

- `_priority_for_request`
- `_derive_next_step`
- `_followup_draft_context`
- `_deadline_followup_draft_context`
- `_contains_user_action_hint`

Recommended cases:

- Each urgent status maps to the expected priority band.
- `awaiting_response`, `successful`, `refused`, and unknown statuses produce stable next-step text.
- Deadline draft context always sets `deadline_exceeded=True`.
- Free-text hints such as `fee`, `clarif`, `postal`, and `confirmation` behave as intended, including negative phrases such as `no fee`.

### Integration tests with a mocked FroideClient

Mock the Froide API boundary and assert the JSON shape returned by higher-level tools:

- `triage_my_requests`
- `preflight_request_submission`
- `draft_followup_for_request`
- `draft_request`
- `followup_after_deadline`
- `get_request_analytics`

Verify:

- Required keys are always present in the response.
- `draft_context` shape is stable — field names and semantics do not drift silently.
- Mutating tools are not called by draft or triage helpers.
- Pagination parameters are forwarded correctly.
- Edge cases such as empty `results`, missing messages, or absent optional metadata are handled gracefully.

MCP agents depend on field names and response shape; silent schema drift can break agent behaviour even when the underlying Froide API still works correctly.

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
