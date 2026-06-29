# ── Cloud Run Service — froide-mcp ───────────────────────────────────────

resource "google_cloud_run_v2_service" "mcp" {
  name     = "froide-mcp"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.mcp.email

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # Scale to zero when idle
        cpu_idle = true
      }

      # Plain env vars
      env {
        name  = "FROIDE_BASE_URL"
        value = var.froide_service_url
      }
      env {
        name  = "ALLOWED_HD"
        value = var.allowed_hd
      }

      # Secrets from Secret Manager
      dynamic "env" {
        for_each = {
          GOOGLE_CLIENT_ID     = "froide-mcp-google-client-id"
          GOOGLE_CLIENT_SECRET = "froide-mcp-google-client-secret"
          SESSION_SECRET       = "froide-mcp-session-secret"
          FROIDE_CLIENT_ID     = "froide-mcp-froide-client-id"
          FROIDE_CLIENT_SECRET = "froide-mcp-froide-client-secret"
        }
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

      # MCP_BASE_URL is injected after first deploy (chicken-and-egg)
      # Set it manually: gcloud run services update froide-mcp --set-env-vars MCP_BASE_URL=<url>
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  # Require authentication at Cloud Run level (IAM invoker)
  # The MCP client must present a Google ID token or the session token flow
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Output the service URL so MCP_BASE_URL can be set
output "mcp_service_url" {
  value = google_cloud_run_v2_service.mcp.uri
}
