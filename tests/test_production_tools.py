"""Local production-tool regression tests."""

from pathlib import Path

from core.persistence import SqliteMemoryStore
from scripts.backup_sqlite import main as backup_main
from scripts.production_check import main as production_check_main


def test_production_check_passes_with_safe_defaults(monkeypatch) -> None:
    monkeypatch.delenv("AIOS_ALLOW_LIVE_EXECUTION", raising=False)
    monkeypatch.delenv("AUTONOMY_MODE", raising=False)
    assert production_check_main() == 0


def test_production_check_rejects_autonomous_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_MODE", "AUTONOMOUS")
    assert production_check_main() == 1


def test_backup_sqlite_preserves_verified_chain(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup" / "copy.db"
    store = SqliteMemoryStore(source)
    store.append_event("TEST", "one", {"value": 1})
    store.close()

    assert backup_main([str(source), str(destination)]) == 0
    restored = SqliteMemoryStore(destination)
    try:
        assert restored.verify_chain() == (True, None)
        assert restored.read_events()[-1]["payload"] == {"value": 1}
    finally:
        restored.close()
