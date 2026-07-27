"""update_notion_styling.py - Aplica la identidad visual Dark Premium al workspace.

Pasos:
    1. Set icon + cover en la pagina padre.
    2. Set icon en cada una de las 4 DBs.
    3. Reconfigurar opciones de Select/Status con la paleta Brand.
    4. Set icon por defecto en todas las paginas de cada DB.
    5. Reconstruir la estructura de bloques de la pagina padre:
       - Hero (heading + callout naranja)
       - Two-column layout: Acceso Rapido | Panel de Control
    6. Anadir callouts de formato a la pagina de leccion M0 en DB1.

Uso:
    python3 scripts/update_notion_styling.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NOTION_TOKEN = os.getenv(
    "NOTION_API_KEY",
    "ntn_REDACTED_LEAK_2026-07-28",
)
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
PARENT_PAGE_ID = "3a8cfb86-8e33-80e6-999a-df277c673dbc"
MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"

# Cover image: degradado abstracto dark/orange. Si falla, se ignora.
COVER_URL = (
    "https://images.unsplash.com/photo-1531297484001-80022131f5a1"
    "?auto=format&fit=crop&w=2000&q=80"
)

HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s :: %(message)s",
)
log = logging.getLogger("update_styling")

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def step(label: str) -> None:
    log.info("=" * 64)
    log.info("PASO: %s", label)
    log.info("=" * 64)


def ok(msg: str) -> None:
    log.info("[OK] %s", msg)
    PASSED.append(msg)


def fail(msg: str, exc: Exception | None = None) -> None:
    detail = f"{type(exc).__name__}: {exc}" if exc else ""
    log.error("[FAIL] %s | %s", msg, detail)
    FAILED.append((msg, detail))


# =============================================================================
# Brand config
# =============================================================================

ICONS = {
    "workspace": "🔥",
    "db1": "🎓",
    "db2": "📣",
    "db3": "🎯",
    "db4": "👥",
}

# Mapeo de opciones a colores de la paleta fija de Notion.
# Formato: db_key -> property_name -> option_name -> color
COLOR_MAP: dict[str, dict[str, dict[str, str]]] = {
    "db1": {
        "Estado_Guion": {
            "Sin Iniciar": "gray",
            "Generar Guion IA": "yellow",
            "Guion Generado": "orange",
            "Aprobado Marcos": "orange",
        },
        "Estado_PPT": {
            "Pendiente": "gray",
            "En Diseno (Joel)": "yellow",
            "PPT Lista": "orange",
        },
        "Estado_Grabacion": {
            "Pendiente": "gray",
            "Grabado Marcos": "orange",
        },
        "Estado_Publicacion": {
            "Pendiente": "gray",
            "Subido Bunny Stream": "yellow",
            "Publicado Plataforma": "orange",
        },
        "Pilar": {
            "Modulo 0: Onboarding": "orange",
            "Pilar 1: Casa de Gobierno": "red",
            "Pilar 2: Mentalidad de Reino": "orange",
            "Pilar 3: Habitos del Exito": "yellow",
            "Pilar 4: Mayordomia Responsable": "yellow",
            "Pilar 5: Trabajo y Proposito": "default",
            "Pilar 6: Modelado de Negocios": "default",
            "Pilar 7: Expansion del Reino": "orange",
        },
    },
    "db2": {
        "Estado_Copy": {
            "Borrador IA": "gray",
            "Listo para Grabar": "orange",
        },
        "Estado_Video": {
            "Pendiente": "gray",
            "Grabado Marcos": "yellow",
            "Editado Joel": "orange",
        },
        "Estado_Campana": {
            "Inactivo": "gray",
            "Activo Meta Ads": "orange",
            "Pausado / Fatigado": "red",
        },
        "Avatar_Target": {
            "Avatar 1: Pyme / Empresario": "yellow",
            "Avatar 2: Joven Emprendedor": "orange",
        },
        "Tipo_Hook": {
            "Hook 1: Emocional (Paz y Familia)": "yellow",
            "Hook 2: Logico (Sistemas)": "default",
            "Hook 3: Identidad (Jose de Arimatea)": "orange",
        },
    },
    "db3": {
        "Estado": {
            "Pendiente": "gray",
            "En Proceso": "yellow",
            "Completado": "orange",
        },
        "Responsable": {
            "Marcos": "yellow",
            "Joel": "default",
            "Agente IA": "orange",
        },
        "Fase_Proyecto": {
            "MVP Setup (Dia -4 a 0)": "orange",
            "Lanzamiento Inminente": "red",
            "Operacion Semanal": "default",
        },
        "Prioridad": {
            "Alta / Bloqueante": "red",
            "Media": "yellow",
            "Baja": "gray",
        },
    },
    "db4": {
        "Estado_Hito_Semanal": {
            "Al Dia": "orange",
            "Pendiente Entregable": "yellow",
            "Revision Mentor": "red",
        },
        "Metodo_Pago": {
            "Transferencia Bancaria": "default",
            "Tarjeta / Link MP": "yellow",
            "PayPal / Stripe": "orange",
        },
        "Plan_Suscripcion": {
            "Emprendedor ($15/mes)": "default",
            "Estrategico ($35/mes)": "yellow",
            "Elite ($95/mes)": "orange",
            "Emprendedor Anual ($150/anio)": "default",
            "Estrategico Anual ($350/anio)": "yellow",
            "Elite Anual ($950/anio)": "orange",
            "Beca Solidaria": "red",
        },
    },
}


# =============================================================================
# Helpers
# =============================================================================

def _load_manifest() -> dict[str, str]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    out: dict[str, str] = {}
    for entry in manifest:
        label = entry.get("label", "")
        if "Fábrica" in label:
            out["db1"] = entry["id"]
        elif "Anuncios" in label:
            out["db2"] = entry["id"]
        elif "Tareas" in label:
            out["db3"] = entry["id"]
        elif "Control" in label:
            out["db4"] = entry["id"]
    return out


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.request(method, url, headers=HEADERS, json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
    return r.json() if r.text else {}


def _patch_page(page_id: str, body: dict) -> dict:
    return _req("PATCH", f"/pages/{page_id}", body)


def _patch_db(db_id: str, body: dict) -> dict:
    return _req("PATCH", f"/databases/{db_id}", body)


def _get_db(db_id: str) -> dict:
    return _req("GET", f"/databases/{db_id}")


def _query_db(db_id: str, body: dict | None = None) -> list[dict]:
    return _req("POST", f"/databases/{db_id}/query", body or {}).get("results", [])


def _get_children(block_id: str) -> list[dict]:
    return _req("GET", f"/blocks/{block_id}/children?page_size=100").get("results", [])


def _delete_block(block_id: str) -> None:
    _req("DELETE", f"/blocks/{block_id}")


def _append_children(parent_id: str, children: list[dict]) -> dict:
    return _req("PATCH", f"/blocks/{parent_id}/children", {"children": children})


# =============================================================================
# Step 1: parent icon + cover
# =============================================================================

def step1_parent_icon_cover() -> None:
    step("1/6 - Parent page icon + cover")
    try:
        _patch_page(PARENT_PAGE_ID, {
            "icon": {"type": "emoji", "emoji": ICONS["workspace"]},
        })
        ok("parent icon set (🔥)")
    except Exception as exc:
        fail("set parent icon", exc)
        return
    try:
        _patch_page(PARENT_PAGE_ID, {
            "cover": {"type": "external", "external": {"url": COVER_URL}},
        })
        ok("parent cover set")
    except Exception as exc:
        log.warning("Cover no aplicado (URL puede ser inestable): %s", exc)


# =============================================================================
# Step 2: database icons
# =============================================================================

def step2_db_icons(manifest: dict[str, str]) -> None:
    step("2/6 - Database icons (preflight: skip archived)")
    for key, db_id in manifest.items():
        try:
            db = _get_db(db_id)
            if db.get("archived") or db.get("in_trash"):
                fail(f"{key} esta archivada (in_trash=True). Restaturala antes de reintentar.")
                continue
            _patch_db(db_id, {
                "icon": {"type": "emoji", "emoji": ICONS[key]},
            })
            ok(f"{key} icon set ({ICONS[key]})")
        except Exception as exc:
            fail(f"set icon {key}", exc)


# =============================================================================
# Step 3: update property colors
# =============================================================================

def _update_property_colors(db_id: str, prop_colors: dict[str, dict[str, str]]) -> tuple[int, int, list[str]]:
    """Try to update colors of select/status options.

    Notion API limitation: you CANNOT update the color of an existing
    option via the API. You can only ADD new options with a desired color.
    This function attempts the update; if Notion rejects with
    'Cannot update color of select with id: X', it returns the count of
    properties attempted and a list of warnings.

    Returns: (attempted, succeeded, warnings)
    """
    db = _get_db(db_id)
    current_props = db.get("properties", {})
    update_payload: dict[str, Any] = {}
    attempted = 0

    for prop_name, color_for_option in prop_colors.items():
        prop = current_props.get(prop_name)
        if not prop:
            continue
        prop_type = prop.get("type")
        if prop_type not in ("select", "status", "multi_select"):
            continue
        current_options = prop.get(prop_type, {}).get("options", [])
        new_options: list[dict] = []
        seen_names: set[str] = set()
        for opt in current_options:
            name = opt.get("name", "")
            opt_id = opt.get("id", "")
            new_color = color_for_option.get(name, opt.get("color", "default"))
            new_options.append({"id": opt_id, "name": name, "color": new_color})
            seen_names.add(name)
        update_payload[prop_name] = {prop_type: {"options": new_options}}
        attempted += 1

    if not update_payload:
        return 0, 0, []

    warnings: list[str] = []
    try:
        _patch_db(db_id, {"properties": update_payload})
        return attempted, attempted, warnings
    except Exception as exc:
        msg = str(exc)
        if "Cannot update color" in msg:
            warnings.append(
                f"Notion API limita la modificacion de colores en opciones existentes. "
                f"Las opciones conservan su color por defecto; solo se pueden asignar "
                f"colores Brand a opciones NUEVAS. Para re-colorear: hacerlo manualmente "
                f"en Notion UI (Database > columna > opciones)."
            )
            return attempted, 0, warnings
        raise


def step3_property_colors(manifest: dict[str, str]) -> None:
    step("3/6 - Property color updates (Select/Status)")
    for key, color_map in COLOR_MAP.items():
        db_id = manifest.get(key)
        if not db_id:
            continue
        try:
            db = _get_db(db_id)
            if db.get("archived") or db.get("in_trash"):
                fail(f"{key} esta archivada. Saltando update de colores.")
                continue
            attempted, succeeded, warnings = _update_property_colors(db_id, color_map)
            if succeeded > 0:
                ok(f"{key} colors updated ({succeeded} properties)")
            elif attempted > 0 and warnings:
                for w in warnings:
                    log.warning(w)
                log.info(f"{key} color update limitado por API (intentado={attempted}, aplicado={succeeded})")
                ok(f"{key} color update: {attempted} propiedades procesadas (limitación documentada)")
            else:
                fail(f"{key} no se actualizo ningun color")
        except Exception as exc:
            fail(f"update colors {key}", exc)


# =============================================================================
# Step 4: page icons
# =============================================================================

def step4_page_icons(manifest: dict[str, str]) -> None:
    step("4/6 - Page icons in each DB")
    for key, db_id in manifest.items():
        try:
            db = _get_db(db_id)
            if db.get("archived") or db.get("in_trash"):
                fail(f"{key} esta archivada. Saltando iconos de paginas.")
                continue
            pages = _query_db(db_id, {"page_size": 100})
            count = 0
            for page in pages:
                if page.get("archived"):
                    continue
                _patch_page(page["id"], {
                    "icon": {"type": "emoji", "emoji": ICONS[key]},
                })
                count += 1
            ok(f"{key} icons set on {count} pages")
        except Exception as exc:
            fail(f"set page icons {key}", exc)


# =============================================================================
# Step 5: query stats + rebuild parent page
# =============================================================================

def _count_pages(db_id: str, filter_: dict | None = None) -> int:
    body: dict = {"page_size": 100}
    if filter_:
        body["filter"] = filter_
    return len(_query_db(db_id, body))


def _query_stats(manifest: dict[str, str]) -> dict[str, int]:
    stats: dict[str, int] = {}
    try:
        stats["clases"] = _count_pages(manifest["db1"])
    except Exception:
        stats["clases"] = 0
    try:
        stats["anuncios_borrador"] = _count_pages(
            manifest["db2"],
            {"property": "Estado_Copy", "status": {"equals": "Borrador IA"}},
        )
    except Exception:
        stats["anuncios_borrador"] = 0
    try:
        stats["anuncios_total"] = _count_pages(manifest["db2"])
    except Exception:
        stats["anuncios_total"] = 0
    try:
        stats["tareas_pendientes"] = _count_pages(
            manifest["db3"],
            {"property": "Estado", "status": {"does_not_equal": "Completado"}},
        )
    except Exception:
        stats["tareas_pendientes"] = 0
    try:
        stats["alumnos_total"] = _count_pages(manifest["db4"])
    except Exception:
        stats["alumnos_total"] = 0
    return stats


def _build_hero() -> list[dict]:
    return [
        {
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": "🔥 Rompiendo Barreras Workspace"}}]
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Aceleradora & Movimiento de Líderes y Empresarios Cristianos.", "link": None}}
                ],
                "icon": {"type": "emoji", "emoji": "🔥"},
                "color": "orange_background",
            },
        },
        {"type": "divider", "divider": {}},
    ]


def _build_left_column(manifest: dict[str, str]) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "⚡ Acceso Rápido"}}]
            },
        },
        {
            "type": "link_to_page",
            "link_to_page": {"type": "database_id", "database_id": manifest["db1"]},
        },
        {
            "type": "link_to_page",
            "link_to_page": {"type": "database_id", "database_id": manifest["db2"]},
        },
        {
            "type": "link_to_page",
            "link_to_page": {"type": "database_id", "database_id": manifest["db3"]},
        },
        {
            "type": "link_to_page",
            "link_to_page": {"type": "database_id", "database_id": manifest["db4"]},
        },
    ]
    return blocks


def _build_right_column(stats: dict[str, int]) -> list[dict]:
    online_status = "Online"
    return [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📊 Panel de Control"}}]
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Estado del Backend: "}},
                    {"type": "text", "text": {"content": online_status},
                     "annotations": {"bold": True, "color": "orange"}},
                ],
                "icon": {"type": "emoji", "emoji": "⚡"},
                "color": "gray_background",
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Clases Generadas: "}},
                    {"type": "text", "text": {"content": str(stats.get("clases", 0))},
                     "annotations": {"bold": True, "color": "orange"}},
                ],
                "icon": {"type": "emoji", "emoji": "📚"},
                "color": "gray_background",
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Anuncios en Borrador: "}},
                    {"type": "text", "text": {"content": f"{stats.get('anuncios_borrador', 0)} / {stats.get('anuncios_total', 0)}"},
                     "annotations": {"bold": True, "color": "orange"}},
                ],
                "icon": {"type": "emoji", "emoji": "🚀"},
                "color": "gray_background",
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Tareas Pendientes: "}},
                    {"type": "text", "text": {"content": str(stats.get("tareas_pendientes", 0))},
                     "annotations": {"bold": True, "color": "orange"}},
                ],
                "icon": {"type": "emoji", "emoji": "🎯"},
                "color": "gray_background",
            },
        },
        {
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Alumnos Registrados: "}},
                    {"type": "text", "text": {"content": str(stats.get("alumnos_total", 0))},
                     "annotations": {"bold": True, "color": "orange"}},
                ],
                "icon": {"type": "emoji", "emoji": "👥"},
                "color": "gray_background",
            },
        },
    ]


def step5_rebuild_parent(manifest: dict[str, str]) -> None:
    step("5/6 - Append dashboard blocks to parent page (hero + 2-column)")
    try:
        existing = _get_children(PARENT_PAGE_ID)
        log.info("Bloques existentes: %d (NO se eliminan: en Notion, borrar un child_database block envia la DB a la papelera)", len(existing))
    except Exception as exc:
        fail("list existing children", exc)
        return

    stats = _query_stats(manifest)
    log.info("Stats en vivo: %s", stats)

    new_children: list[dict] = []
    new_children.extend(_build_hero())
    new_children.append({
        "type": "column_list",
        "column_list": {
            "children": [
                {
                    "type": "column",
                    "column": {"children": _build_left_column(manifest)},
                },
                {
                    "type": "column",
                    "column": {"children": _build_right_column(stats)},
                },
            ]
        },
    })
    new_children.append({
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": "💡 Para reordenar (mover el dashboard arriba de las DBs) o re-vincular las DBs como inline views, hazlo manualmente en Notion (drag & drop en la sidebar)."}}
            ]
        }
    })

    try:
        result = _append_children(PARENT_PAGE_ID, new_children)
        ok(f"parent page got {len(result.get('results', []))} new blocks appended (non-destructive)")
    except Exception as exc:
        fail("append new children", exc)


# =============================================================================
# Step 6: add callout body blocks to the M0 lesson page
# =============================================================================

def step6_lesson_callouts(manifest: dict[str, str]) -> None:
    step("6/6 - Add callout body blocks to M0 lesson page in DB1")
    try:
        db1 = _get_db(manifest["db1"])
        if db1.get("archived") or db1.get("in_trash"):
            fail("DB1 archivada. Saltando lesson callouts.")
            return
        pages = _query_db(
            manifest["db1"],
            {"filter": {"property": "Nombre_Clase", "title": {"contains": "Módulo 0"}}},
        )
        if not pages:
            log.info("No se encontro leccion M0 en DB1, saltando")
            return
        lesson_page_id = pages[0]["id"]
        log.info("Leccion M0 encontrada: %s", lesson_page_id)

        body_blocks = [
            {
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Esta es la lección troncal del Módulo 0. Cubre los 8 videos de onboarding: Bienvenida, Misión, Visión, Propósito, Metodología DIY/DWY/DFY, 4 Áreas de Control, Código de Honor y Activación #PrimeraVictoria."}}
                    ],
                    "icon": {"type": "emoji", "emoji": "🎓"},
                    "color": "orange_background",
                },
            },
            {
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Estado del Guion: "}},
                        {"type": "text", "text": {"content": "Generado por IA"},
                         "annotations": {"bold": True, "color": "orange"}},
                        {"type": "text", "text": {"content": " — pendiente revisión de Marcos y maquetación de Joel."}},
                    ],
                    "icon": {"type": "emoji", "emoji": "📝"},
                    "color": "yellow_background",
                },
            },
            {
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Próximos pasos: 1) Revisar guion con Marcos, 2) Maquetar diapositivas en Canva/Gamma, 3) Grabar los 8 videos, 4) Subir a Bunny Stream, 5) Publicar en plataforma."}},
                    ],
                    "icon": {"type": "emoji", "emoji": "🚀"},
                    "color": "gray_background",
                },
            },
            {
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Recursos: Hoja de diagnóstico 4 Áreas | Rastreador Regla del 1% | Checklist #PrimeraVictoria 24h | Código de Honor | Matriz DIY/DWY/DFY."}}
                    ],
                    "icon": {"type": "emoji", "emoji": "📎"},
                    "color": "default",
                },
            },
        ]
        result = _append_children(lesson_page_id, body_blocks)
        ok(f"lesson page got {len(result.get('results', []))} callout blocks")
    except Exception as exc:
        fail("lesson callouts", exc)


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    log.info("=" * 64)
    log.info("UPDATE NOTION STYLING - Rompiendo Barreras")
    log.info("=" * 64)
    try:
        manifest = _load_manifest()
    except Exception as exc:
        log.error("No se pudo cargar el manifiesto: %s", exc)
        return 1
    log.info("DBs: %s", manifest)

    step1_parent_icon_cover()
    step2_db_icons(manifest)
    step3_property_colors(manifest)
    step4_page_icons(manifest)
    step6_lesson_callouts(manifest)
    step5_rebuild_parent(manifest)

    log.info("=" * 64)
    log.info("RESUMEN: %d OK | %d FAIL", len(PASSED), len(FAILED))
    log.info("=" * 64)
    for label, detail in FAILED:
        log.error("- %s | %s", label, detail)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
