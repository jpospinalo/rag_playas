output "s3_bucket_name" {
  description = "Nombre del bucket S3 de datos (usar como S3_BUCKET_NAME en .env)"
  value       = aws_s3_bucket.data.bucket
}

output "s3_bucket_arn" {
  description = "ARN del bucket S3 de datos"
  value       = aws_s3_bucket.data.arn
}

output "chromadb_public_ip" {
  description = "IP elastica de la instancia ChromaDB"
  value       = aws_eip.chromadb.public_ip
}

output "chromadb_public_dns" {
  description = "DNS publico de la instancia ChromaDB"
  value       = aws_eip.chromadb.public_dns
}

output "chromadb_instance_id" {
  description = "ID de la instancia EC2 ChromaDB"
  value       = aws_instance.chromadb.id
}

output "ollama_public_ip" {
  description = "IP elastica de la instancia Ollama"
  value       = aws_eip.ollama.public_ip
}

output "ollama_public_dns" {
  description = "DNS publico de la instancia Ollama"
  value       = aws_eip.ollama.public_dns
}

output "ollama_instance_id" {
  description = "ID de la instancia EC2 Ollama"
  value       = aws_instance.ollama.id
}
