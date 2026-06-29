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
- Smoke tests are transport-agnostic production checks. They verify service
  liveness, auth middleware behaviour, and non-500 failure modes. They do not
  try to emulate the full MCP transport unless the exact wire protocol is
  intentionally pinned and tested.
- `SMOKE_SESSION_TOKEN` is suitable for short-lived post-deploy checks, but not
  for unattended long-term monitoring because application session tokens expire
  after 8 hours.

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
| `SMOKE_SESSION_TOKEN` | Secret | `deploy.yml` | Short-lived session token for post-deploy smoke tests |

## Monitoring note

`monitor.yml` should not rely on `SMOKE_SESSION_TOKEN` because session tokens
expire after 8 hours. For unattended monitoring, prefer checks that do not
require an end-user session, such as `/healthz`, Cloud Run uptime probes, or a
future dedicated non-interactive monitoring credential.
