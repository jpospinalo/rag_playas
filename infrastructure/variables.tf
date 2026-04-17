variable "project" {
  description = "Nombre del proyecto, usado en nombres y tags de recursos"
  type        = string
  default     = "rag-playas"
}

variable "environment" {
  description = "Entorno de despliegue"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "El entorno debe ser dev, staging o prod."
  }
}

variable "key_pair_name" {
  description = "Nombre del key pair de AWS existente para acceso SSH"
  type        = string
  default     = "vockey"
}
