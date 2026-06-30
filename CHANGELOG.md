# Changelog

All notable changes to froide-mcp are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — v0.1.0

First deployable release. Covers the full path from Cloud Run infra to
authenticated MCP tool calls via a Froide instance.

### Added

#### Core server
- FastMCP 3.x HTTP server with `Streamable HTTP` transport at `/mcp`
- `RequireSessionMiddleware` — rejects unauthenticated requests with
  structured `{"error": "Unauthenticated", "detail": "..."}` JSON
- `/healthz` liveness endpoint
- `/auth/login` + `/auth/callback` Google OAuth2 flow; session token returned
  as JSON, accepted on subsequent requests via `X-Froide-Session` header
- `config.py` — all configuration from environment variables; validated at
  startup with clear error messages

#### MCP tools
- `get_my_profile` — authenticated user profile from Froide
- `list_my_requests` — paginated list of the user’s FOI requests
- `get_request` — full detail for a single request
- `search_requests` — free-text search across requests
- `get_public_bodies` — search and browse public bodies
- `make_request` — submit a new FOI request
- `send_followup` — send a follow-up message on an existing request
- `get_attachment` — fetch an attachment from a request thread

#### Orchestration tools
- `triage_my_requests` — priority-scored work queue across all urgent
  request statuses
- `find_requests_needing_action` — focused subset of triage (priority ≥ 80)
- `summarize_request_thread` — operator briefing for a single thread
- `draft_followup_for_request` — status-aware follow-up draft (does not send)
- `preflight_request_submission` — validation pass before `make_request`
- `get_request_analytics` — status distribution and priority bands
- `draft_request` — FOI request body draft from a plain-language goal
- `followup_after_deadline` — statutory-deadline follow-up draft

#### Infrastructure (Terraform)
- Cloud Run v2 service with Secret Manager env injection
- Artifact Registry repository (`froide` Docker repository)
- Secret Manager secrets for all five OAuth credentials
- MCP runtime service account with `roles/run.invoker` on the Froide service
- `terraform.tfvars.example` with all required variables documented

#### CI/CD
- `ci.yml` — ruff lint + format check, mypy, pytest (unit + integration,
  coverage ≥ 80%), Docker build check
- `cd.yml` — build → Artifact Registry push → Cloud Run deploy → smoke
  tests; uses Workload Identity Federation (no long-lived keys)
- `nightly.yml` — 04:00 UTC smoke run; opens GitHub Issue with pytest output
  on failure

#### Documentation
- `README.md` — architecture diagram, quickstart, full tool reference
- `docs/deployment.md` — end-to-end deploy guide including two-pass Terraform
- `docs/workload_identity.md` — WIF setup (Terraform + gcloud, reuse from
  froide-infra)
- `docs/github_actions_secrets.md` — all six secrets/variables, rotation
  instructions for `SMOKE_SESSION_TOKEN`
- `docs/orchestration.md` — all eight orchestration tools documented with
  parameter tables and example return values

### Fixed

- `tests/test_smoke.py`: read `MCP_SERVICE_URL` (consistent with `cd.yml` and
  `nightly.yml`) instead of `SMOKE_TEST_URL`, which was never set — all
  smoke tests were silently skipped on every deploy

[Unreleased]: https://github.com/jaakkokorhonen/froide-mcp/compare/HEAD...HEAD
