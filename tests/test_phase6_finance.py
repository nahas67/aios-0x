"""Phase 6 Finance Back Office tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from communities.c11_finance.audit_graph import decision_provenance, hypothesis_impact
from communities.c11_finance.ca_review import CAWorkflow
from communities.c11_finance.compliance import Surveillance, compute_nav
from communities.c11_finance.ledger import DoubleEntryLedger
from communities.c11_finance.tax import BUILTIN_RULES, LotBook, TaxEngine
from core.event_bus import InMemoryEventBus
from schemas.contracts import TradeExecutionReceipt


def _receipt(symbol="BTC/USD", fill=100.0, qty=1.0, fees=1.0):
    return TradeExecutionReceipt(
        strategy_id="s1",
        symbol=symbol,
        fill_price=fill,
        filled_quantity=qty,
        slippage=0.5,
        fees=fees,
        is_simulated=True,
    )


# ---------------------------------------------------------------------- ledger


def test_double_entry_invariant_across_mixed_activity() -> None:
    async def _run():
        ledger = DoubleEntryLedger()
        await ledger.post_fill_open("BTC/USD", 100.0, 2.0, 2.0, "e1")
        await ledger.post_exit_close("BTC/USD", 20000, 21000, 1000, "e1")
        await ledger.post_fill_open("ETH/USD", 50.0, 4.0, 0.0, "e2")
        await ledger.post_exit_close("ETH/USD", 20000, 18000, -2000, "e2")
        return ledger

    ledger = asyncio.run(_run())
    assert ledger.trial_balance_total() == 0
    balances = ledger.balances()
    # Cash net = exit proceeds (21000+18000) - entry costs (20000+20000) - fees (200c)
    assert balances["CASH"] == 39000 - 40200
    assert balances["INCOME:REALIZED_PNL"] == -1000  # credit shown negative
    assert balances["EXPENSE:REALIZED_LOSS"] == 2000


def test_ledger_rejects_bad_postings() -> None:
    async def _run():
        ledger = DoubleEntryLedger()
        with pytest.raises(ValueError):
            await ledger.post("A", "B", 0)
        with pytest.raises(ValueError):
            await ledger.post("A", "A", 100)

    asyncio.run(_run())


# ------------------------------------------------------------------ tax lots


def _ts(day: int) -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=day)


def test_fifo_partial_consumption_and_holding_split() -> None:
    book = LotBook(long_term_days=365)
    r1 = _receipt(fill=100.0, qty=2.0)
    lot = book.open_from_fill(r1, opened_at=_ts(0))

    # Partial sale after 30 days (short-term), remainder after 400 days (long)
    d1 = book.consume("BTC/USD", 1.0, 110.0, _ts(30), "e-exit-1")
    d2 = book.consume("BTC/USD", 1.0, 120.0, _ts(400), "e-exit-2")

    assert lot.qty_remaining == pytest.approx(0.0)
    assert len(d1) == 1 and len(d2) == 1
    assert d1[0].long_term is False
    assert d1[0].basis_minor == 10000
    assert d1[0].proceeds_minor == 11000
    assert d2[0].long_term is True
    assert book.open_qty("BTC/USD") == 0.0

    with pytest.raises(ValueError):
        book.consume("BTC/USD", 0.5, 120.0, _ts(401), "overdraw")


def test_tax_engine_jurisdictions_and_signoff_gate() -> None:
    from schemas.contracts import Disposal

    def _d(gain_minor: int, long_term: bool) -> Disposal:
        return Disposal(
            lot_id="l",
            symbol="BTC/USD",
            disposed_qty=1.0,
            basis_minor=max(0, 10000 - gain_minor),
            proceeds_minor=10000,
            gain_minor=gain_minor,
            holding_days=400 if long_term else 30,
            long_term=long_term,
            disposed_at=_ts(400),
            ref_execution_id_exit="x",
        )

    india = TaxEngine(BUILTIN_RULES["IN_VDA_FLAT30"])
    comp = india.compute([_d(10_000, long_term=False)])
    assert comp.rule_citation.startswith("Income-tax Act 1961")
    assert comp.tax_due_minor == int(round(10_000 * 0.30))
    assert comp.requires_professional_signoff is True

    us = TaxEngine(BUILTIN_RULES["US_IRC_1222"])
    comp_us = us.compute([_d(10_000, long_term=True), _d(4_000, long_term=False)])
    expected = int(round(10_000 * 0.15 + 4_000 * 0.37))
    assert comp_us.tax_due_minor == expected


# ------------------------------------------------------------------- CA gate


def test_ca_workflow_blocks_filing_until_approved() -> None:
    wf = CAWorkflow()
    item = wf.create(subject_kind="tax_computation", subject_ref="comp-1")

    with pytest.raises(PermissionError, match="APPROVED_BY_CA"):
        wf.export_for_filing(item.item_id)

    wf.prepare(item.item_id, prepared_by="system-preparer")
    wf.submit_for_review(item.item_id)

    with pytest.raises(ValueError):
        wf.approve(item.item_id, "")  # blank reviewer refused

    wf.reject(item.item_id, reviewer="ca-1", note="missing TDS schedule")
    # Rejected items must restart the pipeline
    with pytest.raises(AssertionError):
        wf.submit_for_review(item.item_id)


def test_ca_workflow_happy_path_exports_with_identity() -> None:
    wf = CAWorkflow()
    item = wf.create("nav_report", "fund-A-2026Q3")
    wf.prepare(item.item_id, "prep-bot")
    wf.submit_for_review(item.item_id)
    wf.approve(item.item_id, "CA-LICENSE-12345")
    exported = wf.export_for_filing(item.item_id)
    assert exported["approved_by"] == "CA-LICENSE-12345"


# ---------------------------------------------------------------- compliance


def test_surveillance_restricted_symbol_blocks() -> None:
    bus = InMemoryEventBus()

    async def _run():
        await bus.start()
        surveillance = Surveillance(bus, restricted_symbols={"BAD/USD"})
        alerts = await surveillance.check_fill(_receipt(symbol="BAD/USD"))
        await bus.stop()
        return alerts

    alerts = asyncio.run(_run())
    assert any(a.rule_name == "RESTRICTED_SYMBOL" and a.blocks_execution for a in alerts)


def test_surveillance_fat_finger_after_history() -> None:
    bus = InMemoryEventBus()

    async def _run():
        await bus.start()
        s = Surveillance(bus, fat_finger_multiple=10.0)
        for _ in range(6):
            await s.check_fill(_receipt(qty=1.0))
        alerts = await s.check_fill(_receipt(qty=500.0))
        await bus.stop()
        return alerts

    alerts = asyncio.run(_run())
    assert any(a.rule_name == "FAT_FINGER_QTY" for a in alerts)


def test_nav_math() -> None:
    nav = compute_nav(cash=50000.25, positions={"BTC/USD": (0.5, 60000.0)})
    assert nav == pytest.approx(80000.25)


# ------------------------------------------------------------- audit graph E2E


def test_provenance_walk_over_full_replay(tmp_path: Path) -> None:
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "audit.db",
    )
    summary = asyncio.run(runner.run())
    assert summary.trades_closed >= 1

    receipt = runner.c7.trade_receipts[0]
    walk = decision_provenance(runner.store, receipt.execution_id)
    assert walk["chain_complete"] is True
    assert walk["execution"]["strategy_id"] == walk["strategy"]["strategy_id"]
    assert walk["hypothesis"]["hypothesis_id"] == walk["strategy"]["hypothesis_id"]

    hypothesis_id = walk["hypothesis"]["hypothesis_id"]
    impact = hypothesis_impact(runner.store, hypothesis_id)
    assert impact["executions"], "impact must find downstream executions"
    assert impact["total_realized_pnl"] is not None

    # Ledger stayed balanced through an entire honest replay
    assert runner.ledger.trial_balance_total() == 0
