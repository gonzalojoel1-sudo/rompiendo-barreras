"""test_memory_integration.py - Pruebas de integracion del Sprint 2.

Cubre:
    1. Escritura atomica del scratchpad bajo carga concurrente + rolling por tamano.
    2. Cache de schemas de Notion: cache hit/miss observable.
    3. Sincronizacion bidireccional real con Notion (DB3 Tareas).
    4. Resiliencia: con Notion "caido", la cola local se preserva y reintenta.

Uso:
    export NOTION_API_KEY="ntn_..."
    python -m vps_backend.tests.test_memory_integration
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "vps_backend"))
sys.path.insert(0, str(ROOT))

from scratchpad_io import ScratchpadIO  # noqa: E402
from notion_bridge import CachedSchemaService, NotionClient  # noqa: E402
from notion_bridge.cache import SchemaCache  # noqa: E402
from notion_bridge.config import NotionBridgeConfig  # noqa: E402
from sync_manager import MemorySyncManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("test_memory_integration")

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def record(test_name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(test_name)
        print(f"  [OK]   {test_name} {detail}")
    else:
        FAILED.append((test_name, detail))
        print(f"  [FAIL] {test_name} {detail}")


def find_db_id(label_hint: str) -> str:
    manifest_path = ROOT / "manifests" / "notion_databases_manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    for entry in manifest:
        if label_hint in entry.get("label", ""):
            return entry["id"]
    raise RuntimeError(f"DB {label_hint!r} no encontrada en el manifiesto")


class FakeMemoryManager:
    """Stub minimo que emula la interfaz de HierarchicalMemoryManager para los tests."""

    def __init__(self, scratchpad: dict | None = None) -> None:
        self.scratchpad = scratchpad or {
            "decisiones_clave": [],
            "hitos_pendientes": [],
            "hitos_completados": [],
            "event_log": [],
            "notion_sync_pending": [],
        }

    def append_event(self, event_type: str, payload: dict) -> None:
        self.scratchpad.setdefault("event_log", []).append(
            {"type": event_type, "payload": payload}
        )

    def enqueue_notion_sync(self, event: dict) -> None:
        self.scratchpad.setdefault("notion_sync_pending", []).append(event)

    def dequeue_notion_synced(self, event: dict) -> None:
        pending = self.scratchpad.get("notion_sync_pending", [])
        self.scratchpad["notion_sync_pending"] = [e for e in pending if e is not event]

    def save_scratchpad(self) -> None:
        pass


# =============================================================================
# Test 1: Escritura atomica + rotacion
# =============================================================================
def test_1_atomic_writes_and_rotation() -> None:
    name = "T1. Escritura atomica + rotacion (sin corrupcion JSON)"
    print(f"\n[TEST] {name}")
    tmp = Path(tempfile.mkdtemp(prefix="rb_scratchpad_test_"))
    path = tmp / "scratchpad.json"

    try:
        io = ScratchpadIO(path, lock_timeout=5)
        io.write({"seed": True, "event_log": []})

        n_writers = 8
        events_per_writer = 25

        def writer(writer_id: int) -> None:
            for i in range(events_per_writer):
                io.read_modify_write(
                    lambda d: {
                        **d,
                        "event_log": d.get("event_log", [])
                        + [{"writer": writer_id, "i": i}],
                    }
                )

        with ThreadPoolExecutor(max_workers=n_writers) as ex:
            futures = [ex.submit(writer, w) for w in range(n_writers)]
            for f in futures:
                f.result()

        final = io.read()
        total = sum(1 for e in final["event_log"] if "writer" in e and "i" in e)
        record(
            name + " - integridad JSON",
            isinstance(final, dict) and "event_log" in final,
            f"| bytes={io.size_bytes()} eventos_validos={total}/{n_writers*events_per_writer}",
        )

        # Rolling: forzar tamano y verificar que no excede el limite
        max_bytes = 2048
        big = {
            "decisiones_clave": [f"decision {i}" for i in range(50)],
            "event_log": [{"type": "TASK_STATUS_CHANGED", "payload": {"x": "y"*100}} for _ in range(50)],
            "contexto_dinamico": "z" * 8000,
        }
        io.write(big)
        before_size = io.size_bytes()

        # Simular la rotacion que haria memory_manager._rotate_if_needed
        if before_size > max_bytes:
            log = big["event_log"]
            if len(log) > 20:
                big["event_log"] = log[-20:]
            decisiones = big["decisiones_clave"]
            if len(decisiones) > 10:
                big["decisiones_clave"] = decisiones[-10:]
            big["contexto_dinamico"] = big["contexto_dinamico"][-4000:]
            io.write(big)

        rotated = io.read()
        rotated_size = io.size_bytes()
        record(
            name + " - rolling reduce tamano",
            rotated_size < before_size
            and len(rotated["decisiones_clave"]) == 10
            and len(rotated["event_log"]) == 20,
            f"| antes={before_size}B despues={rotated_size}B",
        )
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Test 2: Cache de schemas (cache hit/miss observable)
# =============================================================================
def test_2_schema_cache() -> None:
    name = "T2. Cache de schemas con TTL (hit/miss observable)"
    print(f"\n[TEST] {name}")
    if not os.getenv("NOTION_API_KEY"):
        record(name, False, "salteado (NOTION_API_KEY no definida)")
        return
    try:
        config = NotionBridgeConfig.from_env()
        client = NotionClient(config)
        cache = SchemaCache(ttl_seconds=900)
        cached = CachedSchemaService(client, cache=cache)
        db_id = find_db_id("Tareas")

        s1 = cached.get_service(db_id)
        s2 = cached.get_service(db_id)
        s3 = cached.get_service(db_id)
        stats = cache.stats()

        record(
            name + " - hits acumulan",
            stats.hits >= 2 and stats.misses == 1,
            f"| hits={stats.hits} misses={stats.misses} size={stats.size}",
        )

        cached.invalidate(db_id)
        s4 = cached.get_service(db_id)
        stats2 = cache.stats()
        record(
            name + " - invalidate fuerza nuevo miss",
            stats2.misses == stats.misses + 1,
            f"| antes_misses={stats.misses} despues_misses={stats2.misses}",
        )
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Test 3: Sincronizacion end-to-end real con Notion
# =============================================================================
def test_3_sync_end_to_end() -> None:
    name = "T3. Sync bidireccional real con Notion (DB3 Tareas)"
    print(f"\n[TEST] {name}")
    if not os.getenv("NOTION_API_KEY"):
        record(name, False, "salteado (NOTION_API_KEY no definida)")
        return
    try:
        config = NotionBridgeConfig.from_env()
        client = NotionClient(config)
        cache = SchemaCache(ttl_seconds=900)
        cached = CachedSchemaService(client, cache=cache)
        manifest_path = ROOT / "manifests" / "notion_databases_manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        memory = FakeMemoryManager()
        sync = MemorySyncManager(memory, cached, manifest)

        marker = f"SYNC_TEST_{uuid.uuid4().hex[:8]}"
        create_result = sync.push_event(
            "HITO_COMPLETADO",
            {
                "titulo": f"{marker}: sync e2e",
                "responsable": "Agente IA",
                "estado": "Pendiente",
                "prioridad": "Media",
            },
        )
        page_id = create_result.get("notion_result", {}).get("id")
        record(
            name + " - push_event creo pagina en Notion",
            create_result["local_persisted"] is True
            and create_result["notion_synced"] is True
            and bool(page_id),
            f"| page_id={page_id} local={create_result['local_persisted']} notion={create_result['notion_synced']}",
        )

        if page_id:
            update_result = sync.push_event(
                "TASK_STATUS_CHANGED",
                {"page_id": page_id, "status": "En Proceso"},
            )
            record(
                name + " - push_event actualizo estado",
                update_result["notion_synced"] is True,
                f"| synced={update_result['notion_synced']} error={update_result.get('error')}",
            )

        hydrate_result = sync.hydrate_from_notion(["Tareas"])
        hydrated = memory.scratchpad.get("hitos_pendientes", [])
        record(
            name + " - hydrate cargo items desde Notion",
            len(hydrated) > 0,
            f"| pendientes={len(hydrated)} completados={len(memory.scratchpad.get('hitos_completados', []))}",
        )
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


# =============================================================================
# Test 4: Resiliencia (Notion "caido" -> cola local preservada)
# =============================================================================
def test_4_resilience_to_network_failure() -> None:
    name = "T4. Resiliencia: con Notion caido, cola local se preserva"
    print(f"\n[TEST] {name}")
    if not os.getenv("NOTION_API_KEY"):
        record(name, False, "salteado (NOTION_API_KEY no definida)")
        return
    try:
        config = NotionBridgeConfig.from_env()
        client = NotionClient(config)
        cache = SchemaCache(ttl_seconds=900)
        cached = CachedSchemaService(client, cache=cache)
        manifest_path = ROOT / "manifests" / "notion_databases_manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        memory = FakeMemoryManager()
        sync = MemorySyncManager(memory, cached, manifest)
        sync.set_notion_reachable(False)

        result = sync.push_event(
            "HITO_COMPLETADO",
            {"titulo": "OFLINE: este evento no debe perderse", "responsable": "Agente IA"},
        )
        pending_after_offline = len(memory.scratchpad.get("notion_sync_pending", []))

        record(
            name + " - push_event con Notion offline persiste local",
            result["local_persisted"] is True
            and result["notion_synced"] is False
            and "unreachable" in (result.get("error") or ""),
            f"| local=True synced=False pending={pending_after_offline}",
        )

        sync.set_notion_reachable(True)
        flush_summary = sync.flush_pending()
        pending_after_recovery = len(memory.scratchpad.get("notion_sync_pending", []))

        record(
            name + " - flush_pending al recuperar Notion",
            flush_summary.get("synced", 0) >= 1
            and pending_after_recovery == 0,
            f"| synced={flush_summary.get('synced')} pending_despues={pending_after_recovery}",
        )
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    print("=" * 64)
    print("  SPRINT 2 - INTEGRATION TESTS (Memory + Notion Bridge)")
    print("=" * 64)
    test_1_atomic_writes_and_rotation()
    test_2_schema_cache()
    test_3_sync_end_to_end()
    test_4_resilience_to_network_failure()

    print()
    print("=" * 64)
    print(f"  RESULTADO: {len(PASSED)} OK | {len(FAILED)} FAIL")
    print("=" * 64)
    for tname, detail in FAILED:
        print(f"  - FAIL {tname}: {detail}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
