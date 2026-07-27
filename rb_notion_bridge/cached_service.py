"""CachedSchemaService: devuelve un NotionBridgeService por database_id
usando SchemaCache para evitar fetch repetido del schema.
"""

from __future__ import annotations

import logging
from typing import Any

from .cache import SchemaCache
from .client import NotionClient
from .service import NotionBridgeService
from .transformer import NotionTransformer

logger = logging.getLogger(__name__)


class CachedSchemaService:
    """Fabrica de NotionBridgeService con cache de schemas."""

    def __init__(self, client: NotionClient, cache: SchemaCache | None = None) -> None:
        self._client = client
        self._cache = cache or SchemaCache()
        self._services: dict[str, NotionBridgeService] = {}

    @property
    def cache(self) -> SchemaCache:
        return self._cache

    def get_service(self, database_id: str) -> NotionBridgeService:
        """Devuelve (o construye) un NotionBridgeService para el database_id."""
        if database_id in self._services:
            self._cache.record_hit(database_id)
            return self._services[database_id]

        self._cache.record_miss(database_id)
        database = self._client.retrieve_database(database_id)
        schema = database.get("properties") or {}
        if not schema:
            raise ValueError(
                f"database_id={database_id} no devolvio 'properties' validas"
            )
        self._cache.set(database_id, schema)
        transformer = NotionTransformer(schema=schema)
        service = NotionBridgeService(self._client, transformer)
        self._services[database_id] = service
        return service

    def invalidate(self, database_id: str | None = None) -> int:
        """Invalida la entrada (o todas) y purga los services cacheados."""
        if database_id is not None:
            self._services.pop(database_id, None)
        else:
            self._services.clear()
        return self._cache.invalidate(database_id)
