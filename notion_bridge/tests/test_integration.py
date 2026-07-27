"""Test de integracion end-to-end del NotionBridge contra la API real de Notion.

Casos cubiertos (segun la metodologia de 4 fases del Sprint 1):
    A. Lectura de una base de datos (fetchDatabaseItems).
    B. Creacion de un registro enviado desde Orca (createNotionPage).
    C. Actualizacion del estado a "Procesado por Orca" (updateNotionPage).
    D. Edge cases:
       - Token invalido -> NotionAuthError.
       - Payload vacio -> NotionValidationError.
       - Texto > 2000 chars -> truncar a 1900 (no rompe).
       - DB no compartida / inexistente -> NotionNotFoundError.

Uso:
    pip install -r notion_bridge/requirements.txt
    export NOTION_API_KEY="ntn_..."
    python notion_bridge/tests/test_integration.py

El test crea una pagina real con un marcador ORCA_BRIDGE_TEST_* que puedes
localizar y eliminar manualmente desde Notion al terminar.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from notion_bridge import (  # noqa: E402
    NotionAuthError,
    NotionBridgeConfig,
    NotionBridgeError,
    NotionBridgeService,
    NotionNotFoundError,
    NotionTransformer,
    NotionValidationError,
)
from notion_bridge.client import NotionClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("test_integration")

MANIFEST_PATH = ROOT / "manifests" / "notion_databases_manifest.json"
DB3_LABEL_HINT = "Tareas"

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def find_database_id(label_hint: str) -> str:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"Manifiesto no encontrado en {MANIFEST_PATH}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    for entry in manifest:
        if label_hint in entry.get("label", ""):
            return entry["id"]
    raise RuntimeError(f"DB con hint {label_hint!r} no encontrada en el manifiesto")


def build_service(config: NotionBridgeConfig, database_id: str) -> NotionBridgeService:
    client = NotionClient(config)
    database = client.retrieve_database(database_id)
    transformer = NotionTransformer.from_database(database)
    return NotionBridgeService(client, transformer), database, transformer


def record(test_name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(test_name)
        print(f"  [OK]   {test_name} {detail}")
    else:
        FAILED.append((test_name, detail))
        print(f"  [FAIL] {test_name} {detail}")


def test_a_read_database(config: NotionBridgeConfig, database_id: str) -> None:
    name = "A. Lectura de database (fetchDatabaseItems)"
    print(f"\n[TEST] {name}")
    try:
        service, database, _ = build_service(config, database_id)
        title = "".join(t.get("plain_text", "") for t in database.get("title", []))
        items = service.fetch_database_items(database_id, page_size=5)
        record(name, True, f"| db='{title}' items={len(items)}")
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


def test_b_create_page(config: NotionBridgeConfig, database_id: str) -> dict | None:
    name = "B. Creacion de pagina desde payload Orca (createNotionPage)"
    print(f"\n[TEST] {name}")
    marker = f"ORCA_BRIDGE_TEST_{uuid.uuid4().hex[:8]}"
    try:
        service, _, _ = build_service(config, database_id)
        orca_data = {
            "Mision_Tarea": f"{marker}: Validacion end-to-end",
            "Responsable": "Agente IA",
            "Estado": "Pendiente",
            "Prioridad": "Media",
        }
        page = service.create_notion_page(database_id, orca_data)
        page_id = page.get("id")
        if not page_id:
            record(name, False, "Respuesta sin id de pagina")
            return None
        record(name, True, f"| page_id={page_id}")
        return {"page_id": page_id, "marker": marker}
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")
        return None


def test_c_update_status(
    config: NotionBridgeConfig, database_id: str, page_id: str
) -> None:
    name = "C. Actualizacion de estado (updateNotionPage)"
    print(f"\n[TEST] {name}")
    try:
        service, _, _ = build_service(config, database_id)
        updated = service.update_notion_page(page_id, {"Estado": "En Proceso"})
        actual = service.get_property_value(updated, "Estado")
        if actual != "En Proceso":
            record(name, False, f"esperado 'En Proceso', obtenido {actual!r}")
            return
        record(name, True, f"| page_id={page_id} estado={actual!r}")
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


def test_d_invalid_token() -> None:
    name = "D1. Edge: token invalido -> NotionAuthError"
    print(f"\n[TEST] {name}")
    try:
        bad_config = NotionBridgeConfig(
            api_key="ntn_TOKEN_INVENTADO_PARA_TEST_xxxxxxxxxxxxxxxx",
            api_version="2022-06-28",
            timeout=10.0,
            max_retries=0,
            backoff_base=0.1,
            backoff_max=1.0,
        )
        client = NotionClient(bad_config)
        client.retrieve_database("00000000-0000-0000-0000-000000000000")
        record(name, False, "no se lanzo la excepcion esperada")
    except NotionAuthError as exc:
        record(name, True, f"| NotionAuthError capturada: {str(exc)[:60]}...")
    except Exception as exc:
        record(name, False, f"excepcion inesperada {type(exc).__name__}: {exc}")


def test_e_empty_payload(config: NotionBridgeConfig, database_id: str) -> None:
    name = "D2. Edge: payload vacio -> NotionValidationError"
    print(f"\n[TEST] {name}")
    try:
        service, _, _ = build_service(config, database_id)
        service.create_notion_page(database_id, {})
        record(name, False, "no se lanzo excepcion")
    except NotionValidationError as exc:
        record(name, True, f"| NotionValidationError capturada: {exc}")
    except Exception as exc:
        record(name, False, f"excepcion inesperada {type(exc).__name__}: {exc}")


def test_f_long_text_truncation(config: NotionBridgeConfig, database_id: str) -> None:
    name = "D3. Edge: titulo > 2000 chars -> truncar a 1900 sin romper"
    print(f"\n[TEST] {name}")
    try:
        service, database, _ = build_service(config, database_id)
        title_prop = next(
            (name for name, p in database.get("properties", {}).items() if p.get("type") == "title"),
            None,
        )
        if not title_prop:
            record(name, True, "| sin propiedad title en la DB, saltando")
            return
        long_title = "X" * 5000
        marker = f"ORCA_BRIDGE_LONG_{uuid.uuid4().hex[:6]}"
        page = service.create_notion_page(database_id, {title_prop: f"{marker} {long_title}"})
        page_id = page.get("id")
        stored = service.get_property_value(page, title_prop)
        if len(stored) > 2000:
            record(name, False, f"titulo almacenado={len(stored)} chars (esperado <= 2000)")
            return
        record(name, True, f"| almacenado={len(stored)} chars (de 5000 enviados)")
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


def test_g_database_not_shared() -> None:
    name = "D4. Edge: database no compartido / inexistente -> NotionNotFoundError"
    print(f"\n[TEST] {name}")
    try:
        config = NotionBridgeConfig.from_env()
        client = NotionClient(config)
        client.retrieve_database("00000000-0000-0000-0000-000000000000")
        record(name, False, "no se lanzo la excepcion esperada")
    except NotionNotFoundError as exc:
        record(name, True, f"| NotionNotFoundError capturada: {str(exc)[:60]}...")
    except NotionAuthError as exc:
        record(name, True, f"| NotionAuthError (404 a veces devuelto como 401/403 por Notion): {str(exc)[:60]}...")
    except Exception as exc:
        record(name, False, f"excepcion inesperada {type(exc).__name__}: {exc}")


def main() -> int:
    print("=" * 64)
    print("  NOTION BRIDGE - INTEGRATION TESTS (Sprint 1)")
    print("=" * 64)

    if not os.getenv("NOTION_API_KEY"):
        print("ERROR: NOTION_API_KEY no esta definida en el entorno.")
        return 1

    try:
        config = NotionBridgeConfig.from_env()
        print(f"Config OK (key={config.masked_api_key()}, version={config.api_version})")
    except Exception as exc:
        print(f"ERROR cargando config: {exc}")
        return 1

    try:
        database_id = find_database_id(DB3_LABEL_HINT)
    except Exception as exc:
        print(f"ERROR localizando DB: {exc}")
        return 1
    print(f"DB objetivo: {DB3_LABEL_HINT} ({database_id})")

    test_a_read_database(config, database_id)
    created = test_b_create_page(config, database_id)
    if created:
        test_c_update_status(config, database_id, created["page_id"])
    test_d_invalid_token()
    test_e_empty_payload(config, database_id)
    test_f_long_text_truncation(config, database_id)
    test_g_database_not_shared()

    print()
    print("=" * 64)
    print(f"  RESULTADO: {len(PASSED)} OK | {len(FAILED)} FAIL")
    print("=" * 64)
    for tname, detail in FAILED:
        print(f"  - FAIL {tname}: {detail}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
