"""Cache en memoria de schemas de Notion databases con TTL.

Evita round-trips a la API cuando varios servicios consultan el mismo
database en un periodo corto. Es un cache de proceso (no distribuido).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    size: int
    ttl_seconds: float

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class SchemaCache:
    """Cache {database_id -> (schema_dict, timestamp)} con TTL."""

    def __init__(self, ttl_seconds: float = 900.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser > 0")
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[dict[str, Any], float]] = {}
        self._hits = 0
        self._misses = 0

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def get(self, database_id: str) -> dict[str, Any] | None:
        entry = self._store.get(database_id)
        if entry is None:
            return None
        schema, ts = entry
        if (time.time() - ts) > self._ttl:
            logger.info("schema_cache.expired database_id=%s", database_id)
            self._store.pop(database_id, None)
            return None
        return schema

    def set(self, database_id: str, schema: dict[str, Any]) -> None:
        self._store[database_id] = (schema, time.time())
        logger.info("schema_cache.set database_id=%s", database_id)

    def invalidate(self, database_id: str | None = None) -> int:
        if database_id is None:
            count = len(self._store)
            self._store.clear()
            logger.info("schema_cache.flush removed=%d", count)
            return count
        removed = self._store.pop(database_id, None)
        if removed is not None:
            logger.info("schema_cache.invalidate database_id=%s", database_id)
            return 1
        return 0

    def record_hit(self, database_id: str) -> None:
        self._hits += 1
        logger.info("schema_cache.hit database_id=%s", database_id)

    def record_miss(self, database_id: str) -> None:
        self._misses += 1
        logger.info("schema_cache.miss database_id=%s", database_id)

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            size=len(self._store),
            ttl_seconds=self._ttl,
        )
