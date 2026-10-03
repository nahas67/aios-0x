"""Audit every GET route for HTTP 500.

Runs the real server (`CommandCenterServer`) over a real builder and reports the status of
every route, so the 500 inventory is measured rather than reasoned about.

Usage:  python scripts/audit_http_500.py [--verbose]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
sys.path.insert(0, str(REPO))

from api.server import CommandCenterServer  # noqa: E402
from api.views import SystemSnapshotBuilder  # noqa: E402
from core.persistence import SqliteMemoryStore  # noqa: E402

# Query strings where the route needs one to get past its own validation.
PARAMS = {
    "/api/v1/market/candles": "?symbol=BTC/USD&timeframe=1d",
    "/api/v1/decisions/1": "",
    "/api/v1/knowledge/1": "",
    "/api/v1/financial/orders/1": "",
    "/api/v1/financial/lockouts/": "",
    "/api/v1/stream": "?interval_s=3600",
}


def routes() -> list[str]:
    src = (REPO / "api" / "server.py").read_text(encoding="utf-8")
    exact = re.findall(r'path == "(/api/v1/[^"]+)"', src)
    prefixes = re.findall(r'path\.startswith\("(/api/v1/[^"]+)"\)', src)
    seen: list[str] = []
    for r in [*exact, *prefixes, "/metrics"]:
        if r not in seen:
            seen.append(r)
    return seen


def get(port: int, path: str) -> tuple[int, object]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except (json.JSONDecodeError, ValueError):
                return resp.status, raw[:200].decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, raw[:200].decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - the audit reports connection failures too
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    verbose = "--verbose" in sys.argv
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="audit500_"))
    store = SqliteMemoryStore(tmp / "audit.db")
    store.append_event("SEED", None, {"n": 1})

    # A deliberately BARE builder: only the store is wired. This is the realistic shape of a
    # dev server or a composition root that has not finished booting, and it is where
    # "component is None" AttributeErrors surface as 500s.
    builder = SystemSnapshotBuilder(store=store)
    server = CommandCenterServer(builder, None, port=0)
    server.start()
    time.sleep(0.4)

    results: list[tuple[str, int, object]] = []
    try:
        for route in routes():
            path = route + PARAMS.get(route, "")
            results.append((route, *get(server.port, path)))
    finally:
        server.stop()
        store.close()

    counts: dict[int, int] = {}
    for _, status, _ in results:
        counts[status] = counts.get(status, 0) + 1

    print("=== status distribution ===")
    for status in sorted(counts):
        label = {200: "200 OK", 400: "400 bad request", 401: "401 auth",
                 403: "403 forbidden", 404: "404 not found", 500: "500 SERVER ERROR",
                 -1: "connection failure"}.get(status, str(status))
        print(f"  {label:22} {counts[status]}")

    server_errors = [(r, s, b) for r, s, b in results if s == 500]
    print()
    print(f"=== HTTP 500 inventory: {len(server_errors)} route(s) ===")
    for route, _, body in server_errors:
        detail = body.get("error") if isinstance(body, dict) else body
        print(f"  {route}")
        print(f"      {str(detail)[:220]}")

    dropped = [(r, s, b) for r, s, b in results if s == -1]
    if dropped:
        print()
        print(f"=== connection failures: {len(dropped)} ===")
        for route, _, body in dropped:
            print(f"  {route}  {body}")

    if verbose:
        print()
        print("=== every route ===")
        for route, status, body in results:
            detail = body.get("error") if isinstance(body, dict) else ""
            print(f"  {status:>4}  {route}  {str(detail)[:100]}")

    return 1 if server_errors else 0


if __name__ == "__main__":
    sys.exit(main())
