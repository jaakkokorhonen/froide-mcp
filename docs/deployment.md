# Deployment guide — froide-mcp

## Prerequisites

- Froide instance running on Cloud Run (see `jaakkokorhonen/froide-infra`)
- GCP project with Secret Manager, Cloud Run, Artifact Registry APIs enabled
- Terraform state bucket (same as froide-infra or separate)

## 1. Google OAuth2 Client

1. Go to **Google Cloud Console → APIs & Services → Credentials**
2. Create **OAuth 2.0 Client ID** → Web application
3. Authorised redirect URIs: `https://froide-mcp-xxxx.run.app/auth/callback`
   (update after first Terraform deploy — see step 5)
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
cp terraform.tfvars.example terraform.tfvars   # fill in values
terraform init
terraform plan
terraform apply
```

`terraform output mcp_service_url` gives you the Cloud Run URL.

## 5. Set MCP_BASE_URL (chicken-and-egg fix)

After the first deploy, the service URL is known. Set it:

```bash
MCP_URL=$(terraform output -raw mcp_service_url)
gcloud run services update froide-mcp \
  --set-env-vars MCP_BASE_URL=$MCP_URL \
  --region $REGION --project $PROJECT
```

Also update the Google OAuth2 Client redirect URI to `$MCP_URL/auth/callback`.

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
| `MCP_SERVICE_URL` | Variable | `deploy.yml`, `monitor.yml` | Cloud Run service URL — set after first deploy (`terraform output mcp_service_url`) |
| `SMOKE_SESSION_TOKEN` | Secret | `deploy.yml`, `monitor.yml` | Long-lived session token for smoke tests — obtain via `/auth/login` and rotate before expiry (8 h TTL) |
