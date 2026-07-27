"""Atomic I/O para agent_scratchpad.json.

Garantias:
  - Escritura atómica: temp file en el mismo dir + os.replace (mismo filesystem).
  - Concurrencia segura: filelock con timeout configurable.
  - Crash-safe: si el proceso muere a mitad de escritura, el archivo original
    queda intacto; el .tmp queda y se sobreescribe en el siguiente write.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock

logger = logging.getLogger(__name__)


class ScratchpadIO:
    """Lector/escritor thread-safe y crash-safe para un JSON del scratchpad."""

    def __init__(self, path: str | os.PathLike[str], lock_timeout: int = 10) -> None:
        self._path = Path(path)
        self._lock_path = Path(str(self._path) + ".lock")
        self._lock = FileLock(str(self._lock_path), timeout=lock_timeout)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self._path.exists():
                return {}
            with open(self._path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(data)

    def read_modify_write(
        self, modifier: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """Lee, aplica `modifier`, escribe atomicamente. Devuelve el estado final."""
        with self._lock:
            current: dict[str, Any] = {}
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    current = json.loads(content)
            updated = modifier(current)
            self._atomic_write(updated)
            return updated

    def exists(self) -> bool:
        return self._path.exists()

    def size_bytes(self) -> int:
        if not self._path.exists():
            return 0
        return self._path.stat().st_size

    def _atomic_write(self, data: dict[str, Any]) -> None:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=self._path.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
            logger.debug(
                "scratchpad_io.atomic_write path=%s bytes=%d",
                self._path, self._path.stat().st_size,
            )
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
