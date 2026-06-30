# GitHub Actions secrets and variables

`cd.yml` (deploy pipeline) and `nightly.yml` (monitoring) read configuration
from GitHub Actions secrets and variables. Secrets are encrypted at rest;
variables are plain text. Neither appears in workflow logs.

## Where to set them

Go to **github.com/jaakkokorhonen/froide-mcp → Settings → Secrets and
variables → Actions**.

- **Secrets** tab → *New repository secret* for each `Secret` row below
- **Variables** tab → *New repository variable* for each `Variable` row below

The `cd.yml` workflow uses the `production` GitHub Environment. If you have
branch-protection rules or required reviewers on that environment, secrets and
variables can also be scoped to it under
**Settings → Environments → production → Environment secrets/variables**.
Repo-level values act as fallback when no environment-level value is set.

## Required values

| Name | Kind | Used by | Value |
|---|---|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Secret | `cd.yml` | WIF provider resource name — see `docs/workload_identity.md` |
| `GCP_SERVICE_ACCOUNT` | Secret | `cd.yml` | Deploy SA email — see `docs/workload_identity.md` |
| `SMOKE_SESSION_TOKEN` | Secret | `cd.yml`, `nightly.yml` | Short-lived session token (8 h TTL) — see *Obtaining a smoke token* below |
| `GCP_REGION` | Variable | `cd.yml`, `nightly.yml` | GCP region matching Cloud Run, e.g. `europe-north1` |
| `GCP_PROJECT_ID` | Variable | `cd.yml` | GCP project ID, e.g. `my-project-123` |
| `MCP_SERVICE_URL` | Variable | `cd.yml`, `nightly.yml` | Cloud Run base URL, e.g. `https://froide-mcp-xxxx.run.app` |

## Obtaining a smoke token

`SMOKE_SESSION_TOKEN` is a normal end-user session token produced by the
`/auth/login` flow. It is used by smoke tests to verify the full
authenticated path against the deployed service.

```bash
# 1. Open the login URL in a browser
open https://froide-mcp-xxxx.run.app/auth/login

# 2. Complete Google SSO. The server returns the token as a JSON response:
#    {"session_token": "eyJ..."}

# 3. Copy the token value and add it as the SMOKE_SESSION_TOKEN secret
```

The token expires after 8 hours. The nightly workflow runs at 04:00 UTC
(07:00 EEST). If it fails with a 401, rotate the secret:

```bash
# Re-authenticate and update the secret via GitHub CLI
gh secret set SMOKE_SESSION_TOKEN --repo jaakkokorhonen/froide-mcp
```

Paste the new token when prompted.

## Setting secrets via GitHub CLI

If you prefer the command line over the web UI:

```bash
# Secrets
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo jaakkokorhonen/froide-mcp
gh secret set GCP_SERVICE_ACCOUNT            --repo jaakkokorhonen/froide-mcp
gh secret set SMOKE_SESSION_TOKEN            --repo jaakkokorhonen/froide-mcp

# Variables
gh variable set GCP_REGION       --body "europe-north1"                    --repo jaakkokorhonen/froide-mcp
gh variable set GCP_PROJECT_ID   --body "your-gcp-project-id"              --repo jaakkokorhonen/froide-mcp
gh variable set MCP_SERVICE_URL  --body "https://froide-mcp-xxxx.run.app" --repo jaakkokorhonen/froide-mcp
```

`gh secret set` prompts for the value interactively so it never touches your
shell history.
