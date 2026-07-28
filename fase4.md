# 🔧 Plan Maestro de Corrección y Estabilización (Fase 4)

## 📌 Objetivo del Documento
Documentar TODOS los issues identificados durante la auditoría integral del proyecto y la sesión anterior. Esta fase corrige los errores bloqueantes, elimina código duplicado, endurece la seguridad y deja el sistema listo para operación 24/7 confiable.

---

## 🏗️ 1. Arquitectura de Issues por Categoría

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    🔒 SEGURIDAD (Critical/HIGH)                        │
│   - Credentials hardcodeadas en 4+ scripts + TASKS.md                  │
│   - Command injection en telegram_bot                                  │
│   - Default API keys inseguros en prod                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                    🐛 BUGS CRÍTICOS DE CÓDIGO                          │
│   - run_hybrid_squad.py: properties vacías (código unreachable)       │
│   - tools.py: iteration indefinida (NameError)                         │
│   - memory_manager.py: json.loads sin validación (crash)               │
├─────────────────────────────────────────────────────────────────────────┤
│                    🔄 PIPELINE Y QUALITY GATES                         │
│   - Bug 1: prompt nunca testeado (guiones 4x más largos)              │
│   - Brand Guardian falla (score 6/10)                                  │
│   - Few-shot examples faltantes                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                    🧹 LIMPIEZA Y DUPLICACIÓN                           │
│   - notion_bridge vs rb_notion_bridge (99% idéntico)                  │
│   - Documentación desactualizada (fase3.md, TASKS.md)                  │
│   - Scripts huérfanos y obsoletos                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 PASOS DE LA FASE 4

### Paso 1 — Remover Credenciales Hardcodeadas [🔴 CRÍTICO]

**Objetivo:** Eliminar todos los tokens, API keys y secrets del código y documentación.

#### 1.1 Tokens de Notion hardcodeados (4 scripts)

**Archivos afectados:**
| Archivo | Línea | Valor hardcodeado |
|---------|-------|-------------------|
| `scripts/integration_test_e2e.py` | 25 | `ntn_REDACTED_LEAK_2026-07-28` |
| `scripts/publish_mvp_content.py` | 22-25 | fallback hardcodeado |
| `scripts/update_notion_styling.py` | 32-35 | fallback hardcodeado |
| `scripts/build_notion_databases.py` | 22 | `ntn_REDACTED_LEAK_2026-07-28` |

**Fix:** Reemplazar todos por:
```python
import os
NOTION_TOKEN = os.getenv("NOTION_API_KEY")
if not NOTION_TOKEN:
    raise ValueError("NOTION_API_KEY env var required")
```

#### 1.2 Secrets en TASKS.md

**Archivo:** `TASKS.md:líneas 241-250`

**Valores expuestos:**
```
Notion API: ntn_REDACTED_LEAK_2026-07-28
MiniMax API: sk-cp_REDACTED_LEAK_2026-07-28
Telegram bot token: REDACTED_LEAK_2026-07-28_TELEGRAM
Vertex service account: cs-project_REDACTED_LEAK_2026-07-28
```

**Fix:** Mover a `secrets/SECRETS.md` (agregar a .gitignore) con contenido:
```markdown
# NO COMMITEAR — Solo para referencia local
NOTION_API_KEY=ntn_REDACTED_LEAK_2026-07-28
MINIMAX_API_KEY=sk-cp_REDACTED_LEAK_2026-07-28
TELEGRAM_BOT_TOKEN=REDACTED_LEAK_2026-07-28_TELEGRAM
VERTEX_SERVICE_ACCOUNT=cs-project_REDACTED_LEAK_2026-07-28
```
En TASKS.md, reemplazar tabla por:
```
| Recurso | Ubicación |
|---|---|
| Notion API | `secrets/SECRETS.md` |
| MiniMax API | `secrets/SECRETS.md` |
| Telegram bot token | `secrets/SECRETS.md` |
```

#### 1.3 Default API Key inseguro en orca_memory_bridge

**Archivo:** `vps_backend/orca_memory_bridge.py:línea 65`

**Código actual:**
```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "tu_openai_api_key_aqui")
```

**Fix:**
```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")
```

#### 1.4 IP/URL hardcodeada en telegram_bot

**Archivo:** `vps_backend/telegram_bot.py:líneas 66-69`

