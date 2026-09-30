"""Dataset versions survive the process; the state machine comes with them (G030).

``DatasetRegistry`` kept every version in memory: the exact data a backtest
ran on, pinned by content hash, gone on restart. A version that dies with the
process makes its backtest unreproducible months later — nobody re-registers
a dataset daily, so the loss surfaces as archaeology rather than as an error.
This suite covers the durable log plus resume, on both tiers, and the
no-phantom discipline the append-only log demands.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.dataset_version_sink import (
    build_dataset_version_ledger,
    build_postgres_dataset_version_sink,
    build_sqlite_dataset_version_sink,
)
from core.experiment_sink import AppendOnlyViolation
from core.migrations import latest_version
from kernel.bootstrap import create_kernel
from kernel.registries import DatasetRegistry, DatasetStatus
from kernel.state_machine import TransitionError

DSN = os.environ.get("AIOS_TEST_PG_DSN", "")
SECRET = b"k" * 32


def _register(
    registry: DatasetRegistry,
    dataset_id: str = "bars",
    version: str = "v1",
) -> None:
    registry.register(
        dataset_id=dataset_id,
        version=version,
        source="test-feed",
        schema_hash="schema-1",
        content_hash="content-1",
        time_start="2024-01-01",
        time_end="2024-06-01",
        row_count=1000,
        actor_id="system",
        as_of_semantics="available_at",
        bitemporal=True,
        immutable_hash="frozen-1",
    )


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def sink(request, tmp_path: Path):
    if request.param == "sqlite":
        yield build_sqlite_dataset_version_sink(tmp_path / "ds.db")
    else:
        import psycopg

        with psycopg.connect(DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE dataset_version_events, dataset_version_seals")
        store = build_postgres_dataset_version_sink(DSN, auto_migrate=True)
        try:
            yield store
        finally:
            store.close()


@pytest.fixture()
def registry(sink) -> DatasetRegistry:
    kernel = create_kernel()
    return DatasetRegistry(kernel.state_machine, kernel.provenance, sink)


# ══════════════════════════════════════════════════════════════════════════
# Durability and resume
# ══════════════════════════════════════════════════════════════════════════


def test_a_version_lifecycle_survives_the_process(registry: DatasetRegistry, sink) -> None:
    """Register, validate, activate — then forget everything and rebuild.
    Status, hashes, and PIT qualification must come back intact."""
    _register(registry)
    registry.validate("bars", "v1", "validator")
    registry.activate("bars", "v1", "operator")

    kernel = create_kernel()
    resumed = DatasetRegistry.resume(kernel.state_machine, kernel.provenance, sink)
    version = resumed.get("bars", "v1")
    assert version.status is DatasetStatus.ACTIVE
    assert version.content_hash == "content-1"
    assert version.immutable_hash == "frozen-1"
    assert version.is_pit_qualified() is True
    assert version.reference()["content_hash"] == "content-1"
    assert kernel.state_machine.get_state("bars:v1", "bars:v1") == "ACTIVE"


def test_an_illegal_transition_writes_nothing(
    registry: DatasetRegistry, sink
) -> None:
    """The phantom discipline, same as the experiment ledger: legality is
    pre-checked because the sink cannot un-write. Activating a DRAFT version
    must fail before the ACTIVATED event, not after it."""
    _register(registry)
    before = sink.count()
    with pytest.raises(TransitionError):
        registry.activate("bars", "v1", "operator")
    assert sink.count() == before
    assert registry.get("bars", "v1").status is DatasetStatus.DRAFT


def test_a_duplicate_registration_writes_nothing(
    registry: DatasetRegistry, sink
) -> None:
    _register(registry)
    before = sink.count()
    with pytest.raises(ValueError, match="already exists"):
        _register(registry)
    assert sink.count() == before


def test_resume_rebuilds_provenance_without_replaying_transitions(
    registry: DatasetRegistry, sink
) -> None:
    """State objects restored at status, not transitioned there: replaying
    would re-emit receipts for history that already happened."""
    _register(registry)
    registry.validate("bars", "v1", "validator")

    kernel = create_kernel()
    before = len(kernel.state_machine._transitions)
    DatasetRegistry.resume(kernel.state_machine, kernel.provenance, sink)
    assert len(kernel.state_machine._transitions) == before
    assert kernel.state_machine.get_state("bars:v1", "bars:v1") == "VALIDATED"


# ══════════════════════════════════════════════════════════════════════════
# Schema enforcement and seals
# ══════════════════════════════════════════════════════════════════════════


def test_update_and_delete_are_refused(sink) -> None:
    """Raw SQL around the API. The refusal comes from the schema on both
    tiers; the sqlite message names the tamper class."""
    sink.append("bars:v1", "REGISTERED", "{}", "t")
    if hasattr(sink, "_connection") and isinstance(sink._connection, sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            sink._connection.execute(
                "UPDATE dataset_version_events SET payload = '{}' WHERE seq = 1"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            sink._connection.execute("DELETE FROM dataset_version_events WHERE seq = 1")
    else:
        import psycopg

        with pytest.raises(psycopg.errors.Error, match="append-only"):
            with sink._conn.cursor() as cur:
                cur.execute("UPDATE dataset_version_events SET payload = 'x' WHERE seq = 1")
    assert sink.count() == 1


def test_off_head_linkage_is_refused(sink) -> None:
    """A second genesis for the same key is a forked history, refused by name
    on sqlite and by the shared function on postgres."""
    sink.append("bars:v1", "REGISTERED", "{}", "t")
    if hasattr(sink, "_connection") and isinstance(sink._connection, sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError, match="chain break"):
            sink._connection.execute(
                "INSERT INTO dataset_version_events (seq, dataset_key, event_type, "
                "supersedes, recorded_at, payload) VALUES (2, 'bars:v1', 'X', 0, 't', '{}')"
            )
    else:
        import psycopg

        with pytest.raises(psycopg.errors.Error, match="append-only"):
            with sink._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_version_events (seq, dataset_key, event_type, "
                    "supersedes, recorded_at, payload) VALUES (2, 'bars:v1', 'X', 0, 't', '{}')"
                )


def test_seal_and_truncation_audit(sink) -> None:
    """The seal signs (count, head); a shortened log presents a head no seal
    covers. Same truncation argument as the sibling ledgers, same answer."""
    from core.experiment_sink import audit_experiment_log

    sink.append("bars:v1", "REGISTERED", "{}", "t")
    sink.append("bars:v1", "VALIDATED", "{}", "t")
    sink.append("bars:v1", "ACTIVATED", "{}", "t")
    assert sink.seal(SECRET) is not None
    assert sink.audit(SECRET).ok is True

    shortened = sink.read_events()[:2]
    caught = audit_experiment_log(shortened, sink.seals(), SECRET)
    assert caught.ok is False
    assert caught.truncated is True


def test_unsealed_log_is_unanchored(sink) -> None:
    sink.append("bars:v1", "REGISTERED", "{}", "t")
    audit = sink.audit(SECRET)
    assert audit.ok is False
    assert audit.sealed_through is None
    assert "unanchored" in audit.describe()


def test_empty_key_is_refused(sink) -> None:
    with pytest.raises(AppendOnlyViolation, match="must not be empty"):
        sink.append("", "REGISTERED", "{}", "t")


def test_migration_is_registered() -> None:
    assert latest_version() >= 7


def test_fresh_database_gets_v7_tables(tmp_path: Path) -> None:
    handle = build_dataset_version_ledger(tmp_path / "new.db", SECRET)
    try:
        tables = {
            str(r[0])
            for r in handle.sink._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"dataset_version_events", "dataset_version_seals"} <= tables
    finally:
        handle.close()


def test_ledger_without_secret_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sealing secret"):
        build_dataset_version_ledger(tmp_path / "nokey.db", b"")


def test_sinkless_registry_is_unchanged() -> None:
    """Omitting the sink changes nothing: every pre-existing caller
    constructs the registry without one."""
    kernel = create_kernel()
    plain = DatasetRegistry(kernel.state_machine, kernel.provenance)
    assert plain.sink is None
    _register(plain)
    plain.validate("bars", "v1", "validator")
    assert plain.get("bars", "v1").status is DatasetStatus.VALIDATED
