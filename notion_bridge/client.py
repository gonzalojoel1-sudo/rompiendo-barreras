"""Capa cliente: wrapper del SDK oficial notion-client con manejo de
errores tipados, retry ante 429/5xx y backoff exponencial.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

from .config import NotionBridgeConfig
from .exceptions import (
    NotionAuthError,
    NotionBridgeError,
    NotionNotFoundError,
    NotionRateLimitError,
    NotionServerError,
    NotionValidationError,
)

logger = logging.getLogger(__name__)


_STATUS_TO_EXC: dict[int, type[NotionBridgeError]] = {
    400: NotionValidationError,
    401: NotionAuthError,
    403: NotionAuthError,
    404: NotionNotFoundError,
}


class NotionClient:
    """Wrapper del SDK de Notion.

    Expone metodos de alto nivel (query_database, create_page, update_page,
    retrieve_page) y un atributo `raw_client` para acceso directo al SDK
    (necesario para `databases.retrieve` que alimenta al transformer).
    """

    def __init__(self, config: NotionBridgeConfig) -> None:
        self._config = config
        self.raw_client = Client(
            auth=config.api_key,
            notion_version=config.api_version,
            timeout_ms=int(config.timeout * 1000),
        )
        logger.info(
            "notion_bridge.client.init api_version=%s timeout=%.1fs max_retries=%d key=%s",
            config.api_version,
            config.timeout,
            config.max_retries,
            config.masked_api_key(),
        )

    def query_database(
        self,
        database_id: str,
        filter: dict | None = None,
        sorts: list[dict] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"database_id": database_id, "page_size": page_size}
        if filter is not None:
            kwargs["filter"] = filter
        if sorts is not None:
            kwargs["sorts"] = sorts
        if start_cursor is not None:
            kwargs["start_cursor"] = start_cursor
        return self._call("databases.query", **kwargs)

    def create_page(self, parent: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
        return self._call("pages.create", parent=parent, properties=properties)

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._call("pages.update", page_id=page_id, properties=properties)

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._call("pages.retrieve", page_id=page_id)

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self._call("databases.retrieve", database_id=database_id)

    def _call(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Ejecuta una operacion del SDK con reintentos y mapeo de errores."""
        namespace, method_name = operation.split(".", 1)
        method = getattr(getattr(self.raw_client, namespace), method_name)

        last_exc: NotionBridgeError | None = None
        attempts = self._config.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = method(**kwargs)
                if hasattr(response, "to_dict"):
                    return response.to_dict()
                return dict(response) if isinstance(response, dict) else response
            except APIResponseError as exc:
                status = self._extract_status(exc)
                body = self._extract_body(exc)
                retry_after = self._extract_retry_after(exc)

                logger.warning(
                    "notion_bridge.api_call op=%s attempt=%d/%d status=%d retry_after=%s body=%s",
                    operation, attempt, attempts, status, retry_after, body,
                )

                if status in _STATUS_TO_EXC:
                    exc_cls = _STATUS_TO_EXC[status]
                    raise exc_cls(f"Notion API {status} en {operation}: {body}") from exc

                if status == 429:
                    last_exc = NotionRateLimitError(
                        f"Rate limit en {operation}: {body}", retry_after=retry_after
                    )
                    delay = retry_after if retry_after is not None else self._backoff(attempt)
                elif 500 <= status < 600:
                    last_exc = NotionServerError(
                        f"Server error {status} en {operation}: {body}"
                    )
                    delay = self._backoff(attempt)
                else:
                    last_exc = NotionBridgeError(
                        f"Error inesperado {status} en {operation}: {body}"
                    )
                    delay = self._backoff(attempt)

                if attempt >= attempts:
                    raise last_exc from exc
                time.sleep(delay)
            except (ConnectionError, TimeoutError) as exc:
                last_exc = NotionServerError(
                    f"Error de red en {operation}: {exc}"
                )
                if attempt >= attempts:
                    raise last_exc from exc
                time.sleep(self._backoff(attempt))

        raise last_exc or NotionServerError("Fallo desconocido despues de reintentos")

    def _backoff(self, attempt: int) -> float:
        delay = self._config.backoff_base * (2 ** (attempt - 1))
        return min(delay, self._config.backoff_max)

    @staticmethod
    def _extract_status(exc: APIResponseError) -> int:
        status = getattr(exc, "status", None)
        if isinstance(status, int):
            return status
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code.startswith("unknown_error"):
            return 500
        return 500

    @staticmethod
    def _extract_body(exc: APIResponseError) -> str:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            return str(body.get("message") or body)
        return str(body or exc)

    @staticmethod
    def _extract_retry_after(exc: APIResponseError) -> float | None:
        headers = getattr(exc, "headers", None) or {}
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