**Código actual:**
```python
GUIÓN_TRIGGER_URL = os.getenv(
    "WEBHOOK_TRIGGER_URL",
    "https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger",
).strip()
```

**Fix:** Eliminar el fallback. Requerir que `WEBHOOK_TRIGGER_URL` esté siempre en `.env`.

#### 1.5 PAGE_IDs y DB_IDs hardcodeados

**Archivos afectados:**
| Archivo | Línea | ID |
|---------|-------|-----|
| `scripts/update_notion_styling.py` | 38 | `3a8cfb86-8e33-80e6-999a-df277c673dbc` |
| `scripts/build_notion_databases.py` | 23 | `3a8cfb868e33...` (typo: `8e3380e6` vs `8e33-80e6`) |
| `vps_backend/telegram_bot.py` | 65 | `3aacfb86-8e33-8154-8cfe-e473b3f48aae` |

**Fix:** Mover todos a `manifests/notion_databases_manifest.json` y leer desde ahí.

---

### Paso 2 — Corregir Bugs Críticos de Código [🔴 CRÍTICO]

**Objetivo:** Arreglar los bugs que causan fallos en runtime o comportamiento incorrecto.

#### 2.1 BUG-CRÍTICO: Código unreachable en run_hybrid_squad.py (properties vacías)

**Archivo:** `scripts/run_hybrid_squad.py:líneas 1262-1270`

**Problema:** Variables redeclaradas hacen que `properties` siempre quede vacío `{}`. Todas las páginas se crean en Notion sin título ni propiedades.

```python
# LÍNEA 1262 (correcta)
db_id = manifest[target]
properties: dict[str, Any] = {}

# LÍNEAS 1265-1267 (DUPLICADAS / SHADOWED)
target = idea.get("target_db", "db_M0")   # shadow
db_id = manifest[target]                  # sobreescribe
properties: dict[str, Any] = {}           # sobreescribe → vacío
# ... código que asigna a properties NUNCA se ejecuta
```

**Fix:** Eliminar líneas 1265-1267 duplicadas.

#### 2.2 BUG: `iteration` indefinida en tools.py

**Archivo:** `vps_backend/tools.py:línea 494`

**Código:**
```python
"id": f"fc_{iteration}_{i}",  # iteration nunca definida
```

**Fix:** Cambiar a:
```python
"id": f"fc_{fc_index}_{i}",
```
Donde `fc_index` viene del enumerate del loop externo.

#### 2.3 BUG: json.loads sin validación en memory_manager.py

**Archivo:** `vps_backend/memory_manager.py:línea 205`

**Código:**
```python
updated = json.loads(res.choices[0].message.content)
self.scratchpad = updated  # si LLM devuelve no-JSON, crashea
```

**Fix:**
```python
try:
    updated = json.loads(res.choices[0].message.content)
    required_keys = {"proyecto", "fase_actual", "decisiones_clave"}
    if isinstance(updated, dict) and required_keys.issubset(updated.keys()):
        self.scratchpad = updated
    else:
        logger.warning("auto_compact: schema inesperado, manteniendo estado anterior")
except json.JSONDecodeError as exc:
    logger.warning("auto_compact: JSON inválido del LLM, err=%s", exc)
```

#### 2.4 BUG: Auth relajada en modo dev (telegram_bot)

**Archivo:** `vps_backend/telegram_bot.py:líneas 78-80`

**Código:**
```python
def _is_authorized(update: Any) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True  # Permite TODO si no hay whitelist
```

**Fix:** En producción, fallar si `ALLOWED_CHAT_IDS` está vacío:
```python
def _is_authorized(update: Any) -> bool:
    if not ALLOWED_CHAT_IDS:
        log.error("TELEGRAM_ALLOWED_CHAT_IDS no configurado - rechazando request")
        return False
```

#### 2.5 BUG: Command injection en run_ideate

**Archivo:** `vps_backend/telegram_bot.py:líneas 99-107`

**Código:**
```python
cmd = [
    "python3",
    str(ORCHESTRATOR_SCRIPT),
    "--mode=ideate",
    f"--topic={topic}",  # topic SIN sanitizar
]
proc = subprocess.run(cmd, ...)
```

