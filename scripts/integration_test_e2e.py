"""integration_test_e2e.py

Prueba de integracion end-to-end: Notion <-> Scripts locales.

Flujo:
  1. Lee el ID de DB3 (Tareas y Roadmap) desde manifests/.
  2. Busca la tarea de prueba (titulo contiene 'TEST_E2E').
  3. Calcula el siguiente estado en la maquina: Pendiente -> En Proceso -> Completado.
  4. Actualiza el estado en Notion via PATCH /v1/pages/{id}.
  5. Re-consulta la DB para verificar persistencia.

Uso:
    python integration_test_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

NOTION_TOKEN = "ntn_REDACTED_LEAK_2026-07-28"
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
REQUEST_TIMEOUT = 30

HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

TEST_TITLE_FRAGMENT = "TEST_E2E"
DB3_LABEL_HINT = "Tareas"
STATE_FLOW: tuple[str, ...] = ("Pendiente", "En Proceso", "Completado")


def mask_token(token: str) -> str:
    if len(token) < 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def load_db3_id() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(project_root, "manifests", "notion_databases_manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    for entry in manifest:
        if DB3_LABEL_HINT in entry.get("label", ""):
            return entry["id"]
    raise RuntimeError(f"No se encontro DB3 (hint: '{DB3_LABEL_HINT}') en el manifiesto.")


def query_test_task(database_id: str) -> dict[str, Any] | None:
    body = {
        "filter": {
            "property": "Mision_Tarea",
            "title": {"contains": TEST_TITLE_FRAGMENT},
        }
    }
    response = requests.post(
        f"{BASE_URL}/databases/{database_id}/query",
        headers=HEADERS,
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None


def get_status(page: dict[str, Any]) -> str:
    try:
        return page["properties"]["Estado"]["status"]["name"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Pagina sin propiedad 'Estado' valida: {exc}") from exc


def update_status(page_id: str, new_status: str) -> dict[str, Any]:
    body = {
        "properties": {
            "Estado": {"status": {"name": new_status}},
        }
    }
    response = requests.patch(
        f"{BASE_URL}/pages/{page_id}",
        headers=HEADERS,
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def next_state(current: str) -> str | None:
    if current not in STATE_FLOW:
        raise RuntimeError(f"Estado '{current}' no esta en el flujo {STATE_FLOW}.")
    idx = STATE_FLOW.index(current)
    if idx == len(STATE_FLOW) - 1:
        return None
    return STATE_FLOW[idx + 1]


def main() -> int:
    print("=" * 64)
    print("  PRUEBA DE INTEGRACION END-TO-END - NOTION <-> SCRIPTS")
    print("=" * 64)
    print(f"Token:       {mask_token(NOTION_TOKEN)}")
    print(f"DB objetivo: {DB3_LABEL_HINT} (Tareas y Roadmap)")
    print(f"Marca:       titulo contiene '{TEST_TITLE_FRAGMENT}'")
    print(f"Flujo:       {' -> '.join(STATE_FLOW)}")
    print()

    try:
        db_id = load_db3_id()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[ERROR] No se pudo cargar DB3 desde el manifiesto: {exc}")
        return 1
    print(f"[1/5] DB3 ID: {db_id}")

    print(f"[2/5] Consultando tarea '{TEST_TITLE_FRAGMENT}'...")
    task = query_test_task(db_id)
    if task is None:
        print(f"  No existe la tarea de prueba. Crear primero con un INSERT previo.")
        return 1
    page_id = task["id"]
    current_status = get_status(task)
    print(f"  Page ID:       {page_id}")
    print(f"  Estado actual: {current_status}")

    print("[3/5] Calculando siguiente estado...")
    nxt = next_state(current_status)
    if nxt is None:
        print(f"  Estado terminal '{current_status}'. No hay transicion pendiente.")
        return 0
    print(f"  Transicion: {current_status} -> {nxt}")

    print(f"[4/5] PATCH /v1/pages/{page_id}  (Estado = {nxt!r})...")
    updated = update_status(page_id, nxt)
    api_status = get_status(updated)
    assert api_status == nxt, f"API devolvio estado inconsistente: {api_status!r} != {nxt!r}"
    print(f"  Respuesta API: {api_status}")

    print("[5/5] Verificando persistencia (re-query)...")
    refetched = query_test_task(db_id)
    if refetched is None:
        print("  ERROR: la tarea desaparecio despues del PATCH.")
        return 2
    verified_status = get_status(refetched)
    assert verified_status == nxt, f"Persistencia fallida: {verified_status!r} != {nxt!r}"
    print(f"  Estado verificado: {verified_status}")

    print()
    print("=" * 64)
    print("  QA: TRANSICION APLICADA Y PERSISTIDA")
    print("=" * 64)
    print(f"  Tarea:   {page_id}")
    print(f"  Cambio:  {current_status} -> {verified_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())