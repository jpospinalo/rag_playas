#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

echo "=== Inicio setup Ollama: $(date) ==="

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

# 2. Instalar Docker
apt-get ${APT_OPTS} install -y docker.io

# 3. Habilitar Docker
# --no-block evita un deadlock conocido donde systemctl start cuelga
# cuando se invoca desde dentro de cloud-final.service
systemctl enable docker
systemctl start --no-block docker

# 4. Esperar que el Docker daemon esté listo antes de correr contenedores
echo "Esperando Docker daemon..."
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "Docker listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 3
done

# 5. Crear volumen y lanzar Ollama
docker volume create ollama

docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# 6. Esperar que el servicio Ollama esté listo dentro del contenedor
echo "Esperando que Ollama este listo..."
for i in $(seq 1 30); do
  if docker exec ollama ollama list >/dev/null 2>&1; then
    echo "Ollama listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 5
done

# 7. Descargar el modelo
echo "Descargando modelo embeddinggemma..."
docker exec ollama ollama pull embeddinggemma:latest

echo "=== Setup Ollama completado: $(date) ==="
