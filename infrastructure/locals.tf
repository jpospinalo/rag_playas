locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  # Nombre único del bucket: sufijo con el account ID garantiza unicidad global
  bucket_name = "${var.project}-data-${data.aws_caller_identity.current.account_id}"
}
