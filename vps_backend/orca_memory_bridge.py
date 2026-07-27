"""orca_memory_bridge.py - Middleware / API REST v1 para Agentes de Orca.

Sprint 4: API publica/privada con autenticacion X-Orca-API-Key.
Endpoints:
    GET  /health
    GET  /api/v1/orca/status
    GET  /api/v1/orca/memory
    GET  /api/v1/orca/cache/stats
    GET  /api/v1/orca/scratchpad/pending
    POST /api/v1/orca/scratchpad/append
    POST /api/v1/orca/webhook/trigger
    POST /api/v1/orca/execute
    POST /api/v1/orca/sync/to-notion
    POST /api/v1/orca/sync/from-notion
    POST /api/v1/orca/sync/flush
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# Sprint 6: garantizar que el directorio vps_backend este en sys.path
# para resolver imports relativos a `api_models`, `memory_manager`,
# `notion_bridge`, `sync_manager` cuando se ejecuta el archivo como
# modulo (vps_backend.orca_memory_bridge:app).
_VPS_BACKEND_DIR = Path(__file__).resolve().parent
if str(_VPS_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_VPS_BACKEND_DIR))
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from api_models import (  # noqa: E402
    AgentTaskRequest,
    EventRequest,
    PendingItem,
    PendingSyncResponse,
    ScratchpadAppendResponse,
    ScratchpadEventInput,
    StatusMemorySection,
    StatusNotionSection,
    StatusResponse,
    StatusScratchpadSection,
    WebhookTriggerInput,
    WebhookTriggerResponse,
)
from memory_manager import HierarchicalMemoryManager  # noqa: E402
from rb_notion_bridge import CachedSchemaService, NotionClient  # noqa: E402
from rb_notion_bridge.config import NotionBridgeConfig  # noqa: E402
from sync_manager import EVENT_TO_NOTION, MemorySyncManager  # noqa: E402

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "tu_openai_api_key_aqui")
ORCA_API_KEY = os.getenv("ORCA_API_KEY", "")
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
SCRATCHPAD_PATH = os.getenv(
    "SCRATCHPAD_PATH",
    str(BASE_DIR / "agent_scratchpad.json"),
)

app = FastAPI(
    title="Rompiendo Barreras - Orca Agent API",
    description=(
        "Bridge para conectar agentes de Orca con memoria jerarquica y "
        "sincronizacion bidireccional con Notion (Sprint 4: API REST v1)."
    ),
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def custom_openapi() -> dict:
    """Inyecta el esquema de seguridad APIKeyHeader en el OpenAPI."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["OrcaAPIKey"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Orca-API-Key",
        "description": "API key de Orca, comparada con la variable ORCA_API_KEY del servidor.",
    }
    schema["security"] = [{"OrcaAPIKey": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


def _init_memory() -> HierarchicalMemoryManager:
    Path(SCRATCHPAD_PATH).parent.mkdir(parents=True, exist_ok=True)
    return HierarchicalMemoryManager(
        api_key=OPENAI_API_KEY,
        scratchpad_path=SCRATCHPAD_PATH,
    )


def _init_sync_manager(memory: HierarchicalMemoryManager) -> MemorySyncManager | None:
    if not NOTION_API_KEY:
        logger.warning("orca_bridge.sync_manager.skipped reason=NOTION_API_KEY_missing")
        return None
    try:
        return MemorySyncManager.from_env(memory, manifest_path=MANIFEST_PATH)
    except Exception as exc:
        logger.error("orca_bridge.sync_manager.init_error err=%s", exc)
        return None


memory_mgr = _init_memory()
sync_mgr = _init_sync_manager(memory_mgr)


# =============================================================================
# Auth: X-Orca-API-Key
# =============================================================================

def verify_orca_api_key(
    x_orca_api_key: Annotated[str | None, Header(alias="X-Orca-API-Key")] = None,
) -> str:
    """Compara el header X-Orca-API-Key con la variable ORCA_API_KEY del entorno.

    503 si el servidor no tiene ORCA_API_KEY configurada.
    401 si el header falta o no coincide.
    """
    expected = ORCA_API_KEY
    if not expected:
        logger.error("orca_bridge.auth misconfig ORCA_API_KEY missing")
        raise HTTPException(
            status_code=503,
            detail="ORCA_API_KEY no configurada en el servidor.",
        )
    if not x_orca_api_key:
        raise HTTPException(
            status_code=401,
            detail="Header X-Orca-API-Key ausente.",
        )
    if not secrets.compare_digest(x_orca_api_key, expected):
        logger.warning("orca_bridge.auth rejected key_len=%d", len(x_orca_api_key))
        raise HTTPException(
            status_code=401,
            detail="X-Orca-API-Key invalida.",
        )
    return x_orca_api_key


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Endpoints publicos
# =============================================================================

@app.get("/health", include_in_schema=False)
def health_check() -> dict:
    """Health check (Docker HEALTHCHECK). Sin auth."""
    health: dict[str, Any] = {
        "status": "ok",
        "service": "rb_vps_backend",
        "version": app.version,
        "scratchpad": {"path": SCRATCHPAD_PATH, "exists": False, "writable": False, "size_bytes": 0},
        "notion_reachable": False,
        "notion_configured": bool(NOTION_API_KEY),
    }
    try:
        sp = Path(SCRATCHPAD_PATH)
        sp.parent.mkdir(parents=True, exist_ok=True)
        if not sp.exists():
            sp.touch()
        health["scratchpad"] = {
            "path": str(sp),
            "exists": sp.exists(),
            "writable": os.access(sp, os.W_OK),
            "size_bytes": sp.stat().st_size,
        }
    except Exception as exc:
        health["scratchpad"] = {"accessible": False, "error": str(exc)}
        health["status"] = "degraded"

    if sync_mgr is not None:
        try:
            stats = sync_mgr._service.cache.stats()
            health["notion_reachable"] = sync_mgr.notion_reachable
            health["cache_stats"] = {
                "hits": stats.hits,
                "misses": stats.misses,
                "size": stats.size,
                "ttl_seconds": stats.ttl_seconds,
                "hit_ratio": round(stats.hit_ratio, 4),
            }
        except Exception:
            health["status"] = "degraded"
    return health


# =============================================================================
# API v1 - Autenticada con X-Orca-API-Key
# =============================================================================

@app.get("/api/v1/orca/status", response_model=StatusResponse)
def get_status(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> StatusResponse:
    """Dashboard consolidado: memoria + Notion + cache + scratchpad."""
    scratch = memory_mgr.scratchpad
    memory_section = StatusMemorySection(
        proyecto=scratch.get("proyecto"),
        fase_actual=scratch.get("fase_actual"),
        objetivo_activo=scratch.get("objetivo_activo"),
        decisiones_count=len(scratch.get("decisiones_clave", [])),
        hitos_completados_count=len(scratch.get("hitos_completados", [])),
        hitos_pendientes_count=len(scratch.get("hitos_pendientes", [])),
        event_log_count=len(scratch.get("event_log", [])),
        pending_sync_count=len(scratch.get("notion_sync_pending", [])),
    )

    notion_section = StatusNotionSection(configured=bool(NOTION_API_KEY), reachable=False)
    if sync_mgr is not None:
        try:
            stats = sync_mgr._service.cache.stats()
            notion_section = StatusNotionSection(
                configured=True,
                reachable=sync_mgr.notion_reachable,
                cache={
                    "hits": stats.hits,
                    "misses": stats.misses,
                    "size": stats.size,
                    "ttl_seconds": stats.ttl_seconds,
                    "hit_ratio": round(stats.hit_ratio, 4),
                },
            )
        except Exception as exc:
            notion_section = StatusNotionSection(
                configured=True, reachable=False, cache={"error": str(exc)}
            )

    sp = Path(SCRATCHPAD_PATH)
    scratchpad_section = StatusScratchpadSection(
        path=str(sp),
        exists=sp.exists(),
        writable=os.access(sp, os.W_OK) if sp.exists() else False,
        size_bytes=sp.stat().st_size if sp.exists() else 0,
    )

    overall = "ok"
    if not scratchpad_section.writable:
        overall = "degraded"
    if not notion_section.configured:
        overall = "degraded"

    return StatusResponse(
        status=overall,
        service="rb_vps_backend",
        version=app.version,
        memory=memory_section,
        notion=notion_section,
        scratchpad=scratchpad_section,
    )


@app.get("/api/v1/orca/scratchpad/pending", response_model=PendingSyncResponse)
def get_pending_sync(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> PendingSyncResponse:
    """Inspecciona la cola de eventos pendientes de sincronizar con Notion."""
    pending = memory_mgr.scratchpad.get("notion_sync_pending", []) or []
    items: list[PendingItem] = []
    timestamps: list[str] = []
    for ev in pending:
        ts = ev.get("timestamp") if isinstance(ev, dict) else None
        if ts:
            timestamps.append(ts)
        items.append(
            PendingItem(
                type=ev.get("type", "<unknown>") if isinstance(ev, dict) else "<unknown>",
                payload=ev.get("payload", {}) if isinstance(ev, dict) else {},
                attempts=ev.get("attempts", 0) if isinstance(ev, dict) else 0,
                enqueued_at=ts,
                agent_id=ev.get("agent_id") if isinstance(ev, dict) else None,
            )
        )
    return PendingSyncResponse(
        count=len(items),
        items=items,
        oldest_enqueued_at=min(timestamps) if timestamps else None,
        newest_enqueued_at=max(timestamps) if timestamps else None,
    )


@app.post("/api/v1/orca/scratchpad/append", response_model=ScratchpadAppendResponse)
def append_to_scratchpad(
    event: ScratchpadEventInput,
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> ScratchpadAppendResponse:
    """Inyecta un evento al scratchpad.

    - Si `event_type` esta en EVENT_TO_NOTION: delega a `sync_mgr.push_event`,
      que se encarga de (a) append al event_log, (b) encolar y (c) sincronizar.
    - Si no esta mapeado: solo append al event_log (sin Notion).
    """
    timestamp = event.timestamp or _now_iso()
    enriched_payload = dict(event.payload)
    if event.agent_id:
        enriched_payload.setdefault("agent_id", event.agent_id)

    enqueued = False
    synced = False
    detail: str | None = None
    local_persisted = True

    if event.event_type in EVENT_TO_NOTION:
        enqueued = True
        if sync_mgr is not None and sync_mgr.notion_reachable:
            try:
                sync_result = sync_mgr.push_event(event.event_type, enriched_payload)
                synced = bool(sync_result.get("notion_synced"))
                local_persisted = bool(sync_result.get("local_persisted", True))
                if not synced:
                    detail = str(sync_result.get("error") or "sync_failed")
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
        else:
            # Encolar localmente para flush posterior
            if sync_mgr is not None:
                sync_mgr._memory.append_event(event.event_type, enriched_payload)
                sync_mgr._memory.enqueue_notion_sync({
                    "type": event.event_type,
                    "payload": enriched_payload,
                    "attempts": 0,
                })
            else:
                memory_mgr.append_event(event.event_type, enriched_payload)
            detail = "notion_unreachable_or_unconfigured"
    else:
        memory_mgr.append_event(event.event_type, enriched_payload)
        detail = "event_type_not_synced_to_notion"

    return ScratchpadAppendResponse(
        status="synced" if synced else "appended",
        event_type=event.event_type,
        local_persisted=local_persisted,
        enqueued_for_notion=enqueued,
        agent_id=event.agent_id,
        timestamp=timestamp,
        detail=detail,
    )


@app.post("/api/v1/orca/webhook/trigger", response_model=WebhookTriggerResponse)
def webhook_trigger(
    body: WebhookTriggerInput,
    background_tasks: BackgroundTasks,
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> JSONResponse:
    """Dispara acciones orquestadas sobre Notion / sync.

    Acciones soportadas:
        - flush: intenta drenar la cola de pendientes.
        - hydrate: carga el estado activo de Notion al scratchpad.
        - sync_event: procesa `payload` como un evento (debe incluir `event_type`).
        - process_approved: Sprint 6: dispara el pipeline completo
          (scripts/run_hybrid_squad.py --mode=process-approved) en
          BackgroundTasks. Responde 200 inmediato para no bloquear a
          Notion. El payload puede incluir `page_ids` (lista de UUIDs) o
          `all_approved: true` para procesar todas las tarjetas en
          estado Aprobado. Devuelve JSON con
          `{"status": "processing", "message": "Pipeline activado
          en segundo plano", "action": "process_approved", ...}`.
    """
    if sync_mgr is None:
        raise HTTPException(
            status_code=503,
            detail="SyncManager no inicializado (NOTION_API_KEY ausente).",
        )

    action = body.action
    payload = body.payload

    try:
        if action == "flush":
            summary = sync_mgr.flush_pending()
            return WebhookTriggerResponse(
                status="ok",
                action=action,
                detail="Cola de sincronizacion procesada.",
                result=summary,
            )

        if action == "hydrate":
            hints = payload.get("hints") or ["Tareas"]
            hydrated = sync_mgr.hydrate_from_notion(hints)
            return WebhookTriggerResponse(
                status="ok",
                action=action,
                detail=f"Hidratado desde {len(hydrated)} database(s).",
                result={"databases": list(hydrated.keys()), "counts": {k: len(v) for k, v in hydrated.items()}},
            )

        if action == "sync_event":
            event_type = payload.get("event_type")
            if not event_type:
                raise HTTPException(status_code=400, detail="payload.event_type requerido.")
            event_payload = {k: v for k, v in payload.items() if k != "event_type"}
            sync_result = sync_mgr.push_event(event_type, event_payload)
            return WebhookTriggerResponse(
                status="ok" if sync_result.get("notion_synced") else "noop",
                action=action,
                detail="Sincronizacion procesada.",
                result=sync_result,
            )

        if action == "process_approved":
            # Sprint 6: dispara el pipeline completo en BackgroundTasks
            # para no bloquear la conexion HTTP de Notion.
            page_ids = payload.get("page_ids") or []
            all_approved = bool(payload.get("all_approved", False))
            background_tasks.add_task(
                _run_process_approved_pipeline,
                page_ids=page_ids,
                all_approved=all_approved,
            )
            return JSONResponse(
                status_code=200,
                content={
                    "status": "processing",
                    "message": "Pipeline activado en segundo plano",
                    "action": action,
                    "page_ids": page_ids,
                    "all_approved": all_approved,
                },
            )

        raise HTTPException(status_code=400, detail=f"action no soportada: {action!r}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("webhook_trigger.error action=%s", action)
        raise HTTPException(status_code=500, detail=f"Error procesando webhook: {exc}") from exc


# =============================================================================
# Endpoints existentes (migrados a la nueva auth)
# =============================================================================

def _run_process_approved_pipeline(page_ids, all_approved):
    """Sprint 6: ejecuta el pipeline del Squad en segundo plano.

    Dispara scripts/run_hybrid_squad.py en modo --mode=process-approved.
    Si page_ids viene vacio y all_approved=True, procesa TODAS las tarjetas
    en estado Aprobado en Notion. Si page_ids viene con IDs especificos,
    procesa solo esas.

    El resultado se loguea para que el sistema principal pueda revisarlo.
    Falla silenciosamente en background (la excepcion se loguea pero no
    se propaga).
    """
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    script = project_root / "scripts" / "run_hybrid_squad.py"
    log_path = project_root / "logs" / "pipeline_process_approved.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["python3", str(script), "--mode=process-approved"]
    if all_approved:
        cmd.append("--all-approved")
    elif page_ids:
        # Sprint 7: usar --page-ids (plural) con IDs separados por coma
        cmd.extend(["--page-ids", ",".join(page_ids[:5])])

    logger.info(
        "BackgroundTask: lanzando pipeline. cmd=%s log=%s",
        " ".join(cmd), str(log_path),
    )
    try:
        with open(log_path, "a", encoding="utf-8") as logf:
            process = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdout=logf,
                stderr=subprocess.STDOUT,
                env={**os.environ},
            )
        logger.info("BackgroundTask: pipeline lanzado. PID=%s", process.pid)
    except Exception as exc:
        logger.exception("BackgroundTask: fallo al lanzar pipeline. err=%s", exc)


@app.post("/api/v1/orca/execute")
def execute_agent_task(
    payload: AgentTaskRequest,
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> dict:
    try:
        result_text = memory_mgr.run_agent_task(
            system_prompt_agent=payload.system_prompt,
            user_input=payload.user_command,
        )
        return {
            "status": "success",
            "agent_id": payload.agent_id,
            "result": result_text,
            "current_fase": memory_mgr.scratchpad.get("fase_actual"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error ejecutando tarea: {exc}") from exc


@app.get("/api/v1/orca/memory")
def get_current_memory(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> dict:
    return memory_mgr.scratchpad


@app.post("/api/v1/orca/sync/to-notion")
def sync_event_to_notion(
    payload: EventRequest,
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> JSONResponse:
    if sync_mgr is None:
        raise HTTPException(
            status_code=503,
            detail="SyncManager no inicializado (NOTION_API_KEY ausente).",
        )
    result = sync_mgr.push_event(payload.event_type, payload.payload)
    status_code = 200 if result.get("notion_synced") else 202
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/v1/orca/sync/from-notion")
def hydrate_from_notion(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> dict:
    if sync_mgr is None:
        raise HTTPException(
            status_code=503,
            detail="SyncManager no inicializado (NOTION_API_KEY ausente).",
        )
    hydrated = sync_mgr.hydrate_from_notion(["Tareas"])
    return {"status": "ok", "hydrated_keys": list(hydrated.keys())}


@app.post("/api/v1/orca/sync/flush")
def flush_pending(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> dict:
    if sync_mgr is None:
        raise HTTPException(
            status_code=503,
            detail="SyncManager no inicializado (NOTION_API_KEY ausente).",
        )
    summary = sync_mgr.flush_pending()
    return {"status": "ok", **summary}


@app.get("/api/v1/orca/cache/stats")
def cache_stats(
    _api_key: Annotated[str, Depends(verify_orca_api_key)],
) -> dict:
    if sync_mgr is None:
        raise HTTPException(
            status_code=503,
            detail="SyncManager no inicializado (NOTION_API_KEY ausente).",
        )
    stats = sync_mgr._service.cache.stats()
    return {
        "hits": stats.hits,
        "misses": stats.misses,
        "size": stats.size,
        "ttl_seconds": stats.ttl_seconds,
        "hit_ratio": round(stats.hit_ratio, 4),
    }
