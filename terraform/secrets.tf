# ── Secret Manager secrets ───────────────────────────────────────────────
# Values are managed outside Terraform (filled via gcloud or CI).
# Terraform only creates the secret resource; the actual value is set separately.

locals {
  secrets = [
    "google-client-id",
    "google-client-secret",
    "session-secret",
    "froide-client-id",
    "froide-client-secret",
  ]
}

resource "google_secret_manager_secret" "mcp" {
  for_each  = toset(local.secrets)
  secret_id = "froide-mcp-${each.key}"
  project   = var.project_id

  replication {
    auto {}
  }
}

# Allow the MCP service account to read secrets
resource "google_secret_manager_secret_iam_member" "mcp_sa" {
  for_each  = toset(local.secrets)
  secret_id = google_secret_manager_secret.mcp[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp.email}"
}
