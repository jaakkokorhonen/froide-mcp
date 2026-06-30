# Changelog

All notable changes to froide-mcp are documented here.

## [1.0.0] — 2026-06-30

First stable release. The service is deployed on Google Cloud Run alongside a
Froide installation and is ready for production use.

### What is included

**Core infrastructure**
- FastMCP 3.x HTTP server mountable behind any ASGI stack
- `RequireSessionMiddleware` — every `/mcp/*` request requires a valid
  Google SSO session token; anonymous access is rejected with 401
- Google OAuth2 SSO login flow (`/auth/login` → `/auth/callback`)
- HMAC-SHA256 signed session tokens (8 h TTL)
- Froide OAuth2 `client_credentials` bearer-token exchange
- Terraform module for Cloud Run, Secret Manager, Artifact Registry, and
  IAM on GCP
- CI pipeline: ruff, mypy, pytest (≥ 80 % coverage), Docker build
- CD pipeline: Cloud Build + Cloud Run deploy with post-deploy smoke tests
- Nightly monitoring with automatic GitHub Issue alerting on failure

**Tools exposed (23 total)**

| Category | Tools |
|---|---|
| FOI Requests | `list_requests`, `get_request`, `search_requests`, `make_request`, `send_followup`, `set_request_status` |
| Public Bodies & Jurisdictions | `list_public_bodies`, `get_public_body`, `list_jurisdictions` |
| Campaigns | `list_campaigns`, `get_campaign` |
| Laws | `list_laws`, `get_law` |
| Attachments & Profile | `list_attachments`, `get_my_profile` |
| Orchestration helpers | `triage_my_requests`, `find_requests_needing_action`, `summarize_request_thread`, `draft_followup_for_request`, `draft_request`, `preflight_request_submission`, `get_request_analytics`, `followup_after_deadline` |

Orchestration helpers are read-or-compose only — they do not modify any Froide
data and require no Django/backend changes.

**Smoke tests**

Post-deploy smoke and nightly monitoring verify four levels:
1. Service liveness (`/healthz`)
2. Auth middleware rejects missing session with correct 401 structure
3. Invalid session token returns 401, not 500
4. Authenticated `tools/call` → `get_my_profile` proves the full path:
   Cloud Run → session middleware → token decode → Froide bearer → Froide API

### Known limitations

- `auth.py` decodes the Google ID token JWT payload without JWKS signature
  verification. Transport-level trust is high (direct HTTPS POST to
  `accounts.google.com`), but stricter deployments should add
  `google-auth` or `PyJWT + GOOGLE_CERTS_URL` verification.
- `SMOKE_SESSION_TOKEN` expires after 8 hours; nightly monitoring will
  report failures if the secret is not rotated.