**Fix:** Sanitizar topic:
```python
import re
SANITIZED_TOPIC = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ,.:;!?¡¿\-_()]", "", topic)
if not SANITIZED_TOPIC.strip():
    return 1, "", "Topic inválido"
cmd = [
    "python3",
    str(ORCHESTRATOR_SCRIPT),
    "--mode=ideate",
    f"--topic={SANITIZED_TOPIC}",
]
```

#### 2.6 BUG: Comparación con `is not` en sync_manager.py

**Archivo:** `vps_backend/sync_manager.py:línea 120`

**Código:**
```python
self.scratchpad["notion_sync_pending"] = [
    e for e in pending if e is not event  # Comparación de identidad
]
```

**Problema:** Si el evento se serializó a JSON y restauró, `is not` siempre será True aunque sea el mismo evento lógicamente.

**Fix:**
```python
self.scratchpad["notion_sync_pending"] = [
    e for e in pending
    if not (e.get("type") == event.get("type") and e.get("payload") == event.get("payload"))
]
```

#### 2.7 BUG: Path hardcodeado de Joel en run_hybrid_squad.py

**Archivo:** `scripts/run_hybrid_squad.py:líneas 1183-1184`

**Código:**
```python
if "/Users/joelpacheco/PROYECTOS/rompiendo-barreras/vps_backend" not in sys.path:
    sys.path.insert(0, "/Users/joelpacheco/PROYECTOS/rompiendo-barreras/vps_backend")
```

**Fix:** Usar path relativo:
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "vps_backend"))
```

---

### Paso 3 — Testear y Corregir Pipeline de Agentes [🟡 IMPORTANTE]

**Objetivo:** DeBug 1 y mejorar quality gates.

#### 3.1 BUG-01 (TASKS.md): Prompt con reglas de duración/versículo NUNCA testeado

**Archivo:** `config/system_prompts_squad.py`

**Cambios en el prompt (ya hechos, pero nunca probados):**
- Regla de duración EXACTA: `palabras = duración_min * ppm_objetivo` (250 ppm video corto, 280 ppm clase Pilar)
- Regla del versículo: "USÁ el del archivo, NO elijas libre"

**Pasos para validar:**
```bash
# 1. Rebuild imagen Docker
docker build -t rb_vps_backend:latest . --no-cache

# 2. Restart container
docker rm -f rb_vps_backend && docker run -d --name rb_vps_backend ...

# 3. Aprobar una idea en db_M0 (cambiar a "📝 Guion Aprobado")

# 4. Disparar pipeline
curl -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger \
  -H "X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa" \
  -H "Content-Type: application/json" \
  -d '{"action":"process_approved","payload":{"page_ids":["3aacfb86-8e33-81a2-be2f-ce40e371a50a"]}}'

# 5. Verificar en Notion: guion DEBE tener 700-850 palabras y Mateo 25:14-30
```

#### 3.2 BUG-03 (TASKS.md): Docker desactualizado en VM

**Problema:** La VM tiene el código actualizado (scp durante sesión anterior) pero el container Docker usa imagen vieja cacheada.

**Fix:**
```bash
ssh -i ~/.ssh/id_rsa_oracle gonzalojoel1_gmail_com@136.111.55.189
cd /home/gonzalojoel1_gmail_com/rompiendo-barreras
git pull
docker build -t rb_vps_backend:latest . --no-cache
docker rm -f rb_vps_backend
docker run -d --name rb_vps_backend ...
```

#### 3.3 TASK-18.4: Few-shot examples para Copywriter (duración mal calculada)

**Problema:** El Copywriter calcula 25 min en vez de 3 min.

**Fix:** Agregar en `config/system_prompts_squad.py` → `COPYWRITER_PROMPT`:
```
EJEMPLO REAL (video 3 min, 250 ppm):
---
HOOK (0-15s): [Gancho de apertura]
IDES (15-60s): [Idea principal]
DESARROLLO (60-120s): [Desarrollo]
ACCIÓN (120-150s): [CTA específico]
 cerrando (150-180s): [Cierre memorable]

Duración total: 3 min = 180s = ~750 palabras
```

#### 3.4 TASK-18.5: Brand Guardian falla con score 6/10

**Problema:** El Brand Guardian valida con checklist pero siempre falla.

**Fix:** Revisar checklist en bunker y ajustar umbrales o few-shot examples del output esperado.

#### 3.5 TASK-18.6: Validación automática de duración post-generación

**Archivo:** `scripts/run_hybrid_squad.py` → agregar función:
```python
def _validate_duration(guion: str, target_min: int, ppm: int = 250) -> tuple[bool, str]:
    words = len(guion.split())
    expected = target_min * ppm
    deviation = abs(words - expected) / expected
    if deviation > 0.15:  # 15% tolerancia
        return False, f"Duración {words/ppm:.1f}min ≠ {target_min}min objetivo"
    return True, "OK"
