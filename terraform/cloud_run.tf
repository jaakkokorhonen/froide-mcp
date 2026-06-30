# ── Cloud Run service ────────────────────────────────────────────────────

locals {
  # Map from env var name to Secret Manager secret ID
  secret_env_vars = {
    GOOGLE_CLIENT_ID     = "froide-mcp-google-client-id"
    GOOGLE_CLIENT_SECRET = "froide-mcp-google-client-secret"
    SESSION_SECRET       = "froide-mcp-session-secret"
    FROIDE_CLIENT_ID     = "froide-mcp-froide-client-id"
    FROIDE_CLIENT_SECRET = "froide-mcp-froide-client-secret"
  }
}

resource "google_cloud_run_v2_service" "mcp" {
  name     = "froide-mcp"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.mcp.email

    containers {
      image = var.image

      # ── Plain env vars ──────────────────────────────────────────────────
      env {
        name  = "FROIDE_BASE_URL"
        value = var.froide_service_url
      }

      env {
        name  = "MCP_BASE_URL"
        value = var.mcp_base_url
      }

      env {
        name  = "ALLOWED_HD"
        value = var.allowed_hd
      }

      # ── Secret Manager env vars ─────────────────────────────────────────
      dynamic "env" {
        for_each = local.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # Cloud Run injects PORT automatically; the app reads it in config.py
      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  # Ensure env vars are stable — do not drift on re-apply
  lifecycle {
    ignore_changes = []
  }
}

# Make the service publicly reachable for the OAuth callback and MCP clients.
# Auth is enforced by RequireSessionMiddleware — not by IAM.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
