#!/bin/bash
# scripts/check_vps_connection.sh
# Verificación de conexión SSH a VM e2-micro en Google Cloud Platform

VPS_IP="${VPS_IP:-$1}"
SSH_USER="root"
SSH_KEY="~/.ssh/id_rsa_oracle"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ -z "$VPS_IP" ]]; then
    echo -e "${RED}❌ Uso: $0 <IP_PUBLICA>${NC}"
    echo -e "${YELLOW}   o export VPS_IP=<IP_PUBLICA> && $0${NC}"
    exit 1
fi

echo -e "${YELLOW}=== Verificando VM GCP: $VPS_IP ===${NC}"

echo -e "\n${YELLOW}[1/2] Probando ping...${NC}"
if ping -c 3 -W 5 "$VPS_IP" &>/dev/null; then
    echo -e "${GREEN}✅ VM responde a ping${NC}"
else
    echo -e "${RED}❌ VM no responde a ping (¿IP correcta o firewall de GCP?)"${NC}
fi

echo -e "\n${YELLOW}[2/2] Probando SSH...${NC}"
if ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$SSH_USER@$VPS_IP" "echo '✅ SSH exitoso: '$(hostname)" &>/dev/null; then
    echo -e "${GREEN}✅ Conexión SSH exitosa${NC}"
else
    echo -e "${RED}❌ Fallo SSH (verifica clave pública en GCP, IP, y que la instancia esté running)${NC}"
fi
