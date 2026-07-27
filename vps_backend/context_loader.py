"""context_loader.py - Cargador del Búnker de Contexto de Rompiendo Barreras.

Lee los 5 archivos Markdown de `context_vault/` y los expone como:
  - load_context_vault()         -> dict {nombre_archivo: contenido}
  - get_unified_context_prompt()  -> string formateado listo para system prompt

Disenado para inyectar en las llamadas a LLMs del Squad de agentes.
Incluye:
  - LRU cache en memoria (evita releer disco en cada llamada)
  - Manejo defensivo de errores (no rompe el backend si falta el búnker)
  - Logging estructurado de cada operacion
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Path al Búnker de Contexto. Por defecto, la carpeta `context_vault/`
# en la raíz del proyecto. Se puede override via env var
# CONTEXT_VAULT_PATH si el búnker vive en otra ubicación (ej. tests).
# __file__ = vps_backend/context_loader.py
# parent.parent = raiz del proyecto (rompiendo-barreras/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VAULT_PATH = _PROJECT_ROOT / "context_vault"

# Orden canónico de los 5 archivos del Búnker. El orden importa porque
# define como se concatenan en el system prompt (manifiesto -> voz ->
# avatar -> producto -> ejemplos de oro).
CANONICAL_FILE_ORDER: list[str] = [
    "01_brand_manifesto",
    "02_tone_and_voice",
    "03_target_avatar",
    "04_product_matrix",
    "05_gold_standard_examples",
]

# Headers legibles para cada archivo cuando se concatenan en el prompt.
_FILE_HEADERS: dict[str, str] = {
    "01_brand_manifesto": "MANIFIESTO DE MARCA",
    "02_tone_and_voice": "TONO Y VOZ",
    "03_target_avatar": "AVATAR OBJETIVO Y OBJECIONES",
    "04_product_matrix": "MATRIZ DE PRODUCTO (PILARES)",
    "05_gold_standard_examples": "EJEMPLOS DE ORO (REFERENCIA DE CALIDAD)",
}

# Mensaje de fallback si el búnker no esta disponible. Es corto y
# generico para que el LLM no produzca contenido especifico de marca
# cuando no tiene contexto real.
_FALLBACK_PROMPT = (
    "[BUNKER DE CONTEXTO NO DISPONIBLE]\n"
    "El búnker de contexto de Rompiendo Barreras no se pudo cargar. "
    "Procede con precaucion: no generes contenido que dependa de la "
    "identidad de marca, voz o avatar especificos. Si necesitas esa "
    "informacion, pidela al usuario."
)


# =============================================================================
# API publica
# =============================================================================

def _get_vault_path() -> Path:
    """Resuelve la ruta al Búnker, con override via env var."""
    override = os.getenv("CONTEXT_VAULT_PATH", "").strip()
    if override:
        return Path(override)
    return _DEFAULT_VAULT_PATH


@lru_cache(maxsize=1)
def load_context_vault() -> dict[str, str]:
    """Lee todos los archivos .md del búnker y devuelve dict {nombre: contenido}.

    El dict esta cacheado en memoria (lru_cache maxsize=1) para evitar
    releer el disco en cada llamada. Si los archivos del búnker
    cambian en runtime, llamar a `load_context_vault.cache_clear()`.

    Devuelve dict vacio si el búnker no existe. Nunca lanza excepcion.
    """
    vault_path = _get_vault_path()


def invalidate_cache() -> None:
    """Invalida el cache de load_context_vault()."""
    load_context_vault.cache_clear()
    log.info("context_loader: cargando búnker desde %s", vault_path)

    if not vault_path.exists():
        log.warning(
            "context_loader: búnker no existe en %s. Devolviendo dict vacio.",
            vault_path,
        )
        return {}

    result: dict[str, str] = {}
    for stem in CANONICAL_FILE_ORDER:
        file_path = vault_path / f"{stem}.md"
        if not file_path.exists():
            log.warning("context_loader: falta %s", file_path)
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            result[stem] = content
            log.debug("context_loader: cargado %s (%d chars)", stem, len(content))
        except OSError as exc:
            log.warning("context_loader: error leyendo %s: %s", file_path, exc)

    log.info(
        "context_loader: búnker cargado: %d/%d archivos, %d chars totales",
        len(result), len(CANONICAL_FILE_ORDER), sum(len(v) for v in result.values()),
    )
    return result


def get_unified_context_prompt() -> str:
    """Devuelve un string unico con todo el contexto del búnker formateado.

    Pensado para inyectar como system prompt en las llamadas a los LLMs
    del Squad. El orden de los archivos es el canonico (manifiesto ->
    voz -> avatar -> producto -> ejemplos de oro).

    Si el búnker no esta disponible, devuelve un mensaje de fallback
    explicito para que el LLM no invente contenido de marca.
    """
    vault = load_context_vault()
    if not vault:
        return _FALLBACK_PROMPT

    sections: list[str] = []
    for stem in CANONICAL_FILE_ORDER:
        content = vault.get(stem)
        if not content:
            continue
        header = _FILE_HEADERS.get(stem, stem.upper())
        sections.append(
            f"\n\n===== {header} =====\n{content.strip()}"
        )

    if not sections:
        return _FALLBACK_PROMPT

    intro = (
        "===== CONTEXTO DE MARCA: ROMPIENDO BARRERAS =====\n"
        "A continuacion se presenta la verdad de marca, voz, avatar,\n"
        "producto y ejemplos de oro del programa. Todo el contenido\n"
        "que generes debe ser consistente con este contexto. Si alguna\n"
        "instruccion del usuario entra en conflicto con el contexto,\n"
        "el contexto gana. Sin excepciones."
    )
    return intro + "".join(sections)


def get_file(stem: str) -> Optional[str]:
    """Devuelve el contenido de un archivo especifico del búnker.

    Args:
        stem: nombre del archivo sin extension (ej. "01_brand_manifesto").

    Returns:
        Contenido del archivo, o None si no existe.
    """
    return load_context_vault().get(stem)


def get_total_chars() -> int:
    """Devuelve el total de caracteres cargados del búnker (utilidad de debug)."""
    return sum(len(v) for v in load_context_vault().values())


def get_loaded_files() -> list[str]:
    """Devuelve la lista de archivos cargados (utilidad de debug)."""
    return list(load_context_vault().keys())


__all__ = [
    "load_context_vault",
    "get_unified_context_prompt",
    "get_file",
    "get_total_chars",
    "get_loaded_files",
    "CANONICAL_FILE_ORDER",
]
