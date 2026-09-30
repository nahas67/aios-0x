"""The experiment ledger has to outlive the process (goal G070).

``ExperimentRegistry`` kept every run — every failure and its reason, every
verdict, the whole derivation tree — in a dict. On restart, the programme
forgot what it tried, forgot why it failed, and forgot how many things it
tried to find the one that worked. A Sharpe quoted without that denominator
is an anecdote with a decimal point, and an anecdote is what this ledger
exists to prevent.

This suite mirrors the governance-ledger suite's structure because the
guarantee is the same shape: append-only by schema rather than by promise,
and an HMAC seal because a record over the entries present verifies perfectly
over a shortened one. The one property unique to this ledger is the
truncation prize: cut the tail and 10,000 failures disappear while the lucky
result remains. Every seal test below is written from that attacker's
position.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.experiment_sink import (
    AppendOnlyViolation,
    ExperimentLedger,
    ExperimentSeal,
    audit_experiment_log,
    build_experiment_ledger,
)
from core.migrations import latest_version
from kernel.bootstrap import create_kernel
from kernel.registries import ExperimentRegistry, ExperimentStatus
from kernel.state_machine import TransitionError

SECRET = b"k" * 32
OTHER_SECRET = b"x" * 32


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def ledger(tmp_path: Path) -> ExperimentLedger:
    handle = build_experiment_ledger(tmp_path / "experiments.db", SECRET)
    yield handle
    handle.close()


@pytest.fixture()
def registry(ledger: ExperimentLedger) -> ExperimentRegistry:
    kernel = create_kernel()
    return ExperimentRegistry(kernel.state_machine, kernel.provenance, ledger.sink)


def _create(
    registry: ExperimentRegistry,
    experiment_id: str = "exp-1",
    *,
    parent_id: str | None = None,
    hypothesis_id: str = "hyp-1",
) -> object:
    return registry.create(
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
        configuration={"lookback": 20, "threshold": 0.5},
        random_seed=7,
        parent_id=parent_id,
    )


# ══════════════════════════════════════════════════════════════════════════
# Durability: the ledger survives the process
# ══════════════════════════════════════════════════════════════════════════


def test_a_full_lifecycle_is_readable_after_the_process_dies(
    tmp_path: Path, registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """The defect this goal fixes, stated as a test."""
    _create(registry, "exp-1")
    _create(registry, "exp-2", parent_id="exp-1")
    _create(registry, "exp-3", hypothesis_id="hyp-2")
    registry.start("exp-1", "system")
    registry.complete("exp-1", "system", {"sharpe": 1.8})
    registry.attach_verdict("exp-1", verdict="CERTIFIED", deflated_sharpe=1.62)
    registry.start("exp-2", "system")
    registry.fail("exp-2", "system", "deflated sharpe 0.31 below the 0.95 bar")
    registry.start("exp-3", "system")
    ledger.seal()
    path = tmp_path / "experiments.db"

    reopened = build_experiment_ledger(path, SECRET)
    try:
        kernel = create_kernel()
        resumed = ExperimentRegistry.resume(
            kernel.state_machine, kernel.provenance, reopened.sink
        )
        assert resumed.get("exp-1").status is ExperimentStatus.COMPLETED
        assert resumed.get("exp-1").certification_verdict == "CERTIFIED"
        assert resumed.get("exp-1").deflated_sharpe == pytest.approx(1.62)
        assert resumed.get("exp-2").status is ExperimentStatus.FAILED
        assert (
            resumed.get("exp-2").failure_reason
            == "deflated sharpe 0.31 below the 0.95 bar"
        )
        assert resumed.get("exp-3").status is ExperimentStatus.RUNNING
        assert [r.experiment_id for r in resumed.lineage("exp-2")] == ["exp-1", "exp-2"]
        assert resumed.attempt_count() == {"hyp-1": 2, "hyp-2": 1}
        assert {f.experiment_id for f in resumed.failures()} == {"exp-2"}
        # The reproducibility hash is stable across the restart: the same
        # configuration must hash the same on both sides of it.
        assert (
            resumed.get("exp-1").reproducibility_hash
            == registry.get("exp-1").reproducibility_hash
        )
        assert reopened.audit().ok is True
    finally:
        reopened.close()


def test_state_machine_objects_are_restored_at_their_status(
    tmp_path: Path, registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Resume restores sm objects without replaying transitions.

    Replaying would re-emit receipts; restoring sets the state directly. The
    observable difference is what matters here: the resumed registry enforces
    the lifecycle from the restored state.
    """
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "bad fill model")
    ledger.seal()
    path = tmp_path / "experiments.db"

    reopened = build_experiment_ledger(path, SECRET)
    try:
        kernel = create_kernel()
        resumed = ExperimentRegistry.resume(
            kernel.state_machine, kernel.provenance, reopened.sink
        )
        assert kernel.state_machine.get_state("experiment", "exp-1") == "FAILED"
        with pytest.raises(TransitionError):
            resumed.start("exp-1", "system")
    finally:
        reopened.close()


