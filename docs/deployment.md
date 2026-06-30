# Deployment guide — froide-mcp

## Prerequisites

- Froide instance running on Cloud Run (see `jaakkokorhonen/froide-infra`)
- GCP project with Secret Manager, Cloud Run, Artifact Registry APIs enabled
- Terraform state bucket (same as froide-infra or separate)
- Workload Identity Federation configured — see `docs/workload_identity.md`

## Alignment rules

This repository has a few operational invariants that must stay aligned across
Terraform, runtime code, tests, and docs:

- `MCP_BASE_URL` is a runtime requirement because Google OAuth uses it as the
  redirect URI base. It must be managed by Terraform, not set manually with
  `gcloud run services update`, because a later `terraform apply` would remove
  manually-added env vars from the Cloud Run service.
- Smoke tests are functionally meaningful production checks. They verify service
  liveness, auth middleware behaviour (correct 401 responses), and at least one
  authenticated read-only end-to-end MCP tool path against the deployed service.
  They do not pin exact FastMCP wire transport details unless those are
  intentionally documented and stabilised.
- `SMOKE_SESSION_TOKEN` is suitable for short-lived post-deploy checks and
  nightly monitoring, but application session tokens expire after 8 hours. If
  a nightly run fails due to token expiry rather than an application regression,
  rotate the secret and re-run. For unattended long-term monitoring a dedicated
  non-interactive read-only credential would be preferable.

## Security note: Google ID token verification

> **Known limitation:** `auth.py` decodes the Google ID token JWT payload
> without verifying the JWKS signature from `accounts.google.com`. The token
> is received over a direct server-to-server HTTPS POST to Google's token
> endpoint, so the transport-level trust is high in practice. However, for
> stricter production hardening, replace the manual base64 decode in
> `exchange_google_code()` with a proper JWKS verification using
> [`google-auth`](https://pypi.org/project/google-auth/) or
> `PyJWT` + `GOOGLE_CERTS_URL`.

## 1. Workload Identity Federation

GitHub Actions authenticates to GCP using Workload Identity Federation — no
long-lived service account keys are stored anywhere. Set this up first.

See **`docs/workload_identity.md`** for the full Terraform and gcloud
instructions. The setup produces two values needed in step 6:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` — WIF provider resource name
- `GCP_SERVICE_ACCOUNT` — deploy service account email

## 2. Google OAuth2 Client

1. Go to **Google Cloud Console → APIs & Services → Credentials**
2. Create **OAuth 2.0 Client ID** → Web application
3. Authorised redirect URIs: `https://froide-mcp-xxxx.run.app/auth/callback`
   (use the same value you will set as `mcp_base_url` in Terraform)
4. Note the **Client ID** and **Client Secret**

## 3. Froide OAuth2 Application

In Froide Django admin (`/admin/account/application/add/`):

| Field | Value |
|---|---|
| Client type | Confidential |
| Authorization grant type | Client credentials |
| Name | froide-mcp |
| Scopes | `read:request read:profile make:request` |

Note the **Client ID** and **Client Secret**.

## 4. Populate Secret Manager

```bash
export PROJECT=your-gcp-project-id

echo -n "<google-client-id>"     | gcloud secrets versions add froide-mcp-google-client-id     --data-file=- --project=$PROJECT
echo -n "<google-client-secret>" | gcloud secrets versions add froide-mcp-google-client-secret --data-file=- --project=$PROJECT
echo -n "<froide-client-id>"     | gcloud secrets versions add froide-mcp-froide-client-id     --data-file=- --project=$PROJECT
echo -n "<froide-client-secret>" | gcloud secrets versions add froide-mcp-froide-client-secret --data-file=- --project=$PROJECT
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add froide-mcp-session-secret --data-file=- --project=$PROJECT
```

The Secret Manager secrets are created by `terraform/secrets.tf`. Run
`terraform apply` (step 5) before populating them if you have not already.

## 5. Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in values
terraform init
terraform plan
terraform apply
```

`terraform output mcp_service_url` gives you the Cloud Run URL. If the URL
differs from the placeholder in `terraform.tfvars`, copy the output value
into `mcp_base_url` and apply again so Terraform owns the redirect base
permanently:

```bash
# terraform.tfvars
mcp_base_url = "https://froide-mcp-xxxx.run.app"   # <- update to actual URL
```

```bash
terraform apply   # re-apply to push the corrected MCP_BASE_URL env var
```

## 6. GitHub Actions secrets and variables

Set the six values listed in **`docs/github_actions_secrets.md`**. The
deploy pipeline (`cd.yml`) and nightly monitoring (`nightly.yml`) both read
from these.

Quick reference:

| Name | Kind | Value |
|---|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Secret | From WIF setup (step 1) |
| `GCP_SERVICE_ACCOUNT` | Secret | From WIF setup (step 1) |
| `SMOKE_SESSION_TOKEN` | Secret | From `/auth/login` — see step 7 |
| `GCP_REGION` | Variable | e.g. `europe-north1` |
| `GCP_PROJECT_ID` | Variable | GCP project ID |
| `MCP_SERVICE_URL` | Variable | Cloud Run URL from step 5 |

## 7. First login and smoke token

```bash
# Open in browser — complete Google SSO
open https://froide-mcp-xxxx.run.app/auth/login
# Copy the session_token from the JSON response

# Quick manual check
curl -H "X-Froide-Session: <token>" https://froide-mcp-xxxx.run.app/healthz
```

Set the token as `SMOKE_SESSION_TOKEN` in GitHub Actions secrets. It expires
after 8 hours — see `docs/github_actions_secrets.md` for rotation
instructions.

## 8. CD pipeline

Pushing to `main` or tagging `v*` triggers `cd.yml`:

```
Build image → Push to Artifact Registry → gcloud run services update → pytest test_smoke.py
```

The deploy step fails and rolls back if smoke tests do not pass. Manual
trigger is also available via **Actions → Deploy → Run workflow**.

## 9. Nightly monitoring

`nightly.yml` runs smoke tests every night at 04:00 UTC (07:00 EEST). On
failure it opens a GitHub Issue with the pytest output and a note about
`SMOKE_SESSION_TOKEN` rotation.

## MCP client configuration (Claude Desktop)

```json
{
  "mcpServers": {
    "froide": {
      "url": "https://froide-mcp-xxxx.run.app/mcp",
      "headers": {
        "X-Froide-Session": "<your-session-token>"
      }
    }
  }
}
```

Replace `xxxx` with your actual Cloud Run URL and `<your-session-token>` with
a token obtained from `/auth/login`.
