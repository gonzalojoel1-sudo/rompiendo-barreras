# Pendientes — Sprint 18+ (tool calling + agentes)

Este archivo documenta TODO lo que quedó a medio hacer / sin testear / pendiente
para que cualquiera (vos, yo, otra IA) pueda retomar sin perder contexto.

---

## Contexto: dónde estamos parados

**Última sesión:** Sprint 17 (tool calling real). El Copywriter ya puede LEER archivos
del búnker via `read_bunker_file()` y `list_bunker_files()`. Ambos providers
(MiniMax M3 y Vertex Gemini 2.5 Flash) soportan function calling nativo.

**Tests parciales hechos (1 de 7 videos del Onboarding):**
- Test 1 (sin tool calling): 1,640 palabras, versículo equivocado (Nehemías vs Mateo 25) → 4/10
- Test 2 (con tool calling, sin reglas de duración/versículo): 1,498 palabras, Nehemías → 4-5/10
- Test 3 (con tool calling + reglas de duración/versículo): **NO SE TESTEÓ** (gasté API)

**El commit `5e3409e` es el último en producción.**

---

## 🐛 Bug 1 (CRÍTICO): prompt con reglas pero NO testeado

**Commit:** `fb0121e` (Sprint 17.1+17.2)

**Lo que cambié en el prompt:**
- Regla de duración EXACTA: `palabras = duración_min * ppm_objetivo`
  (250 ppm para videos cortos, 280 ppm para clases Pilar)
- Regla del versículo: "USÁ el del archivo, NO elijas libre"

**Lo que falta testear:**
1. Rebuild de la imagen Docker (puede ser `docker build -t rb_vps_backend:latest . --no-cache` — toma ~5-8 min)
2. Re-arrancar el container: `docker rm -f rb_vps_backend && docker run -d --name rb_vps_backend ...`
3. Aprobar una idea en `db_M0` (cambiar a "📝 Guion Aprobado")
4. Llamar webhook: `curl -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger -d '{"action":"process_approved","payload":{"page_ids":["..."]}}'`
5. Verificar en Notion: el guion DEBE tener
   - Entre 700-850 palabras (si duración 3 min)
   - Mateo 25:14-30 como versículo (no Nehemías)
6. Comparar contra mi guion humano (versión B, 6.5/10) en `fase3.md` o en el chat previo

**Prompt actualizado está en:**
`config/system_prompts_squad.py` → `COPYWRITER_PROMPT` → sección "REGLA DE DURACIÓN (Sprint 17.1)" y "REGLA DEL VERSÍCULO (Sprint 17.2)"

**Comando para validar en una sola línea:**
```bash
# Resetear + disparar + esperar
curl -s -X PATCH "https://api.notion.com/v1/pages/3aacfb86-8e33-81a2-be2f-ce40e371a50a" \
  -H "Authorization: Bearer <NOTION_API_KEY>" \
  -H "Notion-Version: 2022-06-28" -H "Content-Type: application/json" \
  -d '{"properties":{"Estado":{"status":{"name":"📝 Guion Aprobado"}}}}'
curl -s -X POST https://136.111.55.189.sslip.io/api/v1/orca/webhook/trigger \
  -H "X-Orca-API-Key: test_orca_api_key_32chars_minimum_aaaa" -H "Content-Type: application/json" \
  -d '{"action":"process_approved","payload":{"page_ids":["3aacfb86-8e33-81a2-be2f-ce40e371a50a"],"all_approved":false}}'
sleep 240
tail -25 /home/gonzalojoel1_gmail_com/rompiendo-barreras/logs/pipeline_process_approved.log
```

---

## 🐛 Bug 2 (MEDIO): la DB Matriz de Anuncios tiene 6 items "espectaculares" mal clasificados

**Estado:** No tocado en la última sesión.

**Síntoma:** El usuario mencionó que "en la db2 (la que archivaste) hay una clase que es espectacular". Investigamos y había 6 items no-stub con títulos prometedores. Pero el usuario luego dijo "esa no es la clase que te decía, seguro se ha borrado, no tomes el contexto de ese anuncio que de hecho está feo".

**Decisión:** NO usar nada de la DB Matriz de Anuncios como referencia para los prompts. Está archivada.

**Acción:** Verificar que la DB archivada (ID `3a8cfb86-8e33-8128-b27b-ca8b329a7f80`) siga archivada. Si se restauró accidentalmente, archivar de nuevo.

---

## 🐛 Bug 3 (MEDIO): versión de la app en VM

