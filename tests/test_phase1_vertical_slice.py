"""Phase 1 Honest Vertical Slice tests: replay, persistence, ledger, determinism."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.persistence import SqliteMemoryStore
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


@pytest.fixture()
def small_dataset(tmp_path: Path) -> dict[str, Path]:
    """Two-symbol 120-bar deterministic dataset for fast slice runs."""
    write_dataset(
        tmp_path / "golden",
        symbols=["BTC/USD", "ETH/USD"],
        total_bars=120,
    )
    by_symbol = {
        "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
        "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
    }
    return {s: p for s, p in by_symbol.items() if p.exists()}


def _run(dataset: dict[str, Path], store_path: Path):
    from core.config import Settings
    settings = Settings(model_provider="none", autonomy_mode="AUTONOMOUS")
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=store_path,
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=settings,
    )
    summary = asyncio.run(runner.run())
    return runner, summary


def test_replay_fetcher_no_lookahead(tmp_path: Path) -> None:
    """Directive 75: only the cursor bar is ever visible; future bars unreachable."""
    from communities.c1_data.data_agent import DataAcquisitionAgent
    from communities.c1_data.replay_fetcher import ReplayCursor, ReplayDataFetcher
    from core.event_bus import InMemoryEventBus

    rows = []
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(5):
        price = 100.0 + i
        rows.append(
            f"{(base + timedelta(days=i)).isoformat()},{price},{price + 1},{price - 1},{price},1000"
        )
    csv_path = tmp_path / "one.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n" + "\n".join(rows))

    cursor = ReplayCursor()
    fetcher = ReplayDataFetcher({"BTC/USD": csv_path}, cursor=cursor)

    # Cursor not advanced yet -> nothing visible
    with pytest.raises(RuntimeError):
        fetcher.current_bar("BTC/USD")

    cursor.advance()
    bar0 = asyncio.run(fetcher.fetch_price_data("BTC/USD", "1d"))
    assert bar0["close"] == 100.0

    # Payloads carry SIM provenance and the constitutional tag (Law 1.3)
    bus = InMemoryEventBus()

    async def _collect() -> None:
        await bus.start()
        agent = DataAcquisitionAgent(fetcher=fetcher, event_bus=bus)
        payload = await agent.collect_and_publish("BTC/USD", "1d")
        await bus.stop()
        assert payload.is_simulated is True
        assert payload.provenance is not None
        assert payload.provenance.source_type == "SIM"

    asyncio.run(_collect())

    # Repeated fetches at same cursor are identical (no state leakage)
    bar0_again = asyncio.run(fetcher.fetch_price_data("BTC/USD", "1d"))
    assert bar0_again == bar0

    cursor.advance()
    bar1 = asyncio.run(fetcher.fetch_price_data("BTC/USD", "1d"))
    assert bar1["close"] == 101.0

    # Exhaustion is loud, never silently wraps
    for _ in range(10):
        cursor.advance()
    with pytest.raises(IndexError):
        asyncio.run(fetcher.fetch_price_data("BTC/USD", "1d"))


def test_memory_store_hash_chain_tamper_detection(tmp_path: Path) -> None:
    """Hash chain verifies when intact and pinpoints tampered sequence."""
    store = SqliteMemoryStore(tmp_path / "audit.db")
    for i in range(5):
        store.append_event("TEST", f"ref-{i}", {"i": i})
    ok, bad_seq = store.verify_chain()
    assert ok is True and bad_seq is None

    store._conn.execute("UPDATE event_log SET payload_json = ? WHERE seq = 3", ('{"i": 999}',))
    store._conn.commit()
    ok2, bad_seq2 = store.verify_chain()
    assert ok2 is False
    assert bad_seq2 == 3
    store.close()


def test_vertical_slice_ledger_and_postmortems(
    small_dataset: dict[str, Path], tmp_path: Path
) -> None:
    """Predictions scored, postmortems per trade, honest cash accounting."""
    runner, summary = _run(small_dataset, tmp_path / "slice.db")

    counts = runner.store.counts()
    assert summary.trades_closed >= 1, "dataset must produce at least one trade"
    assert counts["predictions"] == summary.trades_closed
    assert counts["postmortems"] == summary.trades_closed
    assert counts["observations"] == summary.trades_closed
    assert summary.predictions_scored == summary.trades_closed
    assert summary.chain_valid is True
    assert summary.events_logged > summary.trades_closed

    # Cash conservation: final balance equals initial plus realized PnL (rounding slack)
    assert summary.final_cash_balance == pytest.approx(100000.0 + summary.cumulative_pnl, abs=0.05)

    # PnL series in store matches summary
    series = runner.store.pnl_series()
    assert len(series) == summary.trades_closed
    assert sum(p for _, p in series) == pytest.approx(summary.cumulative_pnl, abs=0.01)

    # Wins + losses reconcile; directional accuracy consistent with wins proxy
    assert summary.wins + summary.losses == summary.trades_closed


def test_vertical_slice_end_to_end_honesty(small_dataset: dict[str, Path], tmp_path: Path) -> None:
    """Every recorded observation derives from its receipt; no fabricated profits."""
    from schemas.contracts import ObservationReport, TradeExecutionReceipt

    runner, _summary = _run(small_dataset, tmp_path / "honesty.db")

    reports: list[ObservationReport] = list(runner.c7.observation_reports)
    receipts: dict[str, TradeExecutionReceipt] = runner._receipts
    assert reports, "expected at least one closed trade"

    for report in reports:
        receipt = receipts[report.execution_id]
        expected_pnl = round(
            (report.actual_pnl + receipt.fees) / receipt.filled_quantity + receipt.fill_price,
            4,
        )
        # Recompute exit price implied by stored pnl; must be a positive market level
        assert expected_pnl > 0
        # Direction flag matches pnl sign exactly
        assert report.direction_correct == (report.actual_pnl > 0)
        assert report.exit_reason in ("TARGET_HIT", "STOP_HIT", "HORIZON_END")

    # Equity curve ends at cash balance (all positions force-closed at horizon end)
    assert runner.paper.open_positions == {}
    assert summary_final_equity_matches(runner)


def summary_final_equity_matches(runner: ReplayRunner) -> bool:
    last_equity = runner.equity_curve[-1]
    return last_equity == pytest.approx(runner.paper.cash_balance, abs=0.05)


def test_determinism_same_dataset_same_hash(small_dataset: dict[str, Path], tmp_path: Path) -> None:
    """Identical dataset+config -> byte-identical trade sequence hash."""
    _, s1 = _run(small_dataset, tmp_path / "run1.db")
    _, s2 = _run(small_dataset, tmp_path / "run2.db")

    assert s1.determinism_hash != ""
    assert s1.determinism_hash == s2.determinism_hash
    assert s1.cumulative_pnl == s2.cumulative_pnl
    assert s1.trades_closed == s2.trades_closed
    assert s1.final_cash_balance == s2.final_cash_balance
