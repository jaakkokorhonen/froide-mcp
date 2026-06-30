# Deployment guide — froide-mcp

## Prerequisites

- Froide instance running on Cloud Run (see `jaakkokorhonen/froide-infra`)
- GCP project with Secret Manager, Cloud Run, Artifact Registry APIs enabled
- Terraform state bucket (same as froide-infra or separate)

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

## 1. Google OAuth2 Client

1. Go to **Google Cloud Console → APIs & Services → Credentials**
2. Create **OAuth 2.0 Client ID** → Web application
3. Authorised redirect URIs: `https://froide-mcp-xxxx.run.app/auth/callback`
   (use the same value you set as `mcp_base_url` in Terraform)
4. Note the **Client ID** and **Client Secret**

## 2. Froide OAuth2 Application

In Froide Django admin (`/admin/account/application/add/`):

| Field | Value |
|---|---|
| Client type | Confidential |
| Authorization grant type | Client credentials |
| Name | froide-mcp |
| Scopes | `read:request read:profile make:request` |

Note the **Client ID** and **Client Secret**.

## 3. Populate Secret Manager

```bash
export PROJECT=your-gcp-project-id

echo -n "<google-client-id>"     | gcloud secrets versions add froide-mcp-google-client-id     --data-file=- --project=$PROJECT
echo -n "<google-client-secret>" | gcloud secrets versions add froide-mcp-google-client-secret --data-file=- --project=$PROJECT
echo -n "<froide-client-id>"     | gcloud secrets versions add froide-mcp-froide-client-id     --data-file=- --project=$PROJECT
echo -n "<froide-client-secret>" | gcloud secrets versions add froide-mcp-froide-client-secret --data-file=- --project=$PROJECT
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add froide-mcp-session-secret --data-file=- --project=$PROJECT
```

## 4. Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in values, including mcp_base_url
terraform init
terraform plan
terraform apply
```

`terraform output mcp_service_url` gives you the Cloud Run URL. If the first
deploy created a slightly different URL than the placeholder in `terraform.tfvars`,
copy the output value into `mcp_base_url` and apply again so Terraform owns the
final redirect base permanently.

## 5. Update Google redirect URI

After the first deploy, compare the actual service URL with `mcp_base_url`.
If needed, update both:

- `terraform.tfvars` → `mcp_base_url = "https://...run.app"`
- Google OAuth2 Client redirect URI → `https://...run.app/auth/callback`

Then run `terraform apply` again.

## 6. First login test

```bash
open $MCP_URL/auth/login
# Complete Google SSO, copy the X-Froide-Session token
curl -H "X-Froide-Session: <token>" $MCP_URL/mcp
```

## 7. Post-deploy verification

`deploy.yml` fails the release if the deployed Cloud Run service does not pass
`tests/test_smoke.py`. The smoke tests verify:

1. **Liveness** — `GET /healthz` returns `{"status": "ok"}`
2. **Auth middleware** — `GET /mcp` without a session header returns 401 with
   the expected JSON error structure from `RequireSessionMiddleware`
3. **Token validation** — an invalid session token returns 401, not 500
4. **Authenticated E2E path** — a valid `SMOKE_SESSION_TOKEN` can call
   `get_my_profile` via `tools/call`, proving the full chain works in the
   deployed environment

Smoke tests intentionally use only read-only, non-mutating tools.

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

## GitHub Actions secrets required

| Name | Type | Used by | Notes |
|---|---|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Secret | `deploy.yml` | Workload Identity Federation provider resource name |
| `GCP_SERVICE_ACCOUNT` | Secret | `deploy.yml` | Service account email for OIDC impersonation |
| `GCP_REGION` | Variable | `deploy.yml` | GCP region, e.g. `europe-north1` |
| `GCP_PROJECT_ID` | Variable | `deploy.yml` | GCP project ID |
| `MCP_SERVICE_URL` | Variable | `deploy.yml`, `monitor.yml` | Cloud Run service URL |
| `SMOKE_SESSION_TOKEN` | Secret | `deploy.yml`, `monitor.yml` | Short-lived session token for authenticated read-only smoke tests (expires after 8 h) |
