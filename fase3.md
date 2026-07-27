# 🚀 Plan Maestro de Operación en Producción: Integración Notion, Webhooks y Célula de Agentes (Fase 3)

## 📌 Objetivo del Documento
Escribir y ejecutar la hoja de ruta operativa de la **Fase 3**. Esta fase conecta el Workspace de Notion con el backend desplegado en Google Cloud Platform (`136.111.55.189.sslip.io`), activando el procesamiento desatendido en tiempo real. Cada vez que una tarjeta se apruebe o actualice en Notion, el servidor disparará la Célula de Agentes, consultará el Búnker de Contexto, ejecutará el Loop de Calidad (9/10+) y devolverá el resultado a Notion de forma 100% Autónoma.

---

## 🏗️ 1. Arquitectura del Flujo en Producción (E2E)

```
Notion (Trigger)
   │
   ▼ POST (HTTPS + X-Orca-API-Key)
Caddy :443  ─── TLS 1.3 (Let's Encrypt sslip.io)
   │
   ▼ reverse_proxy
FastAPI :8765  ─── /api/v1/orca/webhook/trigger
   │
   ▼ action: process_approved
Orca Orchestrator (Background Task)
   │
   ├─→ Trend Hunter   (DeepSeek v4 Flash)
   ├─→ Strategist     (MiniMax-M3)
   ├─→ Copywriter     (Claude Sonnet 4.5)
   └─→ Brand QA       (Gemini Flash)
        │
        ▼ score >= 9/10?
   SyncManager → Notion API (update page)
```

---

## 📋 PASOS DE LA FASE 3

### Paso 1 — Vinculación de Automaciones en Notion [✅ COMPLETADO]

**Objetivo:** Registrar la regla en Notion Automations que dispare el webhook al endpoint productivo.

**Datos de producción:**

| Campo | Valor |
|-------|-------|
| **URL** | `https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger` |
| **Método** | `POST` |
| **Custom Header** | `X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa` |
| **Content-Type** | `application/json` |
| **Body** | Ver JSON abajo |

**Body JSON:**
```json
{
  "action": "process_approved",
  "payload": {
    "page_ids": ["{{event.page_id}}"],
    "event_type": "page.updated"
  }
}
```

**Pasos en Notion:**
1. **Notion → Workspace Settings → Connections → Develop your own integrations** → abrir/crear integración
2. **Capabilities:** `Read content`, `Update content`, `Read user info`
3. **En la base de datos del Búnker** (ej: "Tareas") → click en los `•••` → `+ Add connections` → seleccionar la integración
4. **Crear Automation en Notion:**
   - **Trigger:** "When status is Aprobado"
   - **Action:** "Send webhook"
   - Pegar URL, header y body de arriba
5. **Save** la automation

**Validación de conectividad:** ✅ Verificada con `curl https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger`

### Paso 2 — Ingesta / Hidratación desde Notion [✅ COMPLETADO]

**Objetivo:** Cargar el estado completo de la DB "Tareas" al scratchpad del backend.

**Validación ejecutada:**
```bash
curl -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger \
  -H "X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa" \
  -H "Content-Type: application/json" \
  -d '{"action":"hydrate","payload":{}}'
```

**Salida real:**
```json
{
  "status": "ok",
  "action": "hydrate",
  "detail": "Hidratado desde 1 database(s).",
  "result": {"databases":["Tareas"],"counts":{"Tareas":0}}
}
```

**Eventos reales validados con `action: process_approved`:**
- ✅ Caddy recibe HTTPS POST (TLS 1.3)
- ✅ FastAPI valida header `X-Orca-API-Key`
- ✅ Backend activa `BackgroundTask` (`status:processing`)
- ✅ El script `run_hybrid_squad.py` arranca en background
- ✅ Pipeline conecta a Notion API real (verifica "Status options ya presentes")
- ✅ Reporta "No hay paginas en estado 'Aprobado'. Finalizando limpiamente."

**Issues encontrados y corregidos durante validación:**
1. `notion_bridge` → renombrado a `rb_notion_bridge` (conflicto namespace)
2. `.dockerignore` excluía `scripts/` → corregido
3. `Dockerfile` faltaba `COPY scripts` y `COPY config` → agregados
4. Permisos `/app/logs` (bind mount root) → bind mount explícito en compose
5. Cache de Docker con build fantasma → resuelto con `docker build` directo

**Comando de logs en vivo (Post-Paso 2):**
```bash
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189 \
  "tail -f /home/gonzalojoel1_gmail_com/rompiendo-barreras/logs/pipeline_process_approved.log"
```

### Paso 3 — Pipeline LLMs (Célula de Agentes) [⏳ PENDIENTE]

**Objetivo:** Ejecutar la Célula de Agentes (Trend Hunter → Strategist → Copywriter → Brand QA) sobre la tarjeta aprobada.

**Trigger:** `action: process_approved` con `page_ids: [...]`.

**Comando de prueba local (4 agentes):**
```bash
curl -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger \
  -H "X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa" \
  -H "Content-Type: application/json" \
  -d '{"action":"process_approved","payload":{"page_ids":["abc-123-def"]}}'
```

### Paso 4 — Loop QA 9/10+ (Gate de Calidad) [⏳ PENDIENTE]

**Objetivo:** Si Brand QA puntúa < 9/10, regenerar vía Copywriter hasta alcanzar umbral.

**Configuración esperada en `.env`:**
```bash
BRAND_QA_MIN_SCORE=9.0
MAX_REGENERATION_LOOPS=3
```

### Paso 5 — Sincronización Final con Notion [⏳ PENDIENTE]

**Objetivo:** Volcar el contenido aprobado al campo "Contenido Final" de la tarjeta en Notion.

**Sincronización bidireccional automática.** No requiere acción manual.

### Paso 6 — Monitoreo 24/7 y Operación Autónoma [⏳ PENDIENTE]

**Objetivo:** Confirmar que el sistema funciona desatendido con la laptop apagada.

**Comandos de monitoreo:**
```bash
# Logs en vivo
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189 \
  "cd /home/gonzalojoel1_gmail_com/rompiendo-barreras && docker compose logs -f rb_vps_backend"

# Healthcheck periódico
watch -n 30 "curl -s https://136.111.55.189.sslip.io/health | jq .status"

# Estado del contenedor
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189 \
  "docker ps --filter name=rb_vps_backend --format 'table {{.Names}}\t{{.Status}}'"
```

---

## 🔧 Comandos Rápidos (cheat sheet)

```bash
# SSH a la VM
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189

# Test webhook
curl -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger \
  -H "X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa" \
  -H "Content-Type: application/json" \
  -d '{"action":"hydrate","payload":{}}'

# Logs en vivo
cd ~/rompiendo-barreras && docker compose logs -f rb_vps_backend

# Estado
docker ps && curl -s https://136.111.55.189.sslip.io/health
```

---

## 📌 Estado Global

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Vinculación Automations Notion | ✅ COMPLETADO |
| 2 | Ingesta / Hidratación | ⏳ PENDIENTE |
| 3 | Pipeline LLMs | ⏳ PENDIENTE |
| 4 | Loop QA 9/10+ | ⏳ PENDIENTE |
| 5 | Sincronización Final | ⏳ PENDIENTE |
| 6 | Monitoreo 24/7 | ⏳ PENDIENTE |

