"""Capa de servicio: API de alto nivel que consumen los agentes de Orca.

Encapsula la logica de paginacion, mapeo de payloads y emision de logs
estructurados (action, payload_size, status, duration_ms).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .client import NotionClient
from .exceptions import NotionValidationError
from .transformer import NotionTransformer

logger = logging.getLogger(__name__)


class NotionBridgeService:
    """API publica del bridge.

    Tipicamente se construye asi:
        client = NotionClient(NotionBridgeConfig.from_env())
        database = client.retrieve_database(database_id)
        transformer = NotionTransformer.from_database(database)
        service = NotionBridgeService(client, transformer)
    """

    def __init__(
        self,
        client: NotionClient,
        transformer: NotionTransformer,
    ) -> None:
        self._client = client
        self._transformer = transformer

    def fetch_database_items(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Lee todas las paginas de un database (pagina automaticamente).

        Args:
            database_id: ID de la database a consultar.
            filter: Filtro Notion (mismo formato que la API).
            sorts: Lista de sorts Notion.
            page_size: Tamano de pagina (max 100).

        Returns:
            Lista de paginas (cada pagina es un dict de Notion).
        """
        action = "fetch_database_items"
        start = time.perf_counter()
        all_results: list[dict[str, Any]] = []
        start_cursor: str | None = None
        page_count = 0

        try:
            while True:
                page_count += 1
                response = self._client.query_database(
                    database_id=database_id,
                    filter=filter,
                    sorts=sorts,
                    page_size=page_size,
                    start_cursor=start_cursor,
                )
                all_results.extend(response.get("results", []))
                if not response.get("has_more"):
                    break
                start_cursor = response.get("next_cursor")
                if start_cursor is None and response.get("has_more"):
                    logger.warning("notion_service: has_more=True but cursor=None")
                    break
                if not start_cursor:
                    break

            self._log(
                action, "success",
                database_id=database_id, count=len(all_results),
                pages=page_count, duration_ms=self._elapsed_ms(start),
                filter_present=filter is not None,
                sorts_present=sorts is not None,
            )
            return all_results
        except Exception as exc:
            self._log(
                action, "error",
                database_id=database_id, error=type(exc).__name__,
                duration_ms=self._elapsed_ms(start),
            )
            raise

    def create_notion_page(
        self,
        database_id: str,
        orca_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Crea una pagina en `database_id` a partir de un payload Orca (flat dict)."""
        action = "create_notion_page"
        start = time.perf_counter()
        if not orca_data:
            raise NotionValidationError("orca_data vacio: nada que crear.")

        properties = self._transformer.to_notion_properties(orca_data)
        parent = {"database_id": database_id}
        payload_size = len(json.dumps(orca_data, ensure_ascii=False))

        try:
            response = self._client.create_page(parent=parent, properties=properties)
            self._log(
                action, "success",
                database_id=database_id, page_id=response.get("id"),
                payload_size=payload_size, properties=len(properties),
                duration_ms=self._elapsed_ms(start),
            )
            return response
        except Exception as exc:
            self._log(
                action, "error",
                database_id=database_id, payload_size=payload_size,
                error=type(exc).__name__, duration_ms=self._elapsed_ms(start),
            )
            raise

    def update_notion_page(
        self,
        page_id: str,
        orca_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Actualiza las propiedades de una pagina existente."""
        action = "update_notion_page"
        start = time.perf_counter()
        if not orca_data:
            raise NotionValidationError("orca_data vacio: nada que actualizar.")

        properties = self._transformer.to_notion_properties(orca_data)
        payload_size = len(json.dumps(orca_data, ensure_ascii=False))

        try:
            response = self._client.update_page(page_id=page_id, properties=properties)
            self._log(
                action, "success",
                page_id=page_id, payload_size=payload_size,
                properties=len(properties), duration_ms=self._elapsed_ms(start),
            )
            return response
        except Exception as exc:
            self._log(
                action, "error",
                page_id=page_id, payload_size=payload_size,
                error=type(exc).__name__, duration_ms=self._elapsed_ms(start),
            )
            raise

    def get_property_value(self, page: dict[str, Any], property_name: str) -> Any:
        """Helper para extraer un valor de una pagina Notion sin conocer su tipo."""
        prop = page.get("properties", {}).get(property_name)
        if not prop:
            return None
        prop_type = prop.get("type")
        if not prop_type:
            return None
        return self._transformer._unwrap_value(prop_type, prop)

    @staticmethod
    def _log(action: str, status: str, **fields: Any) -> None:
        extra = {"action": action, "status": status, **fields}
        level = logging.INFO if status == "success" else logging.WARNING
        logger.log(level, f"notion_bridge.{action} status={status}", extra=extra)

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 2)
