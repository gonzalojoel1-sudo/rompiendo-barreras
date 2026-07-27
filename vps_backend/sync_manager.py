"""sync_manager.py - Sincronizacion bidireccional entre agent_scratchpad.json
y las bases de datos de Notion.

Mapea eventos del scratchpad a operaciones del NotionBridgeService.
Maneja la cola de pendientes y recovery ante fallos de red.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from notion_bridge import CachedSchemaService, NotionClient
from notion_bridge.config import NotionBridgeConfig

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"

# Mapeo declarativo: event_type -> (manifest_label_hint, mode, field_map)
#   mode = "create" | "update"
#   field_map para update: {payload_key -> property_name}
#   field_map para create: {payload_key -> property_name} (todos requeridos)
EVENT_TO_NOTION: dict[str, dict[str, Any]] = {
    "TASK_STATUS_CHANGED": {
        "manifest_hint": "Tareas",
        "mode": "update",
        "find_by": "page_id",
        "field_map": {"status": "Estado"},
    },
    "HITO_COMPLETADO": {
        "manifest_hint": "Tareas",
        "mode": "create",
        "field_map": {
            "titulo": "Mision_Tarea",
            "responsable": "Responsable",
            "estado": "Estado",
            "prioridad": "Prioridad",
        },
    },
    "STUDENT_ENROLLED": {
        "manifest_hint": "Control",
        "mode": "create",
        "field_map": {
            "nombre": "Nombre_Alumno",
            "email": "Email",
            "plan": "Plan_Suscripcion",
        },
    },
    "LESSON_SCRIPT_UPDATED": {
        "manifest_hint": "Fábrica",
        "mode": "update",
        "find_by": "page_id",
        "field_map": {"status": "Estado_Guion"},
    },
    "AD_LAUNCHED": {
        "manifest_hint": "Anuncios",
        "mode": "create",
        "field_map": {
            "nombre": "Nombre_Anuncio",
            "estado": "Estado_Campana",
        },
    },
}


class MemorySyncManager:
    """Orquesta la sincronizacion memoria local <-> Notion."""

    def __init__(
        self,
        memory_manager: Any,
        cached_service: CachedSchemaService,
        manifest: list[dict[str, str]],
    ) -> None:
        self._memory = memory_manager
        self._service = cached_service
        self._manifest = manifest
        self._db_id_cache: dict[str, str] = {}
        self._notion_reachable = True

    @property
    def notion_reachable(self) -> bool:
        return self._notion_reachable

    def set_notion_reachable(self, value: bool) -> None:
        self._notion_reachable = value
        logger.warning("sync_manager.notion_reachable=%s", value)

    @classmethod
    def from_env(
        cls,
        memory_manager: Any,
        manifest_path: str | os.PathLike[str] = MANIFEST_PATH,
    ) -> "MemorySyncManager":
        """Constructor de conveniencia: lee config + manifest, arma el cache."""
        config = NotionBridgeConfig.from_env()
        client = NotionClient(config)
        cached_service = CachedSchemaService(client)
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        return cls(memory_manager, cached_service, manifest)

    def _resolve_database_id(self, manifest_hint: str) -> str:
        if manifest_hint in self._db_id_cache:
            return self._db_id_cache[manifest_hint]
        for entry in self._manifest:
            if manifest_hint in entry.get("label", ""):
                db_id = entry["id"]
                self._db_id_cache[manifest_hint] = db_id
                return db_id
        raise KeyError(f"Manifest no contiene ninguna DB con hint {manifest_hint!r}")

    def push_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persistir el evento localmente y sincronizar con Notion si esta
        alcanzable. Devuelve un resumen de la operacion."""
        event = {
            "type": event_type,
            "payload": payload,
            "attempts": 0,
        }
        self._memory.append_event(event_type, payload)
        self._memory.enqueue_notion_sync(event)

        result: dict[str, Any] = {
            "event": event_type,
            "local_persisted": True,
            "notion_synced": False,
            "notion_attempts": 0,
            "error": None,
        }

        if not self._notion_reachable:
            result["error"] = "notion_unreachable: encolado localmente"
            return result

        try:
            sync_result = self._sync_event_to_notion(event)
            result["notion_synced"] = True
            result["notion_result"] = sync_result
            self._memory.dequeue_notion_synced(event)
        except Exception as exc:
            event["attempts"] += 1
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["notion_attempts"] = event["attempts"]
            logger.warning("sync_manager.push_event.sync_failed err=%s", exc)

        return result

    def flush_pending(self) -> dict[str, int]:
        """Intenta sincronizar todos los eventos pendientes. Devuelve
        contadores {synced, failed, remaining}."""
        if not self._notion_reachable:
            return {"synced": 0, "failed": 0, "remaining": 0, "skipped": "unreachable"}

        pending = list(self._memory.scratchpad.get("notion_sync_pending", []))
        synced = 0
        failed = 0
        for event in pending:
            max_retries = 5
            backoff = 1
            for attempt in range(max_retries):
                try:
                    self._sync_event_to_notion(event)
                    self._memory.dequeue_notion_synced(event)
                    synced += 1
                    break
                except Exception as exc:
                    is_rate_limit = (
                        getattr(exc, "status", None) == 429
                        or "429" in str(exc)
                        or "rate limit" in str(exc).lower()
                    )
                    if is_rate_limit and attempt < max_retries - 1:
                        logger.warning("sync_manager.flush.rate_limited attempt=%d backoff=%ds", attempt + 1, backoff)
                        import time
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 60)
                    else:
                        event["attempts"] = event.get("attempts", 0) + 1
                        failed += 1
                        logger.warning("sync_manager.flush.event_failed err=%s", exc)
                        break

        remaining = len(self._memory.scratchpad.get("notion_sync_pending", []))
        logger.info(
            "sync_manager.flush summary synced=%d failed=%d remaining=%d",
            synced, failed, remaining,
        )
        return {"synced": synced, "failed": failed, "remaining": remaining}

    def hydrate_from_notion(
        self,
        manifest_hints: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Carga el estado activo de las DBs de Notion y lo refleja en el
        scratchpad (hitos_pendientes / hitos_completados)."""
        if not self._notion_reachable:
            logger.warning("sync_manager.hydrate.skipped reason=unreachable")
            return {}

        hints = manifest_hints or ["Tareas"]
        result: dict[str, list[dict[str, Any]]] = {}

        for hint in hints:
            try:
                db_id = self._resolve_database_id(hint)
                service = self._service.get_service(db_id)
                items = service.fetch_database_items(db_id, page_size=50)
            except Exception as exc:
                logger.warning("sync_manager.hydrate.db_failed hint=%s err=%s", hint, exc)
                result[hint] = []
                continue

            pendientes: list[str] = []
            completados: list[str] = []
            for item in items:
                title = service.get_property_value(item, "Mision_Tarea") or \
                        service.get_property_value(item, "Nombre_Clase") or \
                        service.get_property_value(item, "Nombre_Anuncio") or \
                        service.get_property_value(item, "Nombre_Alumno") or "<sin titulo>"
                status = service.get_property_value(item, "Estado") or \
                          service.get_property_value(item, "Estado_Guion") or \
                          service.get_property_value(item, "Estado_Campana") or \
                          service.get_property_value(item, "Estado_Hito_Semanal")
                if status and "complet" in str(status).lower():
                    completados.append(title)
                else:
                    pendientes.append(title)

            self._memory.scratchpad["hitos_pendientes"] = pendientes
            self._memory.scratchpad["hitos_completados"] = completados
            self._memory.scratchpad["fase_actual"] = (
                f"Hidratado desde Notion: {len(pendientes)} pendientes, "
                f"{len(completados)} completados"
            )
            self._memory.save_scratchpad()
            result[hint] = items
            logger.info(
                "sync_manager.hydrate.ok hint=%s items=%d",
                hint, len(items),
            )

        return result

    def _sync_event_to_notion(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event["type"]
        payload = event.get("payload", {})
        config = EVENT_TO_NOTION.get(event_type)
        if config is None:
            raise ValueError(f"event_type no soportado: {event_type!r}")

        db_id = self._resolve_database_id(config["manifest_hint"])
        service = self._service.get_service(db_id)
        mode = config["mode"]
        field_map: dict[str, str] = config["field_map"]

        if mode == "update":
            page_id = payload.get(config["find_by"]) or payload.get("page_id")
            if not page_id:
                raise ValueError(
                    f"evento {event_type!r} requiere {config['find_by']!r} en payload"
                )
            update_props = {field_map[k]: v for k, v in payload.items() if k in field_map}
            if not update_props:
                raise ValueError(f"evento {event_type!r} sin campos mapeables")
            return service.update_notion_page(page_id, update_props)

        if mode == "create":
            create_props = {field_map[k]: v for k, v in payload.items() if k in field_map}
            if not create_props:
                raise ValueError(f"evento {event_type!r} sin campos mapeables")
            return service.create_notion_page(db_id, create_props)

        raise ValueError(f"mode no soportado: {mode!r}")
