# OBSOLETO - Usar Notion manualmente
# El script creaba 4 DBs legacy que ya no coinciden con la estructura actual.
# Estructura real: 8 DBs por pilar (db_M0, db_P1..db_P7) + 3 legacy.
# Ver manifest: manifests/notion_databases_manifest.json

"""build_notion_databases.py - OBSOLETO: MVP completado (05-jul-2026)

Crea las 4 bases de datos del ecosistema Rompiendo Barreras dentro de la
pagina padre indicada, respetando estrictamente el esquema definido en
docs/notion_schema.md (nombres de propiedades y opciones exactos, sin
modificar acentos, emojis ni caracteres especiales).

Uso:
    python build_notion_databases.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests

NOTION_TOKEN = os.getenv("NOTION_API_KEY", "ntn_REDACTED_LEAK_2026-07-28")
PARENT_PAGE_ID = "3a8cfb86-8e33-80e6-999a-df277c673dbc"
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
REQUEST_TIMEOUT = 30
INTER_REQUEST_DELAY = 0.4

HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def mask_token(token: str) -> str:
    if len(token) < 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def title_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "title", "title": {}}


def rich_text_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "rich_text", "rich_text": {}}


def number_prop(name: str, fmt: str = "number") -> dict[str, Any]:
    return {"name": name, "type": "number", "number": {"format": fmt}}


def url_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "url", "url": {}}


def email_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "email", "email": {}}


def date_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "date", "date": {}}


def checkbox_prop(name: str) -> dict[str, Any]:
    return {"name": name, "type": "checkbox", "checkbox": {}}


def select_prop(name: str, options: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "type": "select",
        "select": {
            "options": [{"name": opt, "color": "default"} for opt in options],
        },
    }


def status_prop(name: str, options: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "type": "status",
        "status": {
            "options": [{"name": opt, "color": "default"} for opt in options],
        },
    }


DB1_FABRICA_CLASES: dict[str, Any] = {
    "title": [{"type": "text", "text": {"content": "Fábrica de Clases"}}],
    "properties": {
        "Nombre_Clase": title_prop("Nombre_Clase"),
        "Pilar": select_prop(
            "Pilar",
            [
                "Módulo 0: Onboarding",
                "Pilar 1: Casa de Gobierno",
                "Pilar 2: Mentalidad de Reino",
                "Pilar 3: Hábitos del Éxito",
                "Pilar 4: Mayordomía Responsable",
                "Pilar 5: Trabajo y Propósito",
                "Pilar 6: Modelado de Negocios",
                "Pilar 7: Expansión del Reino",
            ],
        ),
        "Semana_Roadmap": number_prop("Semana_Roadmap"),
        "Estado_Guion": status_prop(
            "Estado_Guion",
            ["Sin Iniciar", "Generar Guion IA", "Guion Generado", "Aprobado Marcos"],
        ),
        "Estado_PPT": status_prop(
            "Estado_PPT",
            ["Pendiente", "En Diseño (Joel)", "PPT Lista"],
        ),
        "Estado_Grabacion": status_prop(
            "Estado_Grabacion",
            ["Pendiente", "Grabado Marcos"],
        ),
        "Estado_Publicacion": status_prop(
            "Estado_Publicacion",
            ["Pendiente", "Subido Bunny Stream", "Publicado Plataforma"],
        ),
        "Bunny_Embed_Code": rich_text_prop("Bunny_Embed_Code"),
        "PDF_Entregable_URL": url_prop("PDF_Entregable_URL"),
    },
}

DB2_MATRIZ_ANUNCIOS: dict[str, Any] = {
    "title": [{"type": "text", "text": {"content": "Matriz de Anuncios"}}],
    "properties": {
        "Nombre_Anuncio": title_prop("Nombre_Anuncio"),
        "Avatar_Target": select_prop(
            "Avatar_Target",
            [
                "Avatar 1: Pyme / Empresario",
                "Avatar 2: Joven Emprendedor",
            ],
        ),
        "Tipo_Hook": select_prop(
            "Tipo_Hook",
            [
                "Hook 1: Emocional (Paz y Familia)",
                "Hook 2: Lógico (Sistemas)",
                "Hook 3: Identidad (José de Arimatea)",
            ],
        ),
        "Script_Video": rich_text_prop("Script_Video"),
        "Estado_Copy": status_prop(
            "Estado_Copy",
            ["Borrador IA", "Listo para Grabar"],
        ),
        "Estado_Video": status_prop(
            "Estado_Video",
            ["Pendiente", "Grabado Marcos", "Editado Joel"],
        ),
        "Estado_Campana": status_prop(
            "Estado_Campana",
            ["Inactivo", "Activo Meta Ads", "Pausado / Fatigado"],
        ),
        "Inversion_Diaria_USD": number_prop("Inversion_Diaria_USD", fmt="dollar"),
    },
}

DB3_TAREAS_ROADMAP: dict[str, Any] = {
    "title": [{"type": "text", "text": {"content": "Tareas y Roadmap"}}],
    "properties": {
        "Mision_Tarea": title_prop("Mision_Tarea"),
        "Responsable": select_prop(
            "Responsable",
            ["Marcos", "Joel", "Agente IA"],
        ),
        "Fase_Proyecto": select_prop(
            "Fase_Proyecto",
            [
                "MVP Setup (Día -4 a 0)",
                "Lanzamiento Inminente",
                "Operación Semanal",
            ],
        ),
        "Fecha_Limite": date_prop("Fecha_Limite"),
        "Estado": status_prop(
            "Estado",
            ["Pendiente", "En Proceso", "Completado"],
        ),
        "Prioridad": select_prop(
            "Prioridad",
            [
                "🔴 Alta / Bloqueante",
                "🟡 Media",
                "🟢 Baja",
            ],
        ),
    },
}

DB4_CONTROL_ALUMNOS: dict[str, Any] = {
    "title": [{"type": "text", "text": {"content": "Control de Alumnos e Hitos"}}],
    "properties": {
        "Nombre_Alumno": title_prop("Nombre_Alumno"),
        "Email": email_prop("Email"),
        "Plan_Suscripcion": select_prop(
            "Plan_Suscripcion",
            [
                "Emprendedor ($15/mes)",
                "Estratégico ($35/mes)",
                "Elite ($95/mes)",
                "Emprendedor Anual ($150/año)",
                "Estratégico Anual ($350/año)",
                "Elite Anual ($950/año)",
                "Beca Solidaria",
            ],
        ),
        "Metodo_Pago": select_prop(
            "Metodo_Pago",
            [
                "Transferencia Bancaria",
                "Tarjeta / Link MP",
                "PayPal / Stripe",
            ],
        ),
        "Pilar_Actual_Desbloqueado": number_prop("Pilar_Actual_Desbloqueado"),
        "Kit_Fisico_Requerido": checkbox_prop("Kit_Fisico_Requerido"),
        "Kit_Fisico_Despachado": checkbox_prop("Kit_Fisico_Despachado"),
        "Estado_Hito_Semanal": status_prop(
            "Estado_Hito_Semanal",
            ["Al Día", "Pendiente Entregable", "Revision Mentor"],
        ),
    },
}

DATABASES: list[tuple[str, dict[str, Any]]] = [
    ("DB 1: Fábrica de Clases", DB1_FABRICA_CLASES),
    ("DB 2: Matriz de Anuncios", DB2_MATRIZ_ANUNCIOS),
    ("DB 3: Tareas y Roadmap", DB3_TAREAS_ROADMAP),
    ("DB 4: Control de Alumnos e Hitos", DB4_CONTROL_ALUMNOS),
]


def create_database(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        **payload,
    }
    response = requests.post(
        f"{BASE_URL}/databases",
        headers=HEADERS,
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def fetch_database(database_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}/databases/{database_id}",
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    print("=" * 64)
    print("  DESPLIEGUE DE BASES DE DATOS NOTION - ROMPIENDO BARRERAS")
    print("=" * 64)
    print(f"Token usado: {mask_token(NOTION_TOKEN)}")
    print(f"Pagina padre: {PARENT_PAGE_ID}")
    print(f"API: {BASE_URL}/databases")
    print()

    created: list[dict[str, str]] = []
    failed: list[tuple[str, str]] = []

    for label, payload in DATABASES:
        print(f"Creando {label}...")
        try:
            result = create_database(label, payload)
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else str(exc)
            status_code = exc.response.status_code if exc.response is not None else "?"
            print(f"  ERROR HTTP {status_code}: {body}")
            failed.append((label, body))
            continue
        except requests.RequestException as exc:
            print(f"  ERROR de red: {exc}")
            failed.append((label, str(exc)))
            continue

        db_id = result.get("id", "?")
        db_url = result.get("url", "?")
        title_obj = result.get("title", [])
        db_title = ""
        if title_obj and isinstance(title_obj, list):
            db_title = "".join(seg.get("plain_text", "") for seg in title_obj)
        print(f"  OK | ID: {db_id}")
        print(f"     Titulo devuelto: {db_title!r}")
        print(f"     URL: {db_url}")
        created.append({"label": label, "id": db_id, "url": db_url, "title": db_title})
        time.sleep(INTER_REQUEST_DELAY)

    print()
    print("=" * 64)
    print(f"  RESUMEN: {len(created)} creadas | {len(failed)} fallidas")
    print("=" * 64)

    if created:
        print("\nBases de datos creadas:")
        for entry in created:
            print(f"  - {entry['label']}")
            print(f"      ID:  {entry['id']}")
            print(f"      URL: {entry['url']}")

    if failed:
        print("\nFallos:")
        for label, err in failed:
            print(f"  - {label}: {err}")
        return 1

    print("\nVerificando lectura de cada base de datos recien creada...")
    all_ok = True
    for entry in created:
        try:
            fetched = fetch_database(entry["id"])
            prop_names = list(fetched.get("properties", {}).keys())
            print(f"  - {entry['label']}: {len(prop_names)} propiedades detectadas")
            for prop in prop_names:
                print(f"      * {prop}")
        except requests.RequestException as exc:
            print(f"  - {entry['label']}: ERROR de verificacion: {exc}")
            all_ok = False

    if not all_ok:
        return 2

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_dir = os.path.join(project_root, "manifests")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = os.path.join(manifest_dir, "notion_databases_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(created, f, indent=2, ensure_ascii=False)
    print(f"\nManifiesto guardado en: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())