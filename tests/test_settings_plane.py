"""Settings plane (plan section 4, item B1).

Versioned 96-field SystemSettings JSON blob: opaque storage, hash-chain audit,
``GET /api/v1/settings/v1`` + ``PUT`` roundtrip. The pre-existing
``GET /api/v1/settings`` (system config) must keep working untouched.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from api.server import CommandCenterServer
from api.views import SystemSnapshotBuilder
from core.persistence import SqliteMemoryStore
from core.settings_plane import SETTINGS_MAX_BYTES, SettingsPlane


def _plane(tmp_path: Path) -> tuple[SettingsPlane, SqliteMemoryStore]:
    store = SqliteMemoryStore(tmp_path / "audit.db")
    plane = SettingsPlane(tmp_path / "settings.db", store=store)
    return plane, store


def _put(port: int, path: str, body: bytes, token: str | None = "test-token") -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        method="PUT",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


def _get(port: int, path: str, token: str | None = "test-token") -> tuple[int, dict[str, Any]]:
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{port}{path}", headers=headers
            ),
            timeout=10,
        ) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


@pytest.fixture(scope="module")
def settings_port(tmp_path_factory: pytest.TempPathFactory) -> Any:
    workdir = tmp_path_factory.mktemp("settings")
    store = SqliteMemoryStore(workdir / "audit.db")
    plane = SettingsPlane(workdir / "settings.db", store=store)
    builder = SystemSnapshotBuilder(store=store, settings_plane=plane)
    server = CommandCenterServer(builder, None, port=0, auth_token="test-token")
    server.start()
    time.sleep(0.3)
    yield server.port
    server.stop()
    store.close()


# ------------------------------------------------------------- plane unit


def test_get_empty_returns_default(tmp_path: Path) -> None:
    plane, _ = _plane(tmp_path)
    assert plane.get_settings() == {}


def test_put_returns_version_and_get_roundtrips(tmp_path: Path) -> None:
    plane, _ = _plane(tmp_path)
    version = plane.put_settings({"theme": "dark", "risk": {"halt_dd_pct": 10.0}}, "op-1")
    assert version == 1
    assert plane.get_settings() == {"theme": "dark", "risk": {"halt_dd_pct": 10.0}}


def test_version_increments(tmp_path: Path) -> None:
    plane, _ = _plane(tmp_path)
    assert plane.put_settings({"a": 1}, "op-1") == 1
    assert plane.put_settings({"a": 2}, "op-1") == 2
    assert plane.get_settings() == {"a": 2}


def test_put_appends_hash_chain_audit_event(tmp_path: Path) -> None:
    plane, store = _plane(tmp_path)
    plane.put_settings({"a": 1}, "op-1")
    events = store.iter_event_payloads("SETTINGS_UPDATED")
    assert len(events) == 1
    assert events[0]["version"] == 1
    assert events[0]["updated_by"] == "op-1"
    ok, _ = store.verify_chain()
    assert ok is True


def test_put_rejects_non_object(tmp_path: Path) -> None:
    plane, _ = _plane(tmp_path)
    with pytest.raises(ValueError, match="JSON object"):
        plane.put_settings(["not", "an", "object"], "op-1")  # type: ignore[arg-type]


def test_put_rejects_oversize_blob(tmp_path: Path) -> None:
    plane, _ = _plane(tmp_path)
    big = {"pad": "x" * (SETTINGS_MAX_BYTES + 1)}
    with pytest.raises(ValueError, match="exceeds"):
        plane.put_settings(big, "op-1")


# ------------------------------------------------------------------ HTTP


def test_http_put_then_get_roundtrip(settings_port: int) -> None:
    status, payload = _put(
        settings_port, "/api/v1/settings/v1", json.dumps({"theme": "dark"}).encode()
    )
    assert status == 200, payload
    assert payload["version"] >= 1
    status, payload = _get(settings_port, "/api/v1/settings/v1")
    assert status == 200
    assert payload["settings"] == {"theme": "dark"}
    assert payload["version"] >= 1


def test_http_put_version_increments(settings_port: int) -> None:
    _, first = _put(
        settings_port, "/api/v1/settings/v1", json.dumps({"v": 1}).encode()
    )
    _, second = _put(
        settings_port, "/api/v1/settings/v1", json.dumps({"v": 2}).encode()
    )
    assert second["version"] == first["version"] + 1


def test_http_put_invalid_json_is_400(settings_port: int) -> None:
    status, payload = _put(settings_port, "/api/v1/settings/v1", b"{not json")
    assert status == 400
    assert "error" in payload


def test_http_put_non_object_json_is_400(settings_port: int) -> None:
    status, payload = _put(settings_port, "/api/v1/settings/v1", b"[1, 2, 3]")
    assert status == 400
    assert "error" in payload


def test_http_put_oversize_is_413_or_400(settings_port: int) -> None:
    big = json.dumps({"pad": "x" * (70 * 1024)}).encode()
    status, payload = _put(settings_port, "/api/v1/settings/v1", big)
    assert status in (400, 413), (status, payload)


def test_http_put_unknown_path_is_404(settings_port: int) -> None:
    status, _ = _put(settings_port, "/api/v1/nope", b"{}")
    assert status == 404


def test_http_put_without_token_is_401(settings_port: int) -> None:
    status, payload = _put(settings_port, "/api/v1/settings/v1", b"{}", token=None)
    assert status == 401
    assert "error" in payload


def test_legacy_settings_route_untouched(settings_port: int) -> None:
    status, payload = _get(settings_port, "/api/v1/settings")
    assert status == 200
    assert "system" in payload


# ------------------------------------------------- serve wiring (plan §6)


def _serve_runner(tmp_path: Path) -> Any:
    """Minimal serve-composition runner: golden CSV + file store, no network."""
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    return ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "serve.db",
    )


def test_serve_builder_wires_settings_plane(tmp_path: Path) -> None:
    runner = _serve_runner(tmp_path)
    builder = runner.build_snapshot_builder()
    assert builder.settings_plane is not None
    payload = builder.settings_plane_view()
    assert payload["available"] is True
    out = builder.settings_plane_put({"theme": "dark"}, "op-1")
    assert out["version"] >= 1
    assert builder.settings_plane_view()["settings"] == {"theme": "dark"}


def test_serve_settings_db_is_store_sibling(tmp_path: Path) -> None:
    runner = _serve_runner(tmp_path)
    runner.build_snapshot_builder()
    assert (tmp_path / "serve.settings.db").exists()
