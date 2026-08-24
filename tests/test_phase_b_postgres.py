"""Phase B data-layer tests: PostgreSQL memory store + backend selection.

The factory logic is tested hermetically. The live PostgreSQL round-trip runs
only when ``AIOS_TEST_PG_DSN`` is set (e.g. a disposable container:

    docker run --rm -e POSTGRES_PASSWORD=aios -p 5432:5432 postgres:16

    set AIOS_TEST_PG_DSN=postgresql://postgres:aios@localhost:5432/postgres
); otherwise those tests skip — CI and local suites stay green everywhere.
"""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.config import Settings
from core.persistence import BaseMemoryStore, SqliteMemoryStore, _canonical
from core.pg_store import PostgresMemoryStore
from core.store_factory import build_memory_store, select_store_class
from schemas.contracts import ObservationReport, PredictionRecord
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner

PG_DSN = os.environ.get("AIOS_TEST_PG_DSN", "")

# --------------------------------------------------------------- selection


def test_select_defaults_to_sqlite() -> None:
    assert select_store_class(None) is SqliteMemoryStore
    assert select_store_class("") is SqliteMemoryStore
    assert select_store_class("sqlite:///data/x.db") is SqliteMemoryStore


def test_select_postgres_by_dsn_scheme() -> None:
    assert select_store_class("postgres://u:p@h:5432/db") is PostgresMemoryStore
    assert select_store_class("postgresql://u:p@h:5432/db") is PostgresMemoryStore


def test_build_memory_store_sqlite_default(tmp_path: Path) -> None:
    store = build_memory_store(tmp_path / "x.db")
    assert isinstance(store, SqliteMemoryStore)
    seq = store.append_event("TEST", "r1", {"a": 1})
    assert seq == 1
    ok, _bad = store.verify_chain()
    assert ok
    store.close()


def test_runner_defaults_to_sqlite_without_dsn(tmp_path: Path) -> None:
    """Runner with store=None must land on SQLite when no DSN configured."""
    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=30)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "run.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=Settings(model_provider="none", database_url=None),
    )
    assert isinstance(runner.store, SqliteMemoryStore)


# ------------------------------------------------------- chain semantics


def test_pg_and_sqlite_chains_share_semantics(tmp_path: Path) -> None:
    """Canonical payload hashing + genesis are byte-identical across backends."""
    from core.persistence import _GENESIS_HASH as SQLITE_GENESIS
    from core.pg_store import _GENESIS_HASH as PG_GENESIS

    assert PG_GENESIS == SQLITE_GENESIS
    assert _canonical({"b": 2, "a": 1}) == '{"a":1,"b":2}'

    sqlite_store = SqliteMemoryStore(tmp_path / "local.db")
    seq = sqlite_store.append_event("KIND", "ref", {"x": 1})
    assert seq == 1
    ok, bad = sqlite_store.verify_chain()
    assert ok and bad is None
    sqlite_store.close()


def test_all_stores_satisfy_memory_contract() -> None:
    for cls in (SqliteMemoryStore, PostgresMemoryStore):
        assert issubclass(cls, BaseMemoryStore)


def test_prediction_record_scores_like_runner_flow(tmp_path: Path) -> None:
    """Typed-table payload used by both backends stays contract-stable."""
    prediction = PredictionRecord(
        hypothesis_id="hyp-x",
        symbol="SPY",
        direction="BUY",
        entry_reference_price=100.0,
        target_price=110.0,
        stop_price=95.0,
        horizon_timeframe="1d",
        confidence_score=80.0,
        expected_risk_reward_ratio=2.0,
        decision_bar_timestamp=datetime.now(UTC),
        is_simulated=True,
    )
    scored = prediction.score(
        exit_price=109.0, exit_reason="TARGET_HIT", realized_pnl=90.0, direction_correct=True
    )
    store = SqliteMemoryStore(tmp_path / "p.db")
    store.save_prediction(prediction)
    store.save_prediction(scored)
    observation = ObservationReport(
        execution_id="exec-1",
        actual_pnl=90.0,
        predicted_vs_actual_deviation=0.1,
        lessons_learned=["trend held"],
        exit_reason="TARGET_HIT",
    )
    store.save_observation(observation)
    assert ("exec-1", 90.0) in store.pnl_series()
    store.close()


