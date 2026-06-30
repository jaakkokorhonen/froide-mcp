# Workload Identity Federation for GitHub Actions

`cd.yml` authenticates to GCP using
[Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
(WIF). This avoids long-lived service account JSON keys — GitHub Actions
receives a short-lived OIDC token from Google instead.

## How it works

```
GitHub Actions runner
  │  OIDC token (signed by GitHub, audience = GCP WIF pool)
  ▼
GCP Workload Identity Pool
  │  checks token subject matches repo/branch condition
  ▼
Impersonates deploy-sa@PROJECT.iam.gserviceaccount.com
  │  short-lived access token (1 h)
  ▼
Artifact Registry push + Cloud Run deploy
```

The WIF pool is configured once in Terraform (or gcloud). Afterwards, any
push to `main` or a `v*` tag triggers the deploy pipeline without any stored
credentials.

## Prerequisites

- GCP project with the **IAM Credentials API** enabled
- A deploy service account with the roles listed below
- The `froide-infra` Terraform state bucket accessible (or a separate bucket)

If `froide-infra` already has a WIF pool set up, you can reuse it by adding
a new attribute condition and service account binding — skip to
*Reusing an existing pool* below.

## Option A — Terraform (recommended)

Add the following to your infra Terraform (e.g. in `froide-infra` or a new
`froide-mcp-infra` root):

```hcl
locals {
  github_org  = "jaakkokorhonen"
  github_repo = "froide-mcp"
  project     = var.project_id
}

# ── Workload Identity Pool ─────────────────────────────────────────────────────

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  project                   = local.project
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  project                            = local.project

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Only allow tokens from this repository
  attribute_condition = "attribute.repository == '${local.github_org}/${local.github_repo}'"
}

# ── Deploy service account ──────────────────────────────────────────────────

resource "google_service_account" "deploy" {
  account_id   = "froide-mcp-deploy"
  display_name = "froide-mcp GitHub Actions deploy SA"
  project      = local.project
}

# Allow the WIF provider to impersonate the deploy SA
resource "google_service_account_iam_member" "wif_impersonate" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.github_org}/${local.github_repo}"
}

# ── IAM roles for the deploy SA ────────────────────────────────────────────

locals {
  deploy_sa_roles = [
    "roles/run.developer",           # gcloud run services update
    "roles/artifactregistry.writer",  # docker push
    "roles/iam.serviceAccountUser",   # act as the Cloud Run runtime SA
  ]
}

resource "google_project_iam_member" "deploy_sa" {
  for_each = toset(local.deploy_sa_roles)
  project  = local.project
  role     = each.value
  member   = "serviceAccount:${google_service_account.deploy.email}"
}

# ── Outputs ──────────────────────────────────────────────────────────────

output "wif_provider" {
  description = "Value for GCP_WORKLOAD_IDENTITY_PROVIDER GitHub secret"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_sa_email" {
  description = "Value for GCP_SERVICE_ACCOUNT GitHub secret"
  value       = google_service_account.deploy.email
}
```

After `terraform apply`, copy the two output values into GitHub Actions
secrets:

```bash
terraform output wif_provider    # → GCP_WORKLOAD_IDENTITY_PROVIDER
terraform output deploy_sa_email # → GCP_SERVICE_ACCOUNT
```

## Option B — gcloud (manual, no Terraform)

```bash
export PROJECT=your-gcp-project-id
export REPO=jaakkokorhonen/froide-mcp

# 1. Enable required APIs
gcloud services enable iamcredentials.googleapis.com \
  --project=$PROJECT

# 2. Create WIF pool
gcloud iam workload-identity-pools create github-actions \
  --location=global \
  --display-name="GitHub Actions" \
  --project=$PROJECT

# 3. Create OIDC provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-actions \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="attribute.repository=='${REPO}'" \
  --project=$PROJECT

# 4. Create deploy service account
gcloud iam service-accounts create froide-mcp-deploy \
  --display-name="froide-mcp deploy SA" \
  --project=$PROJECT

# 5. Grant deploy SA the required roles
for ROLE in roles/run.developer roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:froide-mcp-deploy@${PROJECT}.iam.gserviceaccount.com" \
    --role=$ROLE
done

# 6. Allow WIF to impersonate the deploy SA
POOL_NAME=$(gcloud iam workload-identity-pools describe github-actions \
  --location=global --project=$PROJECT --format='value(name)')

gcloud iam service-accounts add-iam-policy-binding \
  froide-mcp-deploy@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${REPO}" \
  --project=$PROJECT

# 7. Print the values needed for GitHub secrets
PROVIDER=$(gcloud iam workload-identity-pools providers describe github-provider \
  --location=global \
  --workload-identity-pool=github-actions \
  --project=$PROJECT \
  --format='value(name)')

echo "GCP_WORKLOAD_IDENTITY_PROVIDER = $PROVIDER"
echo "GCP_SERVICE_ACCOUNT            = froide-mcp-deploy@${PROJECT}.iam.gserviceaccount.com"
```

## Reusing an existing pool from froide-infra

If `froide-infra` already has a `github-actions` WIF pool and provider, you
only need to:

1. Add `froide-mcp-deploy` service account (steps 4–5 above)
2. Update the provider's `attribute_condition` to also allow this repo, or
   use a `principalSet` scoped to the specific repository (step 6 above)
3. Note the existing provider resource name for `GCP_WORKLOAD_IDENTITY_PROVIDER`

The provider resource name follows this format:

```
projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID
```

Retrieve it with:

```bash
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global \
  --workload-identity-pool=github-actions \
  --project=$PROJECT \
  --format='value(name)'
```
