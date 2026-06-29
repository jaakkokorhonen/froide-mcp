terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Mirror your froide-infra backend config here
  backend "gcs" {
    bucket = "YOUR_TF_STATE_BUCKET"
    prefix = "froide-mcp/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
