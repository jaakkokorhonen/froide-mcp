# ── Artifact Registry repository for the MCP container image ─────────────

resource "google_artifact_registry_repository" "froide" {
  repository_id = "froide"
  location      = var.region
  format        = "DOCKER"
  project       = var.project_id

  # Skip if the froide-infra repo already created this
  lifecycle {
    ignore_changes = [labels]
  }
}
