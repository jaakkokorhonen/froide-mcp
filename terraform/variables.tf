variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region (should match Froide Cloud Run region)"
  type        = string
  default     = "europe-north1"
}

variable "froide_service_url" {
  description = "Cloud Run service URL of the Froide instance"
  type        = string
}

variable "allowed_hd" {
  description = "Google Workspace domain to restrict SSO to (empty = any Google account)"
  type        = string
  default     = ""
}

variable "image" {
  description = "Container image URI (Artifact Registry)"
  type        = string
  default     = "europe-north1-docker.pkg.dev/YOUR_PROJECT/froide/froide-mcp:latest"
}

variable "mcp_base_url" {
  description = "Public HTTPS base URL of this MCP service, used for Google OAuth redirect_uri. Keep this in Terraform state so later applies do not remove it."
  type        = string
  default     = ""
}