```

#### 3.6 TASK-18.7: Tabla de versículos por pilar

**Problema:** Copywriter inventa versículos cuando NO debería y no usa los del .docx.

**Fix:** Agregar en Copywriter prompt:
```
MAPA DE VERSÍCULOS POR PILAR (del documento .docx):
| Pilar | Versículo |
|---|---|
| M0 Video 4 | Lucas 12:22-31 |
| P1 | (de sección "Roadmap: Pilar 1") |
| P2 | Mateo 6:25-34 |
SIEMPRE usa el versículo de ESTA TABLA. NO inventes.
```

#### 3.7 TASK-18.8: Stub _generate_ad_content menciona anuncio archivado

**Archivo:** `scripts/run_hybrid_squad.py` → `_generate_ad_content()`

**Problema:** Stub genera "HOOK (0-5s): Tienes un negocio pero Dios no es el CEO..." que menciona a José de Arimatea y el síndrome del impostor — contenido que el usuario dijo NO usar.

**Fix:** Reescribir con template genérico:
```python
def _generate_ad_content(topic: str, target_db: str) -> str:
    return f"""HOOK (0-5s): [Gancho intrigante sobre {topic}]
IDEAS (5-30s): [Breve reflexión relacionada]
CTA (30-60s): [Invitación a action]
"""
```

---

### Paso 4 — Implementar Backoff y Manejo de Errores [🟡 IMPORTANTE]

**Objetivo:** Prevenir rate limiting yhang del sistema.

#### 4.1 Backoff en polling de telegram_bot

**Archivo:** `vps_backend/telegram_bot.py:línea 236`

**Problema:** Polling cada 60s sin backoff — 10 errores = 10 requests en 10s.

**Fix:**
```python
# En poll_approved_ideas_task
backoff = 60  # segundos
max_backoff = 300
while True:
    try:
        await check_and_process_approved()
        backoff = 60  # reset
    except Exception as exc:
        backoff = min(backoff * 2, max_backoff)
    await asyncio.sleep(backoff)
```

#### 4.2 Backoff en sync_manager.flush_pending

**Archivo:** `vps_backend/sync_manager.py:línea 154`

**Problema:** Reintenta TODOS los eventos sin backoff.

**Fix:** Implementar exponential backoff con max 5 reintentos.

#### 4.3 Retry en orchestrator

**Archivo:** `vps_backend/orchestrator.py:línea 108`

**Problema:** `max_retries=1` muy bajo.

**Fix:** Subir a `max_retries=3`.

#### 4.4 Retry en llm_client

**Archivo:** `vps_backend/llm_client.py:línea 519`

**Problema:** Retry interno usa `max_retries=1`.

**Fix:** Implementar circuit breaker tras 2 fallos consecutivos.

---

### Paso 5 — Limpiar Duplicación y Código Muerto [🟢 MEDIO]

**Objetivo:** Eliminar redundancia y archivos obsoletos.

#### 5.1 UNIFICAR notion_bridge y rb_notion_bridge

**Problema:** `rb_notion_bridge/` es 99% idéntico a `notion_bridge/`. La única diferencia es el nombre del paquete en imports.

**Análisis:**
| Archivo | notion_bridge | rb_notion_bridge |
|---|---|---|
| `client.py` | 173 líneas | 173 líneas (idéntico) |
| `service.py` | 176 líneas | 176 líneas (idéntico) |
| `cache.py` | 88 líneas | 88 líneas (idéntico) |
| `config.py` | 88 líneas | 88 líneas (idéntico) |
| `exceptions.py` | 40 líneas | 40 líneas (idéntico) |
| `transformer.py` | 158 líneas | 158 líneas (idéntico) |
| `__init__.py` | 55 líneas | 55 líneas (dif: nombre pkg) |

**Decisión requerida:**
1. **Opción A:** Eliminar `rb_notion_bridge/` y actualizar imports en `scripts/run_hybrid_squad.py` y `vps_backend/` para usar `notion_bridge/`
2. **Opción B:** Mantener `rb_notion_bridge/` y eliminar `notion_bridge/` (si fue留着 como backup)
3. **Opción C:** Mantener ambos pero consolidate en un solo paquete shared

**Recomendación:** Opción A — unificar en `notion_bridge/`.

#### 5.2 Thread safety en notion_bridge/cache.py

**Archivo:** `notion_bridge/cache.py:línea 39`

**Problema:** Cache no es thread-safe. Dos threads pueden corromper `_store`.

**Fix:**
```python
import threading
self._lock = threading.Lock()

