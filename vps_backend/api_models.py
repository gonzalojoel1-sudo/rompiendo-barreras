"""api_models.py - Esquemas Pydantic para la API REST v1.

Modelos de entrada y salida de los endpoints /api/v1/orca/*.
Validacion estricta en el borde (Pydantic v2) antes de tocar la memoria
o el SyncManager.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScratchpadEventInput(BaseModel):
    """Evento entrante al scratchpad desde un agente externo."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = Field(default=None, max_length=100)
    timestamp: str | None = Field(default=None, description="ISO 8601 opcional")


class ScratchpadAppendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["appended", "synced", "rejected"] = "appended"
    event_type: str
    local_persisted: bool
    enqueued_for_notion: bool
    agent_id: str | None = None
    timestamp: str
    detail: str | None = None


class PendingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    payload: dict[str, Any]
    attempts: int
    enqueued_at: str | None = None
    agent_id: str | None = None


class PendingSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    items: list[PendingItem]
    oldest_enqueued_at: str | None = None
    newest_enqueued_at: str | None = None


class WebhookTriggerInput(BaseModel):
    """Disparo de acciones sobre Notion / sync."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["flush", "hydrate", "sync_event", "process_approved"]
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookTriggerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error", "noop"] = "ok"
    action: str
    detail: str
    result: dict[str, Any] = Field(default_factory=dict)


class StatusMemorySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proyecto: str | None = None
    fase_actual: str | None = None
    objetivo_activo: str | None = None
    decisiones_count: int
    hitos_completados_count: int
    hitos_pendientes_count: int
    event_log_count: int
    pending_sync_count: int


class StatusNotionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    reachable: bool
    cache: dict[str, Any] | None = None


class StatusScratchpadSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    exists: bool
    writable: bool
    size_bytes: int


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "down"]
    service: str
    version: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    memory: StatusMemorySection
    notion: StatusNotionSection
    scratchpad: StatusScratchpadSection


class AgentTaskRequest(BaseModel):
    """Ejecuta una tarea en nombre de un agente de Orca."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field(..., min_length=1)
    user_command: str = Field(..., min_length=1)


class EventRequest(BaseModel):
    """Evento generico para /sync/to-notion (compatibilidad Sprint 2)."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