# ------------------------------------------------------------ live PG (opt-in)


@pytest.mark.skipif(
    not PG_DSN, reason="set AIOS_TEST_PG_DSN to run the live PostgreSQL round-trip"
)
class TestPostgresLive:
    def _store(self) -> PostgresMemoryStore:
        return PostgresMemoryStore(PG_DSN)

    def test_hash_chain_round_trip(self) -> None:
        store = self._store()
        for i in range(5):
            store.append_event("TEST", f"ref-{i}", {"i": i})
        ok, bad = store.verify_chain()
        assert ok is True and bad is None
        payloads = store.iter_event_payloads("TEST")
        assert [p["i"] for p in payloads] == [4, 3, 2, 1, 0][::-1]
        counts = store.counts()
        assert counts["event_log"] >= 5
        store.close()

    def test_typed_tables_round_trip(self) -> None:
        store = self._store()
        prediction = PredictionRecord(
            hypothesis_id="hyp-pg",
            symbol="SPY",
            direction="BUY",
            entry_reference_price=100.0,
            target_price=110.0,
            stop_price=95.0,
            horizon_timeframe="1d",
            confidence_score=80.0,
            expected_risk_reward_ratio=2.0,
            decision_bar_timestamp=datetime.now(UTC),
            is_simulated=True,
        )
        store.save_prediction(prediction)
        scored = prediction.score(
            exit_price=109.0,
            exit_reason="TARGET_HIT",
            realized_pnl=90.0,
            direction_correct=True,
        )
        store.save_prediction(scored)
        store.save_observation(
            ObservationReport(
                execution_id=f"exec-pg-{scored.prediction_id[:8]}",
                actual_pnl=90.0,
                predicted_vs_actual_deviation=0.1,
                lessons_learned=["trend held"],
                exit_reason="TARGET_HIT",
            )
        )
        assert any(p == 90.0 for _, p in store.pnl_series())
        store.close()

    def test_tamper_detection_pinpoints_seq(self) -> None:
        store = self._store()
        first_new = store.append_event("TAMPER_TEST", "a", {"v": 1})
        store.append_event("TAMPER_TEST", "b", {"v": 2})
        with store._lock:  # noqa: SLF001 - deliberate tamper drill
            with store._conn.cursor() as cur:
                cur.execute(
                    "UPDATE event_log SET payload_json = %s WHERE seq = %s",
                    ('{"v": 999}', first_new + 1),
                )
            store._conn.commit()
        ok, bad = store.verify_chain()
        assert ok is False
        assert bad == first_new + 1
        with store._conn.cursor() as cur:  # clean up so reruns stay consistent
            cur.execute("DELETE FROM event_log WHERE kind = 'TAMPER_TEST'")
        store._conn.commit()
        store.close()

    def test_full_replay_runs_on_postgres(self, tmp_path: Path) -> None:
        """End-to-end: identical replay semantics on the PG tier."""
        write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=60)
        runner = ReplayRunner(
            csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
            store_path=tmp_path / "unused.db",
            initial_balance=100000.0,
            slippage_pct=0.05,
            settings=Settings(model_provider="none"),
        )
        runner.store = self._store()  # promote to PG before the run
        summary = asyncio.run(runner.run())
        assert summary.chain_valid is True
        assert summary.trades_closed >= 1
        counts = runner.store.counts()
        assert counts["postmortems"] == summary.trades_closed
        assert counts["event_log"] > summary.trades_closed
        receipts = runner.store.iter_event_payloads("DECISION_RECEIPT")
        assert len(receipts) > 0

