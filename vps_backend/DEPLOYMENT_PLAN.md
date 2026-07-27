# Plan de Despliegue — `vps_backend/`

> **Proyecto:** Rompiendo Barreras (Marcos Barbosa & Joel)
> **Stack:** FastAPI + SQLite/Postgres + Nginx + Let's Encrypt
> **Target:** VPS Ubuntu 24.04 LTS (1 vCPU, 1-2 GB RAM, $5 USD/mes)
> **Regla innegociable (spec §1.2):** el VPS **NO** almacena ni sirve MP4. Todo video va por **Bunny Stream**.

---

## 1. Inventario de Servicios

| # | Servicio | Tecnología | Estado | Bloquea producción |
|---|---|---|---|---|
| S1 | Orca Memory Bridge | FastAPI + uvicorn | ✅ Implementado (`orca_memory_bridge.py`) | Sí |
| S2 | Auth Alumnos (JWT) | python-jose | ❌ Pendiente (spec §3.1) | Sí |
| S3 | API REST pública | FastAPI | ❌ Pendiente (spec §3) | Sí |
| S4 | Persistencia SQL | SQLite (dev) / Postgres (prod) | ❌ Pendiente (spec §2) | Sí |
| S5 | Reverse proxy | Nginx | ❌ Pendiente | Sí |
| S6 | TLS | Let's Encrypt (certbot) | ❌ Pendiente | Sí |
| S7 | Email bienvenida | SMTP | ❌ Pendiente (spec §3.2) | No (puede ser manual) |
| S8 | Pagos | MP + Stripe + PayPal | ❌ Pendiente (spec §3.2) | No (cobro manual MVP) |
| S9 | Drip Content cron | PATCH endpoint + cron | ❌ Pendiente (spec §3.4) | No |

**Conclusión para MVP (Día 0):** con S1 + S5 + S6 funcionando ya se puede invitar a Orca a leer/escribir Notion. S2-S4, S7-S9 son sprints siguientes.

---

## 2. Pre-requisitos

- **VPS:** Ubuntu 24.04 LTS, 1 vCPU, 1-2 GB RAM.
- **Acceso SSH:** usuario con `sudo` (NO root directo).
- **DNS:** registro A apuntando `api.tu-dominio.com` → IP pública del VPS.
- **Puertos:** 22 (SSH), 80 (HTTP → redirige a 443), 443 (HTTPS). Todo lo demás bloqueado por UFW.
- **Archivos locales:** este repo (incluye `vps_backend/` con código + `.env.example` + `requirements.txt`).

---

## 3. Procedimiento de Despliegue (orden estricto)

### Paso 1 — Hardening básico del VPS
```bash
sudo apt update && sudo apt upgrade -y
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo adduser --system --group rbapi        # usuario de servicio, sin login
```

### Paso 2 — Instalar runtime y reverse proxy
```bash
sudo apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx
```

### Paso 3 — Desplegar código
```bash
sudo mkdir -p /opt/rbapi
sudo chown rbapi:rbapi /opt/rbapi
sudo -u rbapi git clone <REPO_URL> /opt/rbapi/repo
sudo -u rbapi cp -r /opt/rbapi/repo/vps_backend/* /opt/rbapi/
```

### Paso 4 — Crear venv e instalar dependencias
```bash
sudo -u rbapi python3.11 -m venv /opt/rbapi/venv
sudo -u rbapi /opt/rbapi/venv/bin/pip install --upgrade pip
sudo -u rbapi /opt/rbapi/venv/bin/pip install -r /opt/rbapi/requirements.txt
```

### Paso 5 — Configurar variables de entorno
```bash
sudo mkdir -p /etc/rbapi
sudo cp /opt/rbapi/.env.example /etc/rbapi/rbapi.env
sudo nano /etc/rbapi/rbapi.env        # completar valores reales
sudo chmod 0600 /etc/rbapi/rbapi.env
sudo chown rbapi:rbapi /etc/rbapi/rbapi.env
```

> **Validación obligatoria** antes de continuar: `set -a; source /etc/rbapi/rbapi.env; set +a; env | grep -E '^(OPENAI|SERVER_ADMIN)' | sed 's/=.*/=<set>/'` → deben aparecer enmascaradas.

### Paso 6 — Crear servicio systemd
Archivo `/etc/systemd/system/rbapi.service`:
```ini
[Unit]
Description=Rompiendo Barreras - Orca Memory Bridge
After=network.target

[Service]
Type=simple
User=rbapi
Group=rbapi
WorkingDirectory=/opt/rbapi
EnvironmentFile=/etc/rbapi/rbapi.env
ExecStart=/opt/rbapi/venv/bin/uvicorn orca_memory_bridge:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/rbapi

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rbapi
sudo systemctl status rbapi    # debe estar "active (running)"
```

