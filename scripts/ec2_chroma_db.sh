#!/bin/bash
set -e

# Logs
exec > /var/log/user-data-chromadb.log 2>&1

echo "==== INICIO SETUP CHROMADB ===="

# 1. Actualizar sistema
apt-get update -y
apt-get upgrade -y

# 2. Paquetes útiles
apt-get install -y build-essential docker.io

# 3. Habilitar y arrancar Docker
systemctl enable docker
systemctl start docker

echo "Esperando a que Docker esté listo..."
sleep 10

# 4. Directorio persistente
mkdir -p /opt/chroma-data

# 5. Ejecutar ChromaDB
docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5

echo "==== FIN SETUP CHROMADB ===="
