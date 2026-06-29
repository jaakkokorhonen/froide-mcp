# ── Service account ───────────────────────────────────────────────────────

resource "google_service_account" "mcp" {
  account_id   = "froide-mcp"
  display_name = "Froide MCP Server"
  project      = var.project_id
}

# Allow MCP SA to invoke the Froide Cloud Run service
data "google_cloud_run_service" "froide" {
  name     = "froide"  # adjust if your Froide service has a different name
  location = var.region
  project  = var.project_id
}

resource "google_cloud_run_service_iam_member" "mcp_invokes_froide" {
  service  = data.google_cloud_run_service.froide.name
  location = var.region
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.mcp.email}"
}
