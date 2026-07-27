"""check_health.py - Verificacion rapida del health endpoint.

Uso:
    python scripts/check_health.py
    python scripts/check_health.py http://localhost:8000/health
    docker compose exec vps_backend python /app/scripts/check_health.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/health"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read()
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            data = json.loads(body)
    except urllib.error.URLError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        print(f"[FAIL] {url} unreachable in {elapsed_ms}ms: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        print(f"[FAIL] {url} error in {elapsed_ms}ms: {exc}", file=sys.stderr)
        return 3

    print(f"[OK] {url} responded in {elapsed_ms}ms (HTTP {resp.status})")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0 if data.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