**Estado:** La VM tiene el `system_prompts_squad.py` actualizado con mis reglas (vía `scp` durante la última sesión). PERO el container Docker usa su propia imagen cacheada.

**Comando para sincronizar VM con repo:**
```bash
cd /home/gonzalojoel1_gmail_com/rompiendo-barreras
git pull
docker build -t rb_vps_backend:latest . --no-cache
docker rm -f rb_vps_backend
docker run -d --name rb_vps_backend --env-file /home/gonzalojoel1_gmail_com/rompiendo-barreras/vps_backend/.env \
  -p 8765:8765 -v "$(pwd)/context_vault:/app/context_vault:ro" \
  -v "$(pwd)/logs:/app/logs" -v "$(pwd)/secrets:/app/secrets:ro" \
  -v rb_vps_data:/app/data \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/vertex.json \
  -e GOOGLE_CLOUD_REGION=global rb_vps_backend:latest
```

**Tiempo:** ~10-15 min total (build con todas las deps).

---

## 🎯 Pendiente Sprint 18+ (cuando vuelvas)

### 18.1 — Testear los 7 videos restantes del Onboarding

Una vez confirmado que el Video 1 (Bienvenida) funciona con las reglas nuevas, generar los otros 7:
- Video 2: Nuestra Misión (4 min)
- Video 3: Visión y Legado (5 min)
- Video 4: Propósito (6 min)
- Video 5: Metodología de Implementación (7 min)
- Video 6: Áreas de Control y Corresponsabilidad (7 min)
- Video 7: Código de Honor - Reglas de la Comunidad (4 min)
- Video 8: Activación Inmediata - Primera Victoria (4 min)

Estructura de cada uno ya está en `context_vault/06_onboarding_structure.md`.

### 18.2 — Generar 10 ideas por cada Pilar (M0..P7)

Una vez el Onboarding esté OK, regenerar las 8 DBs con ideas basadas en el búnker:
- P1 Casa de Gobierno (3 semanas, 3 misiones = 3 ideas)
- P2 Mentalidad de Reino (3 semanas = 3 ideas)
- P3 Hábitos del Éxito (3 semanas = 3 ideas)
- ... etc
- Total objetivo: 21 ideas (3 por pilar × 7 pilares) o 80+ si se quiere 10 por pilar

**Búnker a usar:** `06_onboarding_structure.md` da la estructura por pilar (Semana + Misión Operativa + Acción Concreta + Feedback/Validación).

### 18.3 — Mejorar el guard de JSON parsing

**Archivo:** `scripts/run_hybrid_squad.py` → `_parse_llm_json()`

**Problema:** El LLM a veces devuelve JSON inválido (con `<think>` tags o markdown fences) y el parser hace fallback a STUB.

**Mejora:** Agregar 3 estrategias de fallback:
1. Strip `<think>...</think>` ANTES de buscar JSON
2. Buscar primer bloque ` ```json ... ``` `
3. Si falla, pedir retry al LLM con feedback "tu JSON anterior estaba roto"

### 18.4 — Implementar few-shot examples para el Copywriter

**Archivo:** `config/system_prompts_squad.py`

**Qué:** Agregar 1-2 ejemplos REALES de guiones cortos del búnker en el prompt del Copywriter para que entienda el formato esperado.

**Por qué:** El agente ahora sigue la estructura pentagonal (A-I-D-A-C) pero la duración la sigue calculando mal (25 min en vez de 3 min). Few-shot examples ayudarían.

### 18.5 — Few-shot examples para el Brand Guardian

**Archivo:** `config/system_prompts_squad.py`

**Mismo problema que 18.4** pero para el Brand Guardian (que ahora valida con checklist del bunker, pero falla siempre con score 6/10).

### 18.6 — Validación automática de duración

**Archivo:** `scripts/run_hybrid_squad.py` → función nueva `_validate_duration(guion, target_duration_min)`

**Qué:** Después de generar el guion, validar que `len(words) / ppm_objetivo ≈ target_duration`. Si no coincide, regenerar con feedback.

### 18.7 — Mejorar los 3 hooks del .docx

**Archivo:** `config/system_prompts_squad.py`

**Problema:** El Copywriter inventa versículos cuando NO debería (regla 17.2). Pero cuando SÍ los hay en el archivo, no los usa. Necesita tabla de mapping explícita:

| Pilar | Versículo principal del .docx |
|---|---|
| M0 Video 1 | (no especifico, depende del video) |
| M0 Video 4 | Lucas 12:22-31 |
| P1 | (de la sección "Roadmap: Pilar 1") |
| P2 | Mateo 6:25-34 |
| ... | ... |