def get(self, key: str) -> CacheEntry | None:
    with self._lock:
        # existing code
```

#### 5.3 Loop infinito potencial en service.py

**Archivo:** `notion_bridge/service.py:líneas 64-78`

**Problema:** `while True` con `has_more=True` pero `next_cursor=null` → loop infinito.

**Fix:**
```python
while True:
    if not response.get("has_more"):
        break
    start_cursor = response.get("next_cursor")
    if not start_cursor:
        break
    if start_cursor is None and response.get("has_more"):
        # Edge case: API inconsistency
        logger.warning("notion_service: has_more=True but cursor=None")
        break
```

#### 5.4 Archivos/scripts huérfanos

**Archivos a archivar/mover:**
| Archivo | Razón |
|---------|-------|
| `scripts/setup_ecosystem.py` | One-time, ya ejecutado |
| `scripts/update_notion_styling.py` | Nunca integrado al flujo |
| `scripts/build_notion_databases.py` | Desactualizado (4 DBs vs 11 actuales) |
| `scripts/publish_mvp_content.py` | One-time MVP, ya ejecutado |
| `package.json` | Huérfano (referencia install_gcloud.sh que no existe) |

**Acción:** Crear `scripts/archive/` y mover estos archivos ahí.

#### 5.5 DBS legacy en manifest

**Archivo:** `manifests/notion_databases_manifest.json`

**Problema:** `db_anuncios`, `db_tareas`, `db_alumnos` tienen `url: ""` (vacío).

**Fix:** Marcar como `archived: true`:
```json
{
  "db_anuncios": {
    "url": "",
    "archived": true
  }
}
```

---

### Paso 6 — Corregir Documentación [🟢 MEDIO]

**Objetivo:** Sincronizar docs con estado real del proyecto.

#### 6.1 fase3.md desactualizado

**Problema:** Tabla de estado dice Paso 2 ⏳ PENDIENTE pero el análisis dice ✅ COMPLETADO.

**Fix:** Corregir tabla:
```
| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Vinculación Automations Notion | ✅ COMPLETADO |
| 2 | Ingesta / Hidratación | ✅ COMPLETADO |
| 3 | Pipeline LLMs | ⏳ PENDIENTE |
| 4 | Loop QA 9/10+ | ⏳ PENDIENTE |
| 5 | Sincronización Final | ⏳ PENDIENTE |
| 6 | Monitoreo 24/7 | ⏳ PENDIENTE |
```

#### 6.2 Drift de nombres de agentes

**Problema:** `config/prompts_agentes_orca.md` usa "Agentes 1-4" pero `config/system_prompts_squad.py` usa "Trend Hunter/Strategist/Copywriter/Guardian".

**Fix:** Unificar nombres — usar siempre:
- Trend Hunter
- Strategist
- Copywriter
- Brand Guardian

#### 6.3 AGENTS.md workspace structure incompleta

**Archivo:** `AGENTS.md:§5`

**Fix:** Actualizar estructura:
```markdown
## 5. Estructura del Workspace (referencia rápida)

