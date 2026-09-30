"""Policies survive the process; revoked ones do not trade (goal G120).

The router's memory dies on restart. Without a durable store, every
deployment boots with no coverage and every revocation issued while the
process was down is moot — the playbook that should have stopped selecting
was never loaded in the first place. This suite covers the store plus the
load path, and the property that makes the load path safe: certification is
re-asked at load, so a revoked strategy's playbook stays in the store but
never joins the router.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.decision_sink import AppendOnlyViolation
from core.migrations import latest_version
from core.playbook_store import (
    PlaybookSeal,
    audit_playbook_log,
    build_postgres_playbook_store,
    build_sqlite_playbook_store,
    set_hash_of,
)
from kernel.playbook import (
    Bound,
    PlaybookAction,
    PlaybookActionKind,
    PlaybookRouter,
    Regime,
)

DSN = os.environ.get("AIOS_TEST_PG_DSN", "")
SECRET = b"k" * 32
OTHER_SECRET = b"x" * 32


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def store(request, tmp_path: Path):
    if request.param == "sqlite":
        yield build_sqlite_playbook_store(tmp_path / "pb.db")
    else:
        import psycopg

        with psycopg.connect(DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE playbooks, playbook_seals")
        handle = build_postgres_playbook_store(DSN, auto_migrate=True)
        try:
            yield handle
        finally:
            handle.close()


def _payload(playbook_id: str = "pb-mom", content_hash: str = "h1") -> tuple[str, str, str, str, str]:
    import json

    return (
        playbook_id,
        "v1",
        content_hash,
        json.dumps({"playbook_id": playbook_id, "version": "v1"}),
        "2024-01-15T00:00:00+00:00",
    )


# ══════════════════════════════════════════════════════════════════════════
# Behavioural parity
# ══════════════════════════════════════════════════════════════════════════


def test_save_and_read_round_trip(store) -> None:
    assert store.save(*_payload()) is True
    rows = store.read_all()
    assert len(rows) == 1
    ref, content, payload = rows[0]
    assert ref == "pb-mom:v1"
    assert content == "h1"
    assert "pb-mom" in payload
    assert store.count() == 1


def test_resaving_identical_content_is_a_no_op(store) -> None:
    assert store.save(*_payload()) is True
    assert store.save(*_payload()) is False
    assert store.count() == 1


def test_rewriting_a_policy_under_its_version_is_refused(store) -> None:
    """A policy that changes under its version is a different policy wearing
    an old name. The primary key refuses it on both tiers; the message names
    the remedy."""
    store.save(*_payload())
    with pytest.raises(AppendOnlyViolation, match="new version"):
        store.save(*_payload(content_hash="h2"))


def test_update_and_delete_are_refused_by_the_schema(store, tmp_path: Path) -> None:
    store.save(*_payload())
    if hasattr(store, "_connection") and isinstance(store._connection, sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._connection.execute(
                "UPDATE playbooks SET payload = '{}' WHERE playbook_id = 'pb-mom'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._connection.execute("DELETE FROM playbooks WHERE playbook_id = 'pb-mom'")
    else:
        import psycopg

        with pytest.raises(psycopg.errors.Error, match="append-only"):
            with store._conn.cursor() as cur:
                cur.execute("UPDATE playbooks SET payload = 'x' WHERE playbook_id = 'pb-mom'")
    assert store.count() == 1


def test_seal_covers_count_and_set(store) -> None:
    store.save(*_payload("pb-a", "ha"))
    store.save(*_payload("pb-b", "hb"))
    seal = store.seal(SECRET)
    assert seal is not None
    assert (seal.event_count, seal.set_hash) == (2, set_hash_of(["ha", "hb"]))
    assert store.audit(SECRET).ok is True


def test_substitution_with_same_count_is_caught(store) -> None:
    """The reason the seal signs the set, not just the count: swapping one
    policy for another keeps the row count and must still fail."""
    store.save(*_payload("pb-a", "ha"))
    store.save(*_payload("pb-b", "hb"))
    seal = store.seal(SECRET)
    assert seal is not None
    rows = [("pb-a:v1", "ha"), ("pb-b:v1", "SUBSTITUTED")]
    audit = audit_playbook_log(rows, store.seals(), SECRET)
    assert audit.ok is False
    assert audit.seal_signature_valid is False


def test_truncation_is_caught(store) -> None:
    store.save(*_payload("pb-a", "ha"))
    store.save(*_payload("pb-b", "hb"))
    store.save(*_payload("pb-c", "hc"))
    store.seal(SECRET)
    shortened = [("pb-a:v1", "ha"), ("pb-b:v1", "hb")]
    audit = audit_playbook_log(shortened, store.seals(), SECRET)
    assert audit.ok is False
    assert audit.truncated is True
    assert "removed" in audit.describe()


def test_unsealed_store_is_unanchored(store) -> None:
    store.save(*_payload())
    audit = store.audit(SECRET)
    assert audit.ok is False
    assert "unanchored" in audit.describe()


def test_sealing_empty_returns_nothing(store) -> None:
    assert store.seal(SECRET) is None


def test_forged_seal_is_reported(store) -> None:
    store.save(*_payload())
    store.seal(SECRET)
    forged = PlaybookSeal(1, set_hash_of(["ha"]), "2024-01-01T00:00:00+00:00", "deadbeef")
    audit = audit_playbook_log([("pb-mom:v1", "h1")], [forged], SECRET)
    assert audit.ok is False
    assert "compromised" in audit.describe()


def test_wrong_key_does_not_verify(store) -> None:
    store.save(*_payload())
    store.seal(SECRET)
    assert store.audit(OTHER_SECRET).ok is False


def test_set_hash_is_order_independent() -> None:
    """Registration order must not affect the seal: the set is what matters."""
    assert set_hash_of(["b", "a"]) == set_hash_of(["a", "b"])


def test_migration_is_registered() -> None:
    assert latest_version() >= 8


# ══════════════════════════════════════════════════════════════════════════
# Router persist and load
# ══════════════════════════════════════════════════════════════════════════


def _certified_router() -> tuple[PlaybookRouter, object]:
    """A router holding one playbook bound to a certified test verdict."""
    from kernel.playbook import build_playbook
    from kernel.strategy_registry import CertificationCheck, CertificationVerdict

    oracle_holder: dict[str, bool] = {"certified": True}

    class _Oracle:
        def verdict_for(self, strategy_id: str, strategy_version: str):
            return None

        def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
            return oracle_holder["certified"]

    router = PlaybookRouter(_Oracle())
    verdict = CertificationVerdict(
        strategy_id="momentum-1",
        strategy_version="v1",
        verdict="CERTIFIED",
        checks=[
            CertificationCheck(
                name="deflated_sharpe",
                passed=True,
                observed=1.8,
                threshold=0.95,
                detail="test",
            )
        ],
        failure_reasons=[],
        observed_sharpe=2.1,
        deflated_sharpe=1.8,
        n_trials=140,
        policy_version="certification/v1",
        validator_id="validator-1",
    )
    playbook = build_playbook(
        playbook_id="pb-momentum",
        version="v1",
        title="trend momentum",
        regime=Regime.TRENDING_UP,
        bounds=(Bound(feature="trend_strength", minimum=0.3, maximum=1.0),),
        action=PlaybookAction(
            kind=PlaybookActionKind.TRADE, target_weight=0.10, reason="test"
        ),
        strategy_id="momentum-1",
        strategy_version="v1",
        verdict=verdict,
    )
    router.register(playbook)
    return router, oracle_holder


def test_persist_and_load_round_trip(store) -> None:
    """Restart the router, not the policies: everything registered before
    the restart selects after it."""
    from kernel.playbook import load_router, persist_router

    router, _ = _certified_router()
    assert persist_router(router, store) == 1

    class _Oracle:
        def verdict_for(self, strategy_id: str, strategy_version: str):
            return None

        def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
            return True

    loaded, skipped = load_router(_Oracle(), store)
    assert loaded.registered() == ("pb-momentum:v1",)
    assert skipped == ()


def test_load_skips_revoked_strategies_but_keeps_them_stored(store) -> None:
    """The load path re-asks certification: a verdict revoked while the
    process was down stays in the store but never joins the router. Dropping
    it from memory is not deleting it — re-certification restores it on the
    next load — but trading it would be acting on a permission withdrawn."""
    router, oracle_holder = _certified_router()
    from kernel.playbook import load_router, persist_router

    persist_router(router, store)
    oracle_holder["certified"] = False

    class _Oracle:
        def verdict_for(self, strategy_id: str, strategy_version: str):
            return None

        def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
            return False

    loaded, skipped = load_router(_Oracle(), store)
    assert loaded.registered() == ()
    assert skipped == ("pb-momentum:v1",)
    assert store.count() == 1
