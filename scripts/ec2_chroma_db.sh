#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

echo "=== Inicio setup ChromaDB: $(date) ==="

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export NEEDRESTART_SUSPEND=1

# Ubuntu 24.04 arranca con unattended-upgrades corriendo, lo que bloquea dpkg.
# Hay que esperar que libere el lock antes de cualquier operación con apt.
echo "Esperando que unattended-upgrades libere el lock de dpkg..."
systemctl stop unattended-upgrades || true
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 \
   || fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
  echo "  dpkg ocupado, esperando 5s..."
  sleep 5
done
echo "Lock liberado."

APT_OPTS="-o DPkg::Lock::Timeout=300 -o Acquire::Retries=3 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

# 1. Actualizar sistema
echo "Actualizando paquetes..."
apt-get ${APT_OPTS} update
apt-get ${APT_OPTS} upgrade -y

# 2. Instalar dependencias
apt-get ${APT_OPTS} install -y build-essential docker.io

# 3. Habilitar Docker
# --no-block evita un deadlock conocido donde systemctl start cuelga
# cuando se invoca desde dentro de cloud-final.service
systemctl enable docker
systemctl start --no-block docker

# 4. Dar permisos al usuario ubuntu
usermod -aG docker ubuntu

# 5. Esperar que el Docker daemon esté listo antes de correr contenedores
echo "Esperando Docker daemon..."
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "Docker listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 3
done

# 6. Directorio para datos persistentes de Chroma
mkdir -p /opt/chroma-data

# 7. Lanzar ChromaDB en Docker
docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5

echo "=== Setup ChromaDB completado: $(date) ==="