def test_resume_on_an_empty_sink_yields_an_empty_registry(
    tmp_path: Path, ledger: ExperimentLedger
) -> None:
    kernel = create_kernel()
    resumed = ExperimentRegistry.resume(
        kernel.state_machine, kernel.provenance, ledger.sink
    )
    assert resumed.attempt_count() == {}
    assert resumed.failures() == []


def test_every_field_survives_the_round_trip(
    tmp_path: Path, registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """A log that loses the configuration is not a reproducibility log.

    The fields a re-run would need — versions, seed, configuration — are
    exactly the ones a naive "store the outcome" implementation drops.
    """
    registry.create(
        experiment_id="exp-1",
        hypothesis_id="hyp-1",
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
        feature_versions=["f1:v3", "f2:v1"],
        model_versions=["m1:v2"],
        configuration={"lookback": 20, "nested": {"a": [1, 2, 3]}},
        random_seed=99,
        environment="gpu-cluster",
    )
    registry.start("exp-1", "system")
    registry.complete("exp-1", "system", {"sharpe": 2.1})
    ledger.seal()
    path = tmp_path / "experiments.db"

    reopened = build_experiment_ledger(path, SECRET)
    try:
        kernel = create_kernel()
        resumed = ExperimentRegistry.resume(
            kernel.state_machine, kernel.provenance, reopened.sink
        )
        run = resumed.get("exp-1")
        assert run.feature_versions == ["f1:v3", "f2:v1"]
        assert run.model_versions == ["m1:v2"]
        assert run.configuration == {"lookback": 20, "nested": {"a": [1, 2, 3]}}
        assert run.random_seed == 99
        assert run.environment == "gpu-cluster"
        assert run.result == {"sharpe": 2.1}
        assert run.started_at and run.completed_at
    finally:
        reopened.close()


# ══════════════════════════════════════════════════════════════════════════
# The sink is written before the memory commits — and nothing phantom
# ══════════════════════════════════════════════════════════════════════════


def test_an_illegal_transition_writes_nothing(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """The property that justifies the pre-check.

    The sink is append-only, so an event written for a transition that never
    happened is permanent: resume would honour it, promoting a programming
    error into durable history. Legality is therefore checked before the sink
    write, and the proof is that a refused transition leaves no event.
    """
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "bad fill model")
    before = ledger.sink.count()
    with pytest.raises(TransitionError):
        registry.start("exp-1", "system")
    assert ledger.sink.count() == before


def test_a_rejected_failure_reason_writes_nothing(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Validation precedes the sink write in every method, not just the ones
    with a state transition. An empty reason must not leave a CREATED run's
    twin or a half-written FAILED event behind."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    before = ledger.sink.count()
    with pytest.raises(ValueError, match="requires a failure_reason"):
        registry.fail("exp-1", "system", "   ")
    assert ledger.sink.count() == before
    assert registry.get("exp-1").status is ExperimentStatus.RUNNING


def test_a_duplicate_create_writes_nothing(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    _create(registry, "exp-1")
    before = ledger.sink.count()
    with pytest.raises(ValueError, match="already exists"):
        _create(registry, "exp-1")
    assert ledger.sink.count() == before


def test_a_dangling_parent_writes_nothing(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    _create(registry, "exp-1")
    before = ledger.sink.count()
    with pytest.raises(KeyError, match="parent experiment not found"):
        _create(registry, "exp-2", parent_id="does-not-exist")
    assert ledger.sink.count() == before


def test_a_verdict_on_an_unfinished_run_writes_nothing(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    before = ledger.sink.count()
    with pytest.raises(ValueError, match="only a completed run"):
        registry.attach_verdict("exp-1", verdict="CERTIFIED")
    assert ledger.sink.count() == before


# ══════════════════════════════════════════════════════════════════════════
# The schema refuses to be tampered with
# ══════════════════════════════════════════════════════════════════════════


def test_an_update_is_refused_by_the_database(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Raw SQL, the way an attacker with a file handle would — around the
    store API entirely — and the schema still refuses."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo too high")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "UPDATE experiment_events SET payload = '{}' WHERE seq = 3"
        )
    assert "append-only" in str(excinfo.value)
    assert "UPDATE" in str(excinfo.value)


def test_a_delete_is_refused_by_the_database(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """This is how a failure disappears: the FAILED event is removed and the
    run reads back as RUNNING forever, or vanishes from the denominator."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo too high")
    ledger.seal()
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "DELETE FROM experiment_events WHERE event_type = 'FAILED'"
        )
    assert "DELETE" in str(excinfo.value)
    assert ledger.sink.count() == 3
    assert registry.failures()[0].failure_reason == "pbo too high"


def test_a_seal_cannot_be_deleted_either(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    _create(registry, "exp-1")
    ledger.seal()
    with pytest.raises(sqlite3.IntegrityError):
        ledger.sink._connection.execute("DELETE FROM experiment_seals WHERE seal_id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.sink._connection.execute(
            "UPDATE experiment_seals SET signature = 'x' WHERE seal_id = 1"
        )
    assert len(ledger.sink.seals()) == 1


def test_an_out_of_sequence_insert_is_refused_by_the_schema(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """A splice that skips an event leaves a hole no linkage check would see,
    because per-experiment linkage only constrains order within one
    experiment, not the global sequence."""
    _create(registry, "exp-1")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "INSERT INTO experiment_events (seq, experiment_id, event_type, "
            "supersedes, recorded_at, payload) "
            "VALUES (99, 'exp-1', 'STARTED', 1, 't', '{}')"
        )
    assert "sequence break" in str(excinfo.value)
    assert ledger.sink.count() == 1


def test_an_event_that_skips_its_predecessor_is_refused_by_the_schema(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """The per-experiment chain: an event for exp-1 claiming supersedes=0
    when exp-1 already has two events is a fork, and a fork is how a FAILED
    run gets a second, cleaner history written alongside the real one."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "INSERT INTO experiment_events (seq, experiment_id, event_type, "
            "supersedes, recorded_at, payload) "
            "VALUES (3, 'exp-1', 'COMPLETED', 0, 't', '{}')"
        )
    assert "chain break" in str(excinfo.value)
    assert "supersedes" in str(excinfo.value)


def test_an_empty_experiment_id_is_refused(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    with pytest.raises(AppendOnlyViolation, match="must not be empty"):
        ledger.sink.append("", "CREATED", "{}", "t")


# ══════════════════════════════════════════════════════════════════════════
# Truncation — the case a linkage check alone cannot catch
# ══════════════════════════════════════════════════════════════════════════


def test_a_truncated_log_links_cleanly_and_that_is_the_problem(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Documented deliberately: this is the trap the seal exists to escape.

    A shortened log links perfectly — every remaining event still supersedes
    its experiment's head *within the shortened log*. Anyone extending the
    audit must know that linkage alone is insufficient, because it is exactly
    the check that looks sufficient.
    """
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo too high")
    _create(registry, "exp-2")
    registry.start("exp-2", "system")
    registry.fail("exp-2", "system", "no edge after costs")
    ledger.seal()

    events = ledger.sink.read_events()
    truncated = [e for e in events if e.seq <= 3]

    naive = audit_experiment_log(truncated)
    assert naive.chain_intact is True

    caught = audit_experiment_log(truncated, ledger.sink.seals(), SECRET)
    assert caught.ok is False
    assert caught.truncated is True
    assert "tail was cut" in caught.describe()


def test_the_seal_is_what_catches_a_cut_tail(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """The headline property: the failures are what a cut tail removes, and
    the seal is what notices they are gone."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "the failure someone would cut")
    ledger.seal()
    assert ledger.audit().ok is True

    shortened = ledger.sink.read_events()[:2]
    after = audit_experiment_log(shortened, ledger.sink.seals(), SECRET)
    assert after.ok is False
    assert after.truncated is True


def test_an_unsealed_log_is_unanchored_not_clean(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """No seal is not a pass. "Nobody ever called seal()" and "everything
    checked out" must not look alike."""
    _create(registry, "exp-1")
    audit = ledger.audit()
    assert audit.ok is False
    assert audit.sealed_through is None
    assert "unanchored" in audit.describe()


def test_entries_after_a_seal_are_reported_as_an_unanchored_tail(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Legitimate after a restart — and named as unverified rather than
    assumed. Until resealed, a truncation inside that window is invisible."""
    _create(registry, "exp-1")
    ledger.seal()
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "late failure")

    audit = ledger.audit()
    assert audit.chain_intact is True
    assert audit.seal_signature_valid is True
    assert audit.sealed_through == 1
    assert audit.unsealed_events == 2
    assert audit.ok is False
    assert "unanchored" in audit.describe()


def test_resealing_covers_the_new_tail(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    _create(registry, "exp-1")
    ledger.seal()
    registry.start("exp-1", "system")
    assert ledger.audit().ok is False
    ledger.seal()
    audit = ledger.audit()
    assert audit.ok is True
    assert audit.sealed_through == 2


def test_sealing_an_empty_log_returns_nothing(ledger: ExperimentLedger) -> None:
    """A seal over nothing would attest to no trials at all."""
    assert ledger.seal() is None
    assert ledger.audit().ok is False


# ══════════════════════════════════════════════════════════════════════════
# The seal cannot be forged
# ══════════════════════════════════════════════════════════════════════════


def test_a_seal_signed_with_another_key_does_not_verify() -> None:
    seal = ExperimentSeal.sign(3, 3, "2024-01-01T00:00:00+00:00", SECRET)
    assert seal.verify(SECRET) is True
    assert seal.verify(OTHER_SECRET) is False


def test_editing_a_seal_in_place_invalidates_its_signature() -> None:
    seal = ExperimentSeal.sign(3, 3, "2024-01-01T00:00:00+00:00", SECRET)
    assert ExperimentSeal(3, 2, seal.sealed_at, seal.signature).verify(SECRET) is False
    assert ExperimentSeal(9, 3, seal.sealed_at, seal.signature).verify(SECRET) is False
    assert ExperimentSeal(3, 3, "later", seal.signature).verify(SECRET) is False


def test_a_forged_seal_is_reported_as_compromised(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """The message must not read as a clean log with a missing checkpoint."""
    _create(registry, "exp-1")
    ledger.seal()
    forged = ExperimentSeal(1, 1, "2024-01-01T00:00:00+00:00", "deadbeef")
    audit = audit_experiment_log(ledger.sink.read_events(), [forged], SECRET)
    assert audit.ok is False
    assert audit.seal_signature_valid is False


def test_auditing_without_a_key_reports_no_signature_claim(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Absence of a key is not evidence of validity."""
    _create(registry, "exp-1")
    ledger.seal()
    audit = audit_experiment_log(ledger.sink.read_events(), ledger.sink.seals(), None)
    assert audit.ok is False
    assert audit.seal_signature_valid is False


# ══════════════════════════════════════════════════════════════════════════
# Linkage breaks the middle cases the seal does not cover
# ══════════════════════════════════════════════════════════════════════════


def test_a_forked_event_breaks_linkage(ledger: ExperimentLedger) -> None:
    """Two events both claiming the same predecessor is a forked history —
    the shape a rewritten FAILED run takes when it cannot edit the original."""
    from core.experiment_sink import ExperimentEvent

    events = [
        ExperimentEvent(1, "exp-1", "CREATED", 0, "t", "{}"),
        ExperimentEvent(2, "exp-1", "STARTED", 1, "t", "{}"),
        ExperimentEvent(3, "exp-1", "COMPLETED", 1, "t", "{}"),
    ]
    audit = audit_experiment_log(events)
    assert audit.chain_intact is False
    assert audit.ok is False
    assert "linkage broken" in audit.describe()


def test_a_gapped_sequence_breaks_the_audit(ledger: ExperimentLedger) -> None:
    """Contiguity is rechecked on read, not just enforced on write: a gap is
    a removed event, and removal is the tamper this ledger most fears."""
    from core.experiment_sink import ExperimentEvent

    events = [
        ExperimentEvent(1, "exp-1", "CREATED", 0, "t", "{}"),
        ExperimentEvent(3, "exp-1", "STARTED", 1, "t", "{}"),
    ]
    assert audit_experiment_log(events).chain_intact is False


def test_an_empty_log_links_cleanly_but_is_not_ok(ledger: ExperimentLedger) -> None:
    audit = audit_experiment_log([])
    assert audit.chain_intact is True
    assert audit.ok is False


# ══════════════════════════════════════════════════════════════════════════
# Round-trip fidelity and the facade
# ══════════════════════════════════════════════════════════════════════════


def test_snapshots_hold_the_latest_state_per_experiment(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Current state is the latest event per experiment — the read the resume
    path depends on, so it is asserted directly rather than only through it."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "reason one")
    snapshots = ledger.snapshots()
    assert set(snapshots) == {"exp-1"}
    from kernel.registries import ExperimentRun

    run = ExperimentRun.model_validate_json(snapshots["exp-1"])
    assert run.status is ExperimentStatus.FAILED
    assert run.failure_reason == "reason one"


def test_first_seen_order_is_creation_order(
    registry: ExperimentRegistry, ledger: ExperimentLedger
) -> None:
    """Resume replays creation order so parent links resolve. Alphabetical
    would dangle a child created before its parent's name sorts first —
    which is most children, since derivations usually extend the id."""
    _create(registry, "exp-z-root")
    _create(registry, "exp-a-child", parent_id="exp-z-root")
    assert list(ledger.snapshots()) == ["exp-z-root", "exp-a-child"]


def test_the_migration_is_registered() -> None:
    """The durable ledger is a schema step, so it must be one version."""
    assert latest_version() >= 5


def test_a_fresh_database_gets_the_ledger_schema(tmp_path: Path) -> None:
    handle = build_experiment_ledger(tmp_path / "new.db", SECRET)
    try:
        tables = {
            str(r[0])
            for r in handle.sink._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"experiment_events", "experiment_seals"} <= tables
    finally:
        handle.close()


def test_building_a_ledger_without_a_secret_is_refused(tmp_path: Path) -> None:
    """An unsealable ledger cannot be verified, so it is not offered."""
    with pytest.raises(ValueError, match="sealing secret"):
        build_experiment_ledger(tmp_path / "nokey.db", b"")


def test_a_sinkless_registry_is_unchanged() -> None:
    """The sink is optional, and omitting it changes nothing.

    Every pre-existing test constructs the registry without one; this pins
    that the durable path is additive rather than a behaviour change."""
    kernel = create_kernel()
    plain = ExperimentRegistry(kernel.state_machine, kernel.provenance)
    assert plain.sink is None
    plain.create(
        experiment_id="exp-1",
        hypothesis_id="hyp-1",
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
    )
    assert plain.get("exp-1").status is ExperimentStatus.CREATED
