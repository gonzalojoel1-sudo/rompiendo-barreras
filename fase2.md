# 🚀 Plan Maestro de Despliegue 24/7: VPS en Google Cloud Platform (Fase 2)

## [✅ FASE 2 OFICIALMENTE CERRADA Y DESPLEGADA]

## 📌 Objetivo del Documento
Desplegar la infraestructura de "Squad con Contexto Total" (FastAPI + Búnker + Webhook + Agentes) en una VM e2-micro de Google Cloud Platform (2 vCPUs, 1 GB RAM, Debian/Ubuntu). El sistema funcionará 24/7/365 en segundo plano, protegido con SSL/HTTPS y procesando peticiones de Notion de forma Autónoma con la computadora local apagada.

---

## 🏗️ 1. Arquitectura de Despliegue en Producción [✅ COMPLETADO]

- ✅ Construcción local del contenedor funcionando sin errores
- ✅ Puertos mapeados: ./envs local → contenedor
- ✅ `context_vault:/app/context_vault:ro` montado para lectura
- ✅ `./logs:/app/logs` montado para persistencia
- ✅ Reinicio configurado: `unless-stopped`
- ✅ .dockerignore aplicando patrones correctos
- ✅ Variables de entorno desde .env (PYTHONUNBUFFERED=1, PYTHONDONTWRITEBYTECODE=1)
- ✅ Puerto expuesto: 8765
- ✅ Debug/healthcheck funcional
- ✅ Usuario no-root obtenido: `appuser:appuser`
- ✅ Renombrado `notion_bridge/` → `rb_notion_bridge/` para evitar namespace shadow

## 🔧 2. Aprovisionamiento de VM e2-micro en Google Cloud Platform [✅ COMPLETADO]

- ✅ Script `scripts/setup_gcp_server.sh` creado para setup inicial del servidor
- ✅ Swap File de 2 GB configurado en la VM
- ✅ Docker y Docker Compose instalados automáticamente
- ✅ Script `scripts/check_vps_connection.sh` adaptado para GCP
- ✅ OS Login configurado con clave pública SSH ED25519

## 🚀 3. Despliegue del Backend con Docker Compose [✅ COMPLETADO]

- ✅ Código empaquetado en `/tmp/rb_deploy.tar.gz` (127 KB)
- ✅ Transferencia SCP a VM GCP: `136.111.55.189`
- ✅ Descompresión en `/home/gonzalojoel1_gmail_com/rompiendo-barreras`
- ✅ `docker compose up -d --build` ejecutado
- ✅ Healthcheck HTTP 200 verificado

## 🔒 4. Hardening y SSL/HTTPS [✅ COMPLETADO]

- ✅ **Caddy Server v2.11.4** instalado (no nginx, más rápido y automático)
- ✅ **Caddyfile** configurado para `136.111.55.189.sslip.io` con reverse proxy a `127.0.0.1:8765`
- ✅ **Certificado TLS automático** de Let's Encrypt obtenido vía ACME
- ✅ **HTTP/2 habilitado** con TLS 1.3 (cipher: TLS_AES_128_GCM_SHA256)
- ✅ Headers `via: 1.1 Caddy`, `alt-svc: h3=":443"`
- ✅ Servicio systemd `caddy.service` habilitado en boot
- ✅ Logs estructurados JSON en `/var/log/caddy/access.log`

## 🔗 5. Integración de Webhooks en Notion y Prueba E2E [✅ COMPLETADO]

### URL HTTPS definitiva para Webhook:
```
https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger
```

### Header de autenticación:
```
X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa
```

### Acciones soportadas por el endpoint:
| Acción          | Descripción                                               |
|-----------------|-----------------------------------------------------------|
| `hydrate`       | Carga estado de Notion al scratchpad (1.68s respuesta)   |
| `flush`         | Drena cola de sincronización (0.56s respuesta)            |
| `sync_event`    | Procesa payload como evento (requiere `event_type`)      |
| `process_approved` | Dispara pipeline completo en background              |

### Pruebas E2E ejecutadas (TODAS PASARON):

| # | Test                                  | Código | Tiempo  |
|---|---------------------------------------|--------|---------|
| 1 | GET `/health` (HTTPS, sin auth)       | 200    | 1.91s   |
| 2 | POST `/api/v1/orca/webhook/trigger` (hydrate) | 200 | 1.68s   |
| 3 | POST `/api/v1/orca/webhook/trigger` (flush)   | 200 | 0.56s   |
| 4 | POST con X-Orca-API-Key incorrecta    | 401    | -       |

### Respuesta de prueba `hydrate`:
```json
{
  "status": "ok",
  "action": "hydrate",
  "detail": "Hidratado desde 1 database(s).",
  "result": {
    "databases": ["Tareas"],
    "counts": {"Tareas": 0}
  }
}
```

### Logs en vivo — Comando de monitoreo:
```bash
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189 \
  "cd /home/gonzalojoel1_gmail_com/rompiendo-barreras && docker compose logs -f rb_vps_backend"
```

### Configuración del Webhook en Notion (guía):
1. **Notion → Settings → Integrations** → tu integración existente (o crear nueva)
2. **Capabilities:** activar "Read content", "Update content", "Read user info"
3. **OAuth Domain / Redirect URI:** `https://136.111.55.189.sslip.io`
4. **Database Triggers (Automations):**
   - **Trigger:** "When a page is added or updated" en la DB correspondiente
   - **Action:** "Send webhook"
   - **URL:** `https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger`
   - **Custom headers:** `X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa`
   - **Body (JSON):**
     ```json
     {
       "action": "process_approved",
       "payload": {
         "page_ids": ["{{event.page_id}}"],
         "event_type": "page.updated"
       }
     }
     ```
5. **Persistir** y probar con un cambio manual en una página del Búnker.

---

## 🌐 URLs DEFINITIVAS

| Protocolo       | URL                                                       | Uso                  |
|------------------|-----------------------------------------------------------|----------------------|
| **HTTPS Webhook**| `https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger` | Webhook Notion      |
| HTTPS Health     | `https://136.111.55.189.sslip.io/health`                  | Monitoreo            |
| HTTPS Root       | `https://136.111.55.189.sslip.io/`                        | OpenAPI docs         |
| HTTP local       | `http://localhost:8765`                                   | Debug interno        |

---

## 🎯 Resumen Final Fase 2

### Stack desplegado:
- **OS:** Debian 13 (Trixie) en GCP e2-micro (1 GB RAM + 2 GB Swap)
- **Backend:** FastAPI + uvicorn en Docker, usuario no-root `appuser:appuser`
- **Reverse Proxy:** Caddy v2.11.4 con auto-TLS Let's Encrypt
- **Persistencia:** Volumen `vps_data` montado en `/app/data`
- **Healthcheck:** HTTP 200 con `status:ok`, Notion reachable ✅
- **Webhook endpoint:** POST `/api/v1/orca/webhook/trigger` validado con 4 pruebas E2E ✅

### Métricas finales (Fase 2 cerrada):
- Build Docker: ✅ sin errores
- Container: ✅ healthy
- HTTPS: ✅ HTTP/2 + TLS 1.3 funcionando
- Caddy uptime: ✅ systemd enabled
- E2E webhook: ✅ 4/4 pruebas exitosas (incluyendo 401 por auth inválida)

[✅ FASE 2 OFICIALMENTE CERRADA Y DESPLEGADA]
