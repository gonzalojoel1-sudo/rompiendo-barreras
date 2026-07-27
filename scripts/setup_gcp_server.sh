#!/bin/bash
# scripts/setup_gcp_server.sh
# Setup inicial para VM e2-micro en Google Cloud Platform
# Ejecutar ESTE SCRIPT dentro de la VM de GCP (conexión SSH previa)

set -e

echo "=========================================="
echo "  Setup Inicial - VM e2-micro GCP"
echo "=========================================="

# ---- 1. Actualizar sistema ----
echo -e "\n[1/6] Actualizando sistema..."
apt update && apt upgrade -y

# ---- 2. Crear Swap File de 2 GB ----
echo -e "\n[2/6] Creando Swap File de 2 GB..."
if [[ -f /swapfile ]]; then
    echo "Swap file ya existe, saltando..."
else
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap file creado y habilitado"
fi

# ---- 3. Instalar Docker ----
echo -e "\n[3/6] Instalando Docker..."
if command -v docker &>/dev/null; then
    echo "Docker ya instalado, saltando..."
else
    apt install -y ca-certificates curl gnupg lsb-release
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    apt update
    apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    echo "Docker instalado"
fi

# ---- 4. Instalar Docker Compose ----
echo -e "\n[4/6] Verificando Docker Compose..."
if docker compose version &>/dev/null; then
    echo "Docker Compose Plugin ya disponible"
else
    apt install -y docker-compose
fi

# ---- 5. Configurar UFW (firewall) ----
echo -e "\n[5/6] Configurando firewall UFW..."
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 8765/tcp comment 'Backend API'
ufw --force enable
ufw status verbose

# ---- 6. Verificación final ----
echo -e "\n[6/6] Verificación final..."
echo "--- Memoria y Swap ---"
free -h
echo ""
echo "--- Docker ---"
docker --version
docker compose version
echo ""
echo "--- Firewall ---"
ufw status

echo -e "\n=========================================="
echo "  ✅ Setup completado"
echo "  Ejecuta: docker --version && docker compose version"
echo "=========================================="