### 18.8 — Resolver el bug del stub `_generate_ad_content`

**Archivo:** `scripts/run_hybrid_squad.py` → función `_generate_ad_content()`

**Estado:** El stub genera "HOOK (0-5s): Tienes un negocio pero Dios no es el CEO..." que es el contenido del anuncio archivado que el usuario explícitamente dijo que NO usemos.

**Acción:** Reescribir el stub con un template genérico que NO mencione a José de Arimatea ni al síndrome del impostor.

---

## 🏗️ Pendiente estructural (Fase 4 — CI/CD)

### 19.1 — GitHub Actions + SSH

**Estado:** NO implementado. El usuario pidió esto pero nunca lo hicimos (priorizamos el tool calling).

**Por hacer:**
1. Crear `.github/workflows/deploy.yml`
2. Configurar SSH key en la VM (la `id_rsa_oracle` que ya existe en la Mac)
3. Configurar 8 GitHub Secrets:
   - `GOOGLE_APPLICATION_CREDENTIALS` (contenido del JSON)
   - `MINIMAX_API_KEY`
   - `NOTION_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `ORCA_API_KEY`
   - `SSH_PRIVATE_KEY` (contenido de id_rsa_oracle)
   - `VPS_HOST` (136.111.55.189)
   - `VPS_USER` (gonzalojoel1_gmail_com)

**Comando del workflow:**
```yaml
name: Deploy to VPS
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /home/gonzalojoel1_gmail_com/rompiendo-barreras
            git pull
            docker build -t rb_vps_backend:latest . --no-cache
            docker rm -f rb_vps_backend
            docker run -d --name rb_vps_backend \
              --env-file /home/gonzalojoel1_gmail_com/rompiendo-barreras/vps_backend/.env \
              -p 8765:8765 -v "$(pwd)/context_vault:/app/context_vault:ro" \
              -v "$(pwd)/logs:/app/logs" -v "$(pwd)/secrets:/app/secrets:ro" \
              -v rb_vps_data:/app/data \
              -e GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/vertex.json \
              -e GOOGLE_CLOUD_REGION=global rb_vps_backend:latest
```

---

## 📊 Estado de la VM

| Recurso | Estado | Notas |
|---|---|---|
| Backend (`rb_vps_backend`) | ✅ Up | Healthy, response 200 a /health |
| Bot Telegram (`rb_telegram_bot`) | ✅ Up | Polling Notion cada 60s |
| Imagen Docker | ⚠️ Vieja | Necesita rebuild para incluir prompt actualizado |
| `secrets/vertex.json` | ✅ Existe | Archivo de credenciales en la VM |
| `.env` | ✅ Actualizado | Tiene `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/vertex.json` |

---

## 📞 Contactos y credenciales (resumen)

> **⚠️ ATENCIÓN:** Las credenciales reales están en `secrets/SECRETS.md` (NO commitear).

| Recurso | Ubicación |
|---|---|
| GitHub | `secrets/SECRETS.md` |
| Notion API | `secrets/SECRETS.md` |
| MiniMax API | `secrets/SECRETS.md` |
| Telegram bot | `secrets/SECRETS.md` |
| Vertex SA | `secrets/SECRETS.md` |
| VM SSH | `secrets/SECRETS.md` |

---

## 📌 Convenciones del proyecto

- **Idioma:** Los prompts al LLM están en **inglés** pero el contenido generado es en **español** (voz de Marcos)
- **Commits:** Prefijo del sprint en el mensaje (`Sprint 17.1:` ...)
- **Commits con 1 cambio:** Preferir commits granulares sobre commits grandes
- **Sin secrets en repo:** `.gitignore` bloquea `.env`, `*.key`, `*.pem`, `secrets/`
- **DBs Notion:** 8 DBs por pilar (M0 + P1..P7), todas en `gonzalojoel1-sudo`
- **Búnker:** 7 archivos `.md` en `context_vault/` que el agente puede leer via tool calling

---

## 📝 Para retomar (TLDR)

Si querés retomar más tarde, lo más importante es:

1. **Rebuild + restart** la imagen Docker para que use el prompt actualizado (Bug 3)
2. **Testear el Video 1** con el prompt nuevo (Bug 1)
3. Si funciona, **generar los otros 7 videos** del Onboarding (Sprint 18.1)
4. Después seguir con Pilares (Sprint 18.2)

El bug más crítico que tiene impacto inmediato es el **Bug 1** (prompt no testeado). El resto son mejoras incrementales.