```text
rompiendo-barreras/
├── AGENTS.md                              ← constitución
├── docs/                                  ← estrategia, guiones, esquemas
├── config/
│   ├── prompts_agentes_orca.md            ← system prompts Agentes
│   └── system_prompt_orquestador.md       ← plantilla para subagentes
├── context_vault/                         ← 6 archivos .md del búnker
├── scripts/                               ← utilidades ejecutables
│   └── run_hybrid_squad.py                ← core pipeline
├── manifests/                             ← outputs JSON de scripts
├── notion_bridge/                         ← cliente Notion (unificado)
├── vps_backend/                           ← código del VPS
├── fase1.md / fase2.md / fase3.md / fase4.md
└── TASKS.md                               ← backlog de sprints
```
```

#### 6.4 requirements.txt sin upper bounds

**Archivo:** `vps_backend/requirements.txt`

**Problema:** `fastapi>=0.110.0` permite versión 99.0.0 que podría romper.

**Fix:**
```
fastapi>=0.110.0,<0.115.0
uvicorn[standard]>=0.27.0,<0.30.0
pydantic>=2.0.0,<3.0.0
```

---

### Paso 7 — CI/CD con GitHub Actions [🏗️ ESTRUCTURAL]

**Objetivo:** Automatizar deploy a producción.

#### 19.1 — GitHub Actions + SSH (ya documentado en TASKS.md)

**Estado:** NO implementado.

**Archivos a crear:**
1. `.github/workflows/deploy.yml`
2. `.github/workflows/test.yml`

**GitHub Secrets requeridos:**
```
GOOGLE_APPLICATION_CREDENTIALS (JSON del service account)
MINIMAX_API_KEY
NOTION_API_KEY
TELEGRAM_BOT_TOKEN
ORCA_API_KEY
SSH_PRIVATE_KEY (contenido de id_rsa_oracle)
VPS_HOST (136.111.55.189)
VPS_USER (gonzalojoel1_gmail_com)
```

---

## 🔧 Comandos Rápidos de Verificación

```bash
# Verificar que no hay credentials hardcodeadas
grep -r "ntn_REDACTED_LEAK" --include="*.py" --include="*.md" .
grep -r "REDACTED_LEAK_2026-07-28_TELEGRAM" --include="*.py" --include="*.md" .

# Verificar syntax errors
python3 -m py_compile vps_backend/*.py
python3 -m py_compile scripts/*.py

# Test de imports
python3 -c "from vps_backend.orchestrator import generate_surgical_briefs"
```

---

## 📌 Estado Global — Fase 4

| Paso | Descripción | Estado | Notas |
|------|-------------|--------|-------|
| 1 | Remover credentials hardcodeadas | ✅ COMPLETADO | secrets/SECRETS.md creado, tokens de scripts corregidos |
| 2 | Corregir bugs críticos de código | ✅ COMPLETADO | C-01 a C-07 resueltos |
| 3 | Testear pipeline de agentes | ✅ COMPLETADO | Docker rebuild + deploy OK, hydrate funciona |
| 4 | Implementar backoff y retry | ✅ COMPLETADO | polling 60→300s, sync 5 retries, circuit breaker |
| 5 | Limpiar duplicación y código muerto | ✅ COMPLETADO | rb_notion_bridge eliminado, notion_bridge unificado |
| 6 | Corregir documentación | ✅ COMPLETADO | fase3.md sincronizado, AGENTS.md actualizado |
| 7 | CI/CD con GitHub Actions | ⏳ PENDIENTE | No implementado aún |

---

## 📊 Resumen de Issues

| Categoría | Críticos | Altos | Medios | Total |
|-----------|----------|-------|--------|-------|
| Seguridad | 4 | 4 | 3 | 11 |
| Bugs Código | 4 | 4 | 4 | 12 |
| Pipeline/QA | 1 | 5 | 0 | 6 |
| Limpieza | 0 | 1 | 4 | 5 |
| Documentación | 0 | 2 | 2 | 4 |
| **TOTAL** | **9** | **16** | **13** | **38** |

---

## ✅ Check-list de Cierre de Fase 4

- [x] Todos los tokens hardcodeados eliminados
- [x] Secrets movidos a `secrets/SECRETS.md`
- [x] Bug 1 (prompt) testeado con resultado 9/10
- [x] Bug 3 (Docker) rebuild y deployado
- [x] Código unreachable en run_hybrid_squad.py corregido
- [x] iteration undefined corregido en tools.py
- [x] Backoff implementado en polling y sync
- [x] notion_bridge unificado (rb_notion_bridge eliminado)
- [x] fase3.md sincronizado
- [ ] GitHub Actions deploy workflow creado

---

## 🔗 Commits de Fase 4

| Commit | Descripción |
|--------|-------------|
| `8aa052f` | Fase 4: Security fixes - remove hardcoded credentials, command injection, undefined vars |
| `23f26be` | Fase 4: Important fixes - backoff, retries, unificación, prompts, limits |
| `d857106` | Fix Dockerfile: rb_notion_bridge -> notion_bridge |
