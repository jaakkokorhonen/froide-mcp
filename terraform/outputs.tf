output "mcp_service_url" {
  description = "Cloud Run service URL — use as MCP_BASE_URL and in Claude Desktop config"
  value       = google_cloud_run_v2_service.mcp.uri
}

output "mcp_service_account_email" {
  description = "Service account email for the MCP Cloud Run service"
  value       = google_service_account.mcp.email
}