### Paso 7 — Configurar Nginx (reverse proxy)
Archivo `/etc/nginx/sites-available/rbapi`:
```nginx
server {
    listen 80;
    server_name api.tu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Regla innegociable: solo origins permitidos (spec §1.3)
        if ($http_origin !~* "^(https://tu-dominio.com|https://app.tu-dominio.com)$") {
            return 403;
        }
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/rbapi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Paso 8 — Habilitar TLS
```bash
sudo certbot --nginx -d api.tu-dominio.com
# certbot auto-renueva vía timer systemd; verificar con:
sudo systemctl list-timers | grep certbot
```

### Paso 9 — (FUTURO) Inicializar base de datos
```bash
# Cuando exista alembic/ en el repo:
cd /opt/rbapi && /opt/rbapi/venv/bin/alembic upgrade head
```

### Paso 10 — Smoke test
```bash
# 1. Endpoint público responde:
curl -I https://api.tu-dominio.com/docs

# 2. Endpoint admin rechaza sin token:
curl -i https://api.tu-dominio.com/api/v1/orca/memory   # debe dar 401

# 3. Endpoint admin acepta con token:
curl -H "Authorization: Bearer $SERVER_ADMIN_SECRET" https://api.tu-dominio.com/api/v1/orca/memory
```

---

## 4. Checklist de Variables de Entorno

> **Total: 31 variables** (26 en este checklist + 5 en Bunny Stream seccion F, organizadas por dominio).
> Marcar con [x] cada una antes de pasar a producción.
> Plantilla en `vps_backend/.env.example`. Reales en `/etc/rbapi/rbapi.env` (permisos 0600).

### A. [ACTUAL] — Requeridas por el código presente (bloquean arranque)

| # | Variable | Propósito | Usado en | Estado |
|---|---|---|---|---|
| 1 | `OPENAI_API_KEY` | API key OpenAI para `gpt-4o` + `gpt-4o-mini` | `memory_manager.py:16` | ☐ |
| 2 | `SERVER_ADMIN_SECRET` | Bearer token para endpoints `/api/v1/orca/*` | `orca_memory_bridge.py:17` | ☐ |
| 3 | `APP_HOST` | Bind uvicorn (default `127.0.0.1`) | systemd ExecStart | ☐ |
| 4 | `APP_PORT` | Puerto uvicorn (default `8000`) | systemd ExecStart | ☐ |
| 5 | `APP_ENV` | `development` \| `production` | lógica condicional | ☐ |
| 6 | `DOMAIN` | Dominio público (URLs absolutas) | emails + CORS | ☐ |
| 7 | `ALLOWED_ORIGINS` | CSV de orígenes CORS permitidos | Nginx + FastAPI CORS | ☐ |
| 8 | `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | uvicorn + app | ☐ |

### B. [FUTURO §3.1] — Auth JWT alumnos

| # | Variable | Propósito | Estado |
|---|---|---|---|
| 9 | `JWT_SECRET` | Secret de firma (≠ SERVER_ADMIN_SECRET) | ☐ |
| 10 | `JWT_ALGORITHM` | Algoritmo (`HS256` recomendado) | ☐ |
| 11 | `JWT_EXPIRATION_HOURS` | TTL del token de sesión | ☐ |

### C. [FUTURO §2] — Base de datos SQL

| # | Variable | Propósito | Estado |
|---|---|---|---|
| 12 | `DATABASE_URL` | `sqlite:///./rompiendo_barreras.db` o Postgres URL | ☐ |
| 13 | `DB_POOL_SIZE` | Conexiones simultáneas (Postgres) | ☐ |
| 14 | `DB_MAX_OVERFLOW` | Conexiones extra bajo carga | ☐ |

### D. [FUTURO §3.2] — Email transaccional

| # | Variable | Propósito | Estado |
|---|---|---|---|
| 15 | `SMTP_HOST` | Host SMTP | ☐ |
| 16 | `SMTP_PORT` | Puerto SMTP | ☐ |
| 17 | `SMTP_USERNAME` | Usuario SMTP | ☐ |
| 18 | `SMTP_PASSWORD` | App Password (no la contraseña real) | ☐ |
| 19 | `SMTP_USE_TLS` | `true` para STARTTLS (recomendado) | ☐ |
| 20 | `SMTP_FROM_EMAIL` | From del email | ☐ |
| 21 | `SMTP_FROM_NAME` | Nombre legible del remitente | ☐ |

### E. [FUTURO] — Pasarelas de pago

| # | Variable | Pasarela | Estado |
|---|---|---|---|
| 22 | `MERCADOPAGO_ACCESS_TOKEN` | MercadoPago (AR) | ☐ |
| 23 | `STRIPE_SECRET_KEY` | Stripe (internacional) | ☐ |
| 24 | `STRIPE_WEBHOOK_SECRET` | Validación de webhooks Stripe | ☐ |
| 25 | `PAYPAL_CLIENT_ID` | PayPal client ID | ☐ |
| 26 | `PAYPAL_CLIENT_SECRET` | PayPal secret | ☐ |
| 27 | `PAYPAL_MODE` | `sandbox` \| `live` | ☐ |

### F. [FUTURO] — Bunny Stream (metadata y firmado de URLs)

| # | Variable | Propósito | Estado |
|---|---|---|---|
| 28 | `BUNNY_STREAM_API_KEY` | API key de la cuenta Bunny | ☐ |
| 29 | `BUNNY_STREAM_LIBRARY_ID` | ID de la librería de videos | ☐ |
| 30 | `BUNNY_STREAM_TOKEN_AUTH_KEY` | Key para firmar URLs temporales | ☐ |

### G. [FUTURO §3.4] — Drip content cron

| # | Variable | Propósito | Estado |
|---|---|---|---|
| 31 | `DRIP_CRON_SECRET` | Validación del cron semanal que libera pilares | ☐ |

### G. Archivos de datos (no son env vars pero deben coexistir)

| Archivo | Propósito | Estado |
|---|---|---|
| `agent_scratchpad.json` | Estado dinámico (Level 2 memory) | ☐ |
| `rompiendo_barreras_master_context.md` | Knowledge base (Level 1 memory) | ☐ |
| `manifests/notion_databases_manifest.json` | IDs de las 4 DBs Notion | ☐ |
| `config/prompts_agentes_orca.md` | System prompts de los 4 agentes | ☐ |
| `config/system_prompt_orquestador.md` | Preamble del orquestador | ☐ |

---

## 5. Health Checks post-deploy

```bash
# Liveness del proceso
sudo systemctl is-active rbapi

# Endpoint público (debe devolver 200 con HTML de Swagger)
curl -fsS https://api.tu-dominio.com/docs | head -5

# Endpoint admin sin token (debe devolver 401)
curl -s -o /dev/null -w "%{http_code}\n" https://api.tu-dominio.com/api/v1/orca/memory

# Endpoint admin con token (debe devolver 200 + JSON)
curl -s -H "Authorization: Bearer $SERVER_ADMIN_SECRET" https://api.tu-dominio.com/api/v1/orca/memory

# TLS válido
echo | openssl s_client -connect api.tu-dominio.com:443 -servername api.tu-dominio.com 2>/dev/null | openssl x509 -noout -dates

# Disco (regla: nunca almacenar video en el VPS)
du -sh /opt/rbapi/* 2>/dev/null
```

---

## 6. Procedimiento de Rollback

| Escenario | Acción |
|---|---|
| Servicio caído | `sudo systemctl restart rbapi` → si sigue caído, `journalctl -u rbapi -n 100` |
| Deploy con bug | `sudo systemctl stop rbapi` → restaurar backup `/opt/rbapi.bak` → `start` |
| Cert TLS vence | `sudo certbot renew` (auto vía timer, verificar con `--dry-run`) |
| Compromiso de secret | rotar `SERVER_ADMIN_SECRET` en `/etc/rbapi/rbapi.env` → `sudo systemctl restart rbapi` |
| Disco lleno | `df -h`; los logs de uvicorn no deben persistir (usar `journalctl` + logrotate) |

---

## 7. Mapa de archivos del backend

```
vps_backend/
├── DEPLOYMENT_PLAN.md              ← este archivo
├── requirements.txt                 ← deps Python
├── .env.example                     ← plantilla env vars (NO commitear el .env real)
├── agent_scratchpad.json            ← estado dinámico en runtime
├── memory_manager.py                ← gestor memoria jerárquica (Nivel 1 + 2)
├── orca_memory_bridge.py            ← FastAPI: POST /execute, GET /memory
├── rompiendo_barreras_master_context.md  ← knowledge base central
└── vps_backend_spec.md              ← spec autoritativa (no generada por IA)
```

> **Nota de phasing:** el plan anterior cubre S1 (Orca bridge) + S5 (Nginx) + S6 (TLS), que es **suficiente para el MVP del Día 0**. Los servicios S2-S4, S7-S9 son sprints posteriores y ya están provisionados en `.env.example` y `requirements.txt` para que crezcan sin refactors.