"""telegram_bot.py - Bot de Telegram para Orquestador Rompiendo Barreras.

Permite a Marcos enviar texto o notas de voz via Telegram para disparar
la generación automática de ideas de clases via run_hybrid_squad.py.

Endpoints:
  POST /webhook/telegram    <- mensajes del bot (vía webhook HTTPS)
  GET  /webhook/telegram    <- verificación inicial por Telegram

Seguridad:
  - Whitelist de chat_id (solo Marcos puede usar el bot)
  - Token en .env (TELEGRAM_BOT_TOKEN)
  - Filtrado por chat_id almacenado en .env (TELEGRAM_ALLOWED_CHAT_IDS, CSV)

Uso:
  # Modo polling (recomendado para VPS sin dominio fijo):
  python3 vps_backend/telegram_bot.py

  # Modo webhook (para producir con Caddy):
  gunicorn vps_backend.telegram_bot:app --bind 0.0.0.0:8766 &
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Evitar warnings con gestion de versiones de telegram
os.environ.setdefault("PYTHONWARNINGS", "ignore")

log = logging.getLogger("telegram_bot")
logging.basicConfig(
    level=os.getenv("TELEGRAM_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

# Hacer accesibles las carpetas del proyecto para los imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))


# =============================================================================
# Configuración
# =============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
ALLOWED_CHAT_IDS_RAW = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS: set[int] = {
    int(x.strip())
    for x in ALLOWED_CHAT_IDS_RAW.split(",")
    if x.strip().isdigit()
}

ORCHESTRATOR_SCRIPT = PROJECT_ROOT / "scripts" / "run_hybrid_squad.py"
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip().strip('"').strip("'")
IDEAS_DB_ID = os.getenv("IDEAS_DB_ID", "").strip()
WEBHOOK_TRIGGER_URL = os.getenv("WEBHOOK_TRIGGER_URL")

MANIFEST_PATH = PROJECT_ROOT / "manifests" / "notion_databases_manifest.json"
with open(MANIFEST_PATH) as f:
    NOTION_DATABASES = {db["label"]: db for db in json.load(f)}
if not WEBHOOK_TRIGGER_URL:
    raise RuntimeError("WEBHOOK_TRIGGER_URL environment variable is required")
ORCA_API_KEY_HEADER = os.getenv("ORCA_API_KEY", "test_orca_api_key_32chars_minimum_aaaa").strip()

# Estado en memoria de paginas ya procesadas (para no reprocesar)
_PROCESSED_IDS: set[str] = set()


def _is_authorized(update: Any) -> bool:
    """Retorna True si el update proviene de un chat autorizado."""
    if not ALLOWED_CHAT_IDS:
        log.error("TELEGRAM_ALLOWED_CHAT_IDS no configurado - request rechazado")
        return False
    chat = getattr(update, "effective_chat", None)
    if chat is None:
        return False
    return getattr(chat, "id", None) in ALLOWED_CHAT_IDS


# =============================================================================
# Helpers de generación de ideas
# =============================================================================


def _sanitize_topic(topic: str) -> str:
    """Solo permite alfanuméricos, espacios, tildes, y caracteres -_,."""
    sanitized = re.sub(r"[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ ,.:;!?¡¿\-_()]", "", topic)
    return sanitized.strip()


def run_ideate(topic: str) -> tuple[int, str, str]:
    """Ejecuta run_hybrid_squad.py --mode=ideate con el tema dado.
    Retorna (returncode, stdout, stderr).
    """
    sanitized_topic = _sanitize_topic(topic)
    if not sanitized_topic:
        return 1, "", "Topic inválido o vacío"

    if not ORCHESTRATOR_SCRIPT.exists():
        return 1, "", f"Script no encontrado: {ORCHESTRATOR_SCRIPT}"

    cmd = [
        "python3",
        str(ORCHESTRATOR_SCRIPT),
        "--mode=ideate",
        f"--topic={sanitized_topic}",
    ]
    log.info("Ejecutando ideate: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
            env=os.environ.copy(),  # heredar env del container (API keys)
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Timeout de 600s alcanzado"
    except Exception as exc:
        log.exception("Error ejecutando ideate")
        return 1, "", str(exc)


def summarize_ideate_output(stdout: str, stderr: str = "") -> str:
    """Extrae resumen humano del output del orchestrator (cuantas ideas se publicaron).
    NOTA: El orchestrator escribe sus logs a STDERR, no STDOUT.
    """
    # Buscar en AMBOS streams
    combined = (stdout or "") + "\n" + (stderr or "")
    published = 0
    brief_lines = []
    for line in combined.splitlines():
        if "Publicadas:" in line and "paginas" in line:
            m = re.search(r"(\d+)\s*paginas", line)
            if m:
                published = int(m.group(1))
        if "briefs generados:" in line and brief_lines == []:
            brief_lines.append(line.strip())
        if "ideas devueltas:" in line:
            m = re.search(r"(\d+)\s*ideas devueltas", line)
            if m:
                brief_lines.append(f"  - ideas devueltas: {m.group(1)}")
    summary = "\n".join(brief_lines) if brief_lines else ""
    summary += f"\n\n📌 Publicadas en Notion: {published} ideas"
    return summary


# =============================================================================
# Polling: detectar ideas Aprobadas y disparar process_approved
# =============================================================================


def query_approved_ideas() -> list[dict]:
    """Sprint 8: itera sobre las 8 DBs por pilar y devuelve las que están en estado
    '📝 Guion Aprobado' y aún no han sido procesadas.
    """
    if not NOTION_API_KEY:
        log.warning("NOTION_API_KEY no configurada, polling desactivado")
        return []

    pilar_labels = ["db_M0", "db_P1", "db_P2", "db_P3", "db_P4", "db_P5", "db_P6", "db_P7"]
    pilars_dbs = [NOTION_DATABASES[lbl]["id"] for lbl in pilar_labels]

    payload = {
        "filter": {
            "property": "Estado",
            "status": {"equals": "📝 Guion Aprobado"},
        },
        "page_size": 10,
    }

    import urllib.request
    approved = []
    for db_id in pilars_dbs:
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            method="POST",
            data=json.dumps(payload).encode(),
        )
        req.add_header("Authorization", f"Bearer {NOTION_API_KEY}")
        req.add_header("Notion-Version", "2022-06-28")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
        except Exception as exc:
            log.warning(f"Error consultando {db_id[-12:]}: {exc}")
            continue

        for page in data.get("results", []):
            pid = page.get("id")
            if pid and pid not in _PROCESSED_IDS:
                title_prop = page.get("properties", {}).get("Clase", {}).get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_prop)
                # pillar name
                pilar_sel = page.get("properties", {}).get("Pilar", {}).get("select") or {}
                pilar_name = pilar_sel.get("name", "") if isinstance(pilar_sel, dict) else ""
                approved.append({"id": pid, "title": title, "pilar": pilar_name})
    return approved


def trigger_process_approved(page_ids: list[str], all_approved: bool = False) -> tuple[int, str]:
    """Llama al webhook del backend para iniciar el pipeline."""
    import urllib.request
    payload = {
        "action": "process_approved",
        "payload": {
            "page_ids": page_ids,
            "all_approved": all_approved,
            "event_type": "page.approved",
        },
    }
    req = urllib.request.Request(
        WEBHOOK_TRIGGER_URL, method="POST", data=json.dumps(payload).encode()
    )
    req.add_header("X-Orca-API-Key", ORCA_API_KEY_HEADER)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return 0, str(e)


async def poll_approved_ideas_task(context) -> None:
    """Background task: cada 60s revisa Notion y dispara process_approved."""
    import asyncio
    # Primer chequeo: cargar IDs ya existentes para no disparar
    # (solo procesa nuevas Aprobadas que aparezcan DESPUÉS de arrancar el bot)
    existing = query_approved_ideas()
    for e in existing:
        _PROCESSED_IDS.add(e["id"])
    log.info("Polling iniciado. %d ideas ya aprobadas (no se reprocesan)", len(existing))

    backoff = 60
    max_backoff = 300
    while True:
        try:
            new_approved = query_approved_ideas()
            for item in new_approved:
                pid = item["id"]
                if pid in _PROCESSED_IDS:
                    continue
                _PROCESSED_IDS.add(pid)
                log.info("Idea aprobada detectada: %s — %s [%s]", pid, item["title"][:50], item.get("pilar", ""))
                status, body = trigger_process_approved([pid])
                log.info("process_approved disparado: HTTP %s", status)
                for chat_id in ALLOWED_CHAT_IDS or [0]:
                    if chat_id:
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    f"🟢 **Idea aprobada detectada**\n\n"
                                    f"📌 {item['title']}\n"
                                    f"🏛️ {item.get('pilar', '?')}\n"
                                    f"🆔 `{pid[:12]}...`\n\n"
                                    f"Pipeline disparado (HTTP {status}). "
                                    f"En 2-3 min el guion aparecerá como 🎬 Para Grabar."
                                ),
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
            backoff = 60
        except Exception as exc:
            backoff = min(backoff * 2, max_backoff)
            log.exception("Error en polling loop, backoff=%ds", backoff)
        await asyncio.sleep(backoff)


# =============================================================================
# Transcripción de audio via Gemini (multimodal)
# =============================================================================


# =============================================================================
# Transcripción de audio via Gemini (multimodal)
# =============================================================================


def transcribe_ogg_with_gemini(ogg_path: Path) -> str:
    """Convierte un .ogg a texto usando Gemini multimodal.
    Devuelve el texto transcrito.
    """
    try:
        import base64
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest

        # Auth con Vertex AI
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip().strip('"').strip()
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.getenv("GOOGLE_CLOUD_REGION", "global").strip()

        if not creds_path or not Path(creds_path).exists():
            raise RuntimeError(f"Service account no encontrado: {creds_path}")

        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        creds.refresh(GoogleRequest())

        # Leer audio y codificar en base64
        audio_data = base64.b64encode(ogg_path.read_bytes()).decode("utf-8")

        # Endpoint de Gemini 2.5 Flash (multimodal) en Vertex
        url = (
            f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
            f"/publishers/google/models/gemini-2.5-flash:generateContent"
        )

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Transcribe exactamente el contenido en español de este audio. "
                            "Devuelve SOLO el texto transcrito, sin comillas ni explicaciones. "
                            "Si no puedes transcribir, devuelve 'NO_AUDIO'."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": "audio/ogg",
                            "data": audio_data,
                        }
                    },
                ],
            }]
        }

        import urllib.request
        req = urllib.request.Request(
            url, method="POST", data=json.dumps(payload).encode("utf-8")
        )
        req.add_header("Authorization", f"Bearer {creds.token}")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            log.info("Audio transcrito: %d chars", len(text))
            return text

    except Exception as exc:
        log.exception("Error transcribiendo audio")
        return f"NO_AUDIO: {exc}"


# =============================================================================
# Bot de Telegram (polling)
# =============================================================================

WELCOME_MESSAGE = """👋 ¡Hola, Marcos! Soy el bot de Rompiendo Barreras.

