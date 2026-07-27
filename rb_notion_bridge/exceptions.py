"""Jerarquia de excepciones del NotionBridge.

Permite que los agentes de Orca capturen errores especificos y reaccionen
correctamente (e.g. reintentar vs. escalar vs. fallar).
"""

from __future__ import annotations


class NotionBridgeError(Exception):
    """Excepcion base del bridge. Capturarla = error de la integracion."""


class NotionAuthError(NotionBridgeError):
    """401 o 403: token invalido, expirado, o la integracion no esta compartida
    con la pagina/database objetivo. NO se reintenta: requiere intervencion."""


class NotionNotFoundError(NotionBridgeError):
    """404: el recurso (pagina o database) no existe o la integracion no tiene
    acceso. NO se reintenta."""


class NotionValidationError(NotionBridgeError):
    """400: payload malformado, propiedad requerida faltante, o tipo
    incorrecto. NO se reintenta: el caller debe corregir el payload."""


class NotionRateLimitError(NotionBridgeError):
    """429: limite de tasa de Notion excedido. Se reintenta respetando
    el header Retry-After."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotionServerError(NotionBridgeError):
    """5xx: error transitorio del lado de Notion. Se reintenta con backoff
    exponencial hasta max_retries; si persiste, se propaga al caller."""
