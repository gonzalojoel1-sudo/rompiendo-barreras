"""Capa de transformacion entre payloads de Orca (flat dict) y los property
objects que Notion espera en su API.

Schema-driven: el transformer se construye a partir de la respuesta de
`databases.retrieve`, de modo que conoce el tipo exacto de cada propiedad y
puede envolver el valor correctamente.
"""

from __future__ import annotations

import logging
from typing import Any

from .exceptions import NotionValidationError

logger = logging.getLogger(__name__)

_MAX_TITLE_CHARS = 1900
_MAX_RICH_TEXT_CHARS = 1900


class NotionTransformer:
    """Traductor bidireccional Orca <-> Notion.

    Cada metodo (__init__, from_database) recibe el schema; las llamadas de
    conversion usan ese schema para decidir como envolver cada valor.
    """

    def __init__(self, schema: dict[str, dict[str, Any]] | None = None) -> None:
        self._schema: dict[str, dict[str, Any]] = dict(schema or {})

    @classmethod
    def from_database(cls, database: dict[str, Any]) -> "NotionTransformer":
        """Construye un transformer a partir de la respuesta de databases.retrieve."""
        properties = database.get("properties") or {}
        schema = {name: prop for name, prop in properties.items()}
        if not schema:
            raise NotionValidationError(
                "La respuesta de databases.retrieve no contiene 'properties'. "
                "Verifica que el database_id sea correcto y este compartido con la integracion."
            )
        return cls(schema=schema)

    @property
    def property_names(self) -> list[str]:
        return list(self._schema.keys())

    def to_notion_properties(self, orca_payload: dict[str, Any]) -> dict[str, Any]:
        """Convierte un dict Orca (flat) a un dict de propiedades Notion."""
        result: dict[str, Any] = {}
        for key, value in orca_payload.items():
            if key not in self._schema:
                logger.warning(
                    "notion_bridge.transformer.skip key=%r (no existe en schema)",
                    key,
                )
                continue
            prop_type = self._schema[key].get("type")
            try:
                result[key] = self._wrap_value(prop_type, value)
            except NotionValidationError:
                raise
            except Exception as exc:
                raise NotionValidationError(
                    f"No se pudo envolver la propiedad {key!r} (tipo {prop_type!r}): {exc}"
                ) from exc
        return result

    def from_notion_properties(self, notion_props: dict[str, Any]) -> dict[str, Any]:
        """Convierte propiedades Notion a un dict Orca (flat)."""
        result: dict[str, Any] = {}
        for key, prop in notion_props.items():
            prop_type = prop.get("type") if isinstance(prop, dict) else None
            if prop_type is None:
                continue
            result[key] = self._unwrap_value(prop_type, prop)
        return result

    def _wrap_value(self, prop_type: str | None, value: Any) -> dict[str, Any]:
        if value is None:
            return self._wrap_null(prop_type)
        if prop_type == "title":
            return {"title": [{"type": "text", "text": {"content": self._truncate(str(value), _MAX_TITLE_CHARS)}}]}
        if prop_type == "rich_text":
            return {"rich_text": [{"type": "text", "text": {"content": self._truncate(str(value), _MAX_RICH_TEXT_CHARS)}}]}
        if prop_type == "status":
            return {"status": {"name": str(value)}}
        if prop_type == "select":
            return {"select": {"name": str(value)}}
        if prop_type == "multi_select":
            if not isinstance(value, (list, tuple)):
                raise NotionValidationError(
                    f"multi_select requiere una lista, recibido: {type(value).__name__}"
                )
            return {"multi_select": [{"name": str(v)} for v in value]}
        if prop_type == "number":
            if isinstance(value, bool):
                raise NotionValidationError("number no acepta booleanos")
            return {"number": float(value) if value is not None else None}
        if prop_type == "url":
            return {"url": str(value) if value else None}
        if prop_type == "email":
            return {"email": str(value) if value else None}
        if prop_type == "date":
            return {"date": {"start": str(value)}}
        if prop_type == "checkbox":
            return {"checkbox": bool(value)}
        if prop_type == "phone_number":
            return {"phone_number": str(value) if value else None}
        raise NotionValidationError(f"Tipo de propiedad no soportado: {prop_type!r}")

    def _wrap_null(self, prop_type: str | None) -> dict[str, Any]:
        if prop_type in {"title", "rich_text", "status", "select", "multi_select",
                          "url", "email", "phone_number", "date"}:
            return {prop_type: None} if prop_type != "multi_select" else {"multi_select": []}
        if prop_type == "number":
            return {"number": None}
        if prop_type == "checkbox":
            return {"checkbox": False}
        raise NotionValidationError(f"No se puede construir null para tipo {prop_type!r}")

    def _unwrap_value(self, prop_type: str, prop: dict[str, Any]) -> Any:
        if prop_type == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
        if prop_type == "rich_text":
            return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
        if prop_type == "status":
            status = prop.get("status") or {}
            return status.get("name")
        if prop_type == "select":
            select = prop.get("select") or {}
            return select.get("name")
        if prop_type == "multi_select":
            return [o.get("name") for o in prop.get("multi_select", [])]
        if prop_type == "number":
            return prop.get("number")
        if prop_type == "url":
            return prop.get("url")
        if prop_type == "email":
            return prop.get("email")
        if prop_type == "date":
            date = prop.get("date") or {}
            return date.get("start")
        if prop_type == "checkbox":
            return bool(prop.get("checkbox", False))
        if prop_type == "phone_number":
            return prop.get("phone_number")
        return None

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        logger.warning(
            "notion_bridge.transformer.truncate len=%d max=%d (texto recortado)",
            len(text), max_chars,
        )
        return text[:max_chars]
