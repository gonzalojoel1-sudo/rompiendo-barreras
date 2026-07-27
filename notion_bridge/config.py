"""Configuracion del NotionBridge.

Carga variables de entorno y las valida en el arranque. La instancia es
inmutable (frozen dataclass) para evitar mutaciones accidentales en runtime.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotionBridgeConfig:
    """Configuracion validada e inmutable del bridge."""

    api_key: str
    api_version: str
    timeout: float
    max_retries: int
    backoff_base: float
    backoff_max: float

    def masked_api_key(self) -> str:
        if len(self.api_key) < 12:
            return "***"
        return f"{self.api_key[:8]}...{self.api_key[-4:]}"

    @classmethod
    def from_env(cls, prefix: str = "NOTION_") -> "NotionBridgeConfig":
        """Lee las variables de entorno (prefijo NOTION_ por defecto) y
        devuelve una instancia validada. Falla rapido si falta lo esencial.
        """
        api_key = os.getenv(f"{prefix}API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                f"Variable de entorno {prefix}API_KEY es obligatoria. "
                "Suministra un token de integracion de Notion valido."
            )
        if not api_key.startswith("ntn_") and not api_key.startswith("secret_"):
            logger.warning(
                "El token de Notion no tiene el formato esperado (ntn_/secret_). "
                "Verifica que sea correcto."
            )

        timeout = _env_float(prefix, "TIMEOUT", default=30.0)
        max_retries = _env_int(prefix, "MAX_RETRIES", default=3)
        backoff_base = _env_float(prefix, "BACKOFF_BASE", default=0.5)
        backoff_max = _env_float(prefix, "BACKOFF_MAX", default=8.0)

        if max_retries < 0:
            raise ValueError(f"{prefix}MAX_RETRIES debe ser >= 0")
        if timeout <= 0:
            raise ValueError(f"{prefix}TIMEOUT debe ser > 0")
        if backoff_base <= 0 or backoff_max <= 0:
            raise ValueError(f"{prefix}BACKOFF_BASE y BACKOFF_MAX deben ser > 0")

        return cls(
            api_key=api_key,
            api_version=os.getenv(f"{prefix}API_VERSION", "2022-06-28"),
            timeout=timeout,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )


def _env_float(prefix: str, suffix: str, default: float) -> float:
    raw = os.getenv(f"{prefix}{suffix}")
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{prefix}{suffix} debe ser numerico, recibido: {raw!r}") from exc


def _env_int(prefix: str, suffix: str, default: int) -> int:
    raw = os.getenv(f"{prefix}{suffix}")
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{prefix}{suffix} debe ser entero, recibido: {raw!r}") from exc