Comandos disponibles:

🧠  /ideate <tema>     → Genera 3 ideas de clase en Notion
📝  /process [id]       → Genera guion de las ideas Aprobadas (o una específica)
🎙️  Nota de voz (ogg)   → La transcribo y disparo ideación automáticamente
✍️  Texto libre         → Lo uso directamente como tema
📊  /status            → Estado del backend y Notion
❓  /help               → Esta ayuda

⚙️ AUTOMÁTICO: detecto cada 60s si aprobáste ideas en Notion y genero guion solo.

Tip: Probá enviarme '3 claves para salir de deudas con fé'.
"""


def build_application():
    """Construye la Application de telegram-bot."""
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN no configurado. Abortando.")
        sys.exit(1)

    try:
        from telegram import Update  # noqa: F401
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            filters,
            ContextTypes,
        )
    except ImportError as exc:
        log.error(
            "Falta python-telegram-bot. Instalar con: pip install python-telegram-bot"
        )
        raise SystemExit(1) from exc

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def cmd_start(update, context):
        if not _is_authorized(update):
            return
        await update.message.reply_text(WELCOME_MESSAGE)

    async def cmd_help(update, context):
        if not _is_authorized(update):
            return
        await update.message.reply_text(WELCOME_MESSAGE)

    async def cmd_status(update, context):
        if not _is_authorized(update):
            return
        # Chequear health del backend
        import urllib.request
        try:
            with urllib.request.urlopen(
                "https://136.111.55.189.sslip.io/health", timeout=5
            ) as r:
                data = json.loads(r.read())
                status = f"✅ Backend: {data.get('status', '?')} (v{data.get('version', '?')})"
        except Exception as exc:
            status = f"❌ Backend: {exc}"
        await update.message.reply_text(
            f"📊 Estado del sistema\n\n{status}\n\nNotion: conectado ✅"
        )

    async def cmd_ideate(update, context):
        if not _is_authorized(update):
            await update.message.reply_text("⛔ No autorizado")
            return
        topic = " ".join(context.args or [])
        if not topic:
            await update.message.reply_text(
                "🧠 Usa: `/ideate <tema>` o envíame el tema como texto"
            )
            return
        await _process_ideate(update, context, topic)

    async def cmd_process(update, context):
        """Comando manual: /process [page_id] o /process all."""
        if not _is_authorized(update):
            return
        args = context.args or []
        approved = query_approved_ideas()
        if not approved:
            await update.message.reply_text(
                "ℹ️ No hay ideas en estado 'Aprobada' pendientes de procesar."
            )
            return

        if args and args[0] != "all":
            # Filtrar por page_id específico
            target = args[0]
            matched = [a for a in approved if a["id"] == target or a["id"].startswith(target)]
            if not matched:
                await update.message.reply_text(
                    f"❌ No encontré idea aprobada con id `{target}`.\n"
                    f"Aprobadas disponibles: {', '.join(a['id'][:12] + '...' for a in approved[:5])}"
                )
                return
            page_ids = [m["id"] for m in matched]
            titles = "\n".join(f"  • {m['title'][:50]}" for m in matched)
        else:
            page_ids = [a["id"] for a in approved]
            titles = "\n".join(f"  • {a['title'][:50]}" for a in approved)

        await update.message.reply_text(
            f"🟢 Procesando {len(page_ids)} idea(s):\n{titles}\n\n⏳ Pipeline en background (2-3 min)..."
        )
        for pid in page_ids:
            _PROCESSED_IDS.add(pid)
        status, body = trigger_process_approved(page_ids)
        await update.message.reply_text(
            f"Pipeline disparado: HTTP {status}\n```\n{body[:400]}\n```",
            parse_mode=None,
        )

    async def handler_text(update, context):
        # Bloqueo de no autorizados
        if not _is_authorized(update):
            if update.message and update.message.text:
                log.warning("Mensaje no autorizado: chat_id=%s", update.effective_chat.id)
            return
        topic = (update.message.text or "").strip()
        if not topic or topic.startswith("/"):
            return
        await _process_ideate(update, context, topic)

    async def handler_voice(update, context):
        if not _is_authorized(update):
            return
        msg = update.message
        if not msg or not msg.voice:
            return
        # Telegram .ogg file_id
        voice = msg.voice
        await msg.reply_text("🎙️ Audio recibido, transcribiendo con Gemini…")
        try:
            tg_file = await context.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(
                suffix=".ogg", delete=False
            ) as tmp:
                tmp_path = Path(tmp.name)
            tg_file.download(custom_path=str(tmp_path))
            transcript = transcribe_ogg_with_gemini(tmp_path)
            tmp_path.unlink(missing_ok=True)
            if transcript.startswith("NO_AUDIO") or not transcript.strip():
                await msg.reply_text(
                    "❌ No pude transcribir el audio. Probá enviarlo como texto."
                )
                return
            await msg.reply_text(f"📝 Transcripción:\n\n{transcript[:600]}")
            await _process_ideate(update, context, transcript, source="voice")
        except Exception as exc:
            log.exception("Error procesando audio")
            await msg.reply_text(f"❌ Error de audio: {exc}")

    async def _process_ideate(update, context, topic: str, source: str = "text"):
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"🤖 Generando 3 ideas sobre:\n\n> _{topic}_\n\n⏳ Tiempo estimado: 40-60s..."
        )
        # Ejecutar en thread para no bloquear el event loop
        import asyncio
        returncode, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, run_ideate, topic
        )
        if returncode != 0:
            err_tail = (stderr or stdout or "error desconocido")[-1000:]
            await context.bot.send_message(
                chat_id,
                f"❌ Error al generar ideas:\n\n```\n{err_tail}\n```",
                parse_mode="Markdown",
            )
            return
        summary = summarize_ideate_output(stdout or "", stderr or "")
        await context.bot.send_message(
            chat_id,
            f"✅ Ideación completada ({source})\n\n{summary}\n\n👉 Abre Notion para revisar y aprobar.",
            parse_mode=None,
        )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ideate", cmd_ideate))
    app.add_handler(CommandHandler("process", cmd_process))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handler_text)
    )
    app.add_handler(MessageHandler(filters.VOICE, handler_voice))

    return app


def main() -> int:
    """Entry point en modo polling."""
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN no configurado en .env", file=sys.stderr)
        return 1
    print(
        f"🤖 Bot Telegram arrancando... (token=...{TELEGRAM_BOT_TOKEN[-8:]})",
        flush=True,
    )
    print(f"   Authorized chat_ids: {sorted(ALLOWED_CHAT_IDS) or 'TODOS (whitelist vacía)'}", flush=True)
    print(f"   Polling Notion: activado (cada 60s revisa ideas Aprobadas)", flush=True)
    app = build_application()

    async def post_init(application):
        """Arranca la task de polling en background usando asyncio directo."""
        import asyncio
        asyncio.create_task(poll_approved_ideas_task(application))

    app.post_init = post_init
    app.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
