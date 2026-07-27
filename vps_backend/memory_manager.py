"""memory_manager.py - Gestor de Memoria Jerarquica con Rolling Scratchpad.

Sprint 2: integra escritura atomica (filelock + os.replace), rolling por tamano
y hooks para sincronizacion bidireccional con Notion.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

import openai

from scratchpad_io import ScratchpadIO

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRATCHPAD_FILE = os.path.join(BASE_DIR, "agent_scratchpad.json")
DEFAULT_MASTER_CONTEXT_FILE = os.path.join(BASE_DIR, "rompiendo_barreras_master_context.md")

DEFAULT_MAX_SCRATCHPAD_BYTES = 50_000
DEFAULT_MAX_DECISIONES = 10
DEFAULT_MAX_EVENTOS = 100


class HierarchicalMemoryManager:
    """Memoria en 2 niveles:
    - Nivel 1: Contexto Maestro Estatico (Knowledge Base).
    - Nivel 2: Estado Dinamico Comprimido (Rolling Scratchpad en JSON).

    Sprint 2: las escrituras son atomicas (filelock + os.replace) y el scratchpad
    rota automaticamente para no exceder el tamano maximo.
    """

    def __init__(
        self,
        api_key: str,
        primary_model: str = "gpt-4o",
        compression_model: str = "gpt-4o-mini",
        scratchpad_path: str = DEFAULT_SCRATCHPAD_FILE,
        master_context_path: str = DEFAULT_MASTER_CONTEXT_FILE,
        max_scratchpad_bytes: int = DEFAULT_MAX_SCRATCHPAD_BYTES,
        max_decisiones: int = DEFAULT_MAX_DECISIONES,
        max_eventos: int = DEFAULT_MAX_EVENTOS,
    ) -> None:
        self.client = openai.OpenAI(api_key=api_key)
        self.primary_model = primary_model
        self.compression_model = compression_model
        self.max_scratchpad_bytes = max_scratchpad_bytes
        self.max_decisiones = max_decisiones
        self.max_eventos = max_eventos

        self.master_context_path = master_context_path
        self.master_context = self.load_master_context()

        self._io = ScratchpadIO(scratchpad_path)
        loaded = self._io.read() if self._io.exists() else {}
        self.scratchpad = loaded if loaded else self._bootstrap_scratchpad()

    @staticmethod
    def _bootstrap_scratchpad() -> dict[str, Any]:
        return {
            "proyecto": "Rompiendo Barreras",
            "fase_actual": "Inicial",
            "objetivo_activo": "",
            "decisiones_clave": [],
            "hitos_completados": [],
            "hitos_pendientes": [],
            "contexto_dinamico": "",
            "event_log": [],
            "notion_sync_pending": [],
        }

    def load_master_context(self) -> str:
        if os.path.exists(self.master_context_path):
            try:
                with open(self.master_context_path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as exc:
                logger.warning("memory_manager.master_context.read_error err=%s", exc)
        return "Ecosistema Rompiendo Barreras - Formacion de Emprendedores Cristianos."

    def load_scratchpad(self) -> dict[str, Any]:
        return self._io.read()

    def save_scratchpad(self) -> None:
        self._rotate_if_needed()
        self._io.write(self.scratchpad)
        logger.info(
            "memory_manager.scratchpad.saved bytes=%d eventos=%d decisiones=%d",
            self._io.size_bytes(),
            len(self.scratchpad.get("event_log", [])),
            len(self.scratchpad.get("decisiones_clave", [])),
        )

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Agrega un evento al rolling log. Pensado para ser llamado por
        el MemorySyncManager antes de encolar la sincronizacion a Notion."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self.scratchpad.setdefault("event_log", []).append(event)
        self.save_scratchpad()

    def enqueue_notion_sync(self, event: dict[str, Any]) -> None:
        """Encola un evento para sincronizarse con Notion cuando sea posible."""
        self.scratchpad.setdefault("notion_sync_pending", []).append(event)
        self._io.write(self.scratchpad)

    def dequeue_notion_synced(self, event: dict[str, Any]) -> None:
        """Quita un evento de la cola de pendientes tras sync exitoso."""
        pending = self.scratchpad.get("notion_sync_pending", [])
        self.scratchpad["notion_sync_pending"] = [
            e for e in pending if e is not event
        ]
        self._io.write(self.scratchpad)

    def _rotate_if_needed(self) -> None:
        """Rolling: si el JSON crece demasiado, recorta colas largas."""
        size = self._io.size_bytes()
        if size <= self.max_scratchpad_bytes:
            return

        log = self.scratchpad.get("event_log", [])
        if len(log) > self.max_eventos:
            self.scratchpad["event_log"] = log[-self.max_eventos:]
            logger.info(
                "memory_manager.rotate event_log %d -> %d",
                len(log), len(self.scratchpad["event_log"]),
            )

        decisiones = self.scratchpad.get("decisiones_clave", [])
        if len(decisiones) > self.max_decisiones:
            self.scratchpad["decisiones_clave"] = decisiones[-self.max_decisiones:]
            logger.info(
                "memory_manager.rotate decisiones %d -> %d",
                len(decisiones), len(self.scratchpad["decisiones_clave"]),
            )

        contexto = self.scratchpad.get("contexto_dinamico", "")
        if len(contexto) > 4000:
            self.scratchpad["contexto_dinamico"] = contexto[-4000:]
            logger.info("memory_manager.rotate contexto_dinamico truncado a 4000 chars")

        pending = self.scratchpad.get("notion_sync_pending", [])
        if len(pending) > self.max_eventos:
            self.scratchpad["notion_sync_pending"] = pending[-self.max_eventos:]

    def build_optimized_messages(
        self, system_prompt_agent: str, user_input: str
    ) -> list[dict[str, str]]:
        memory_summary = (
            f"=== ESTADO DINAMICO ACTUAL (ROLLING SCRATCHPAD) ===\n"
            f"FASE PROYECTO: {self.scratchpad.get('fase_actual')}\n"
            f"OBJETIVO ACTIVO: {self.scratchpad.get('objetivo_activo')}\n"
            f"DECISIONES VIGENTES: {json.dumps(self.scratchpad.get('decisiones_clave'), ensure_ascii=False)}\n"
            f"HITOS PENDIENTES: {json.dumps(self.scratchpad.get('hitos_pendientes'), ensure_ascii=False)}\n"
            f"CONTEXTO DINAMICO: {self.scratchpad.get('contexto_dinamico')}\n"
            f"PENDING SYNC: {len(self.scratchpad.get('notion_sync_pending', []))} eventos\n"
            f"=================================================="
        )
        return [
            {"role": "system", "content": system_prompt_agent},
            {"role": "system", "content": f"=== BASE DE CONOCIMIENTO CENTRAL (ROMPIENDO BARRERAS) ===\n{self.master_context}"},
            {"role": "system", "content": memory_summary},
            {"role": "user", "content": user_input},
        ]

    def run_agent_task(self, system_prompt_agent: str, user_input: str) -> str:
        messages = self.build_optimized_messages(system_prompt_agent, user_input)
        response = self.client.chat.completions.create(
            model=self.primary_model,
            messages=messages,
            temperature=0.2,
        )
        agent_output = response.choices[0].message.content
        self.auto_compact_state(user_input, agent_output)
        return agent_output

    def auto_compact_state(self, last_input: str, last_output: str) -> None:
        compaction_prompt = [
            {
                "role": "system",
                "content": (
                    "Eres el Compresor de Memoria del proyecto Rompiendo Barreras. "
                    "Devuelve el JSON de memoria actualizado preservando decisiones "
                    "clave y descartando detalles irrelevantes."
                ),
            },
            {"role": "system", "content": f"MEMORIA ACTUAL: {json.dumps(self.scratchpad, ensure_ascii=False)}"},
            {"role": "user", "content": f"ULTIMO COMANDO: {last_input}\nULTIMA RESPUESTA: {last_output}\nDevuelve solo el JSON."},
        ]
        try:
            res = self.client.chat.completions.create(
                model=self.compression_model,
                messages=compaction_prompt,
                response_format={"type": "json_object"},
            )
            updated = json.loads(res.choices[0].message.content)
            self.scratchpad = updated
            self.save_scratchpad()
            logger.info("memory_manager.auto_compact ok")
        except Exception as exc:
            logger.warning("memory_manager.auto_compact.error err=%s", exc)
