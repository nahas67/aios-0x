"""Every hop carries the same correlation id (goal G210).

"Why did this trade happen" is eleven hops with nothing joining them today —
``trace_id`` is a nullable outbox column nobody sets. These tests pin the
join: the id threads from plan through OMS (durable outbox column), adapter
(governed call session), and back out through `why_trade`, which assembles
spans plus order events and names the stages still silent instead of
inventing them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import SqliteFinancialStore
from core.security_master import AssetClass, InstrumentIdentity
from core.trace import (
    STAGES,
    Span,
    TraceContext,
    TraceRecorder,
    new_trace_id,
    why_trade,
)
from schemas.contracts import OrderSide


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="US0378331005",
        listing_id="XNAS:AAPL",
        ticker="AAPL",
        mic="XNAS",
        venue="NASDAQ",
        asset_class=AssetClass.EQUITY,
        currency="USD",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("1"),
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        recorded_from=datetime(2020, 1, 1, tzinfo=UTC),
        source="test",
    )


@pytest.fixture()
def oms(tmp_path: Path) -> DurableOrderManager:
    return DurableOrderManager(SqliteFinancialStore(tmp_path / "fin.db"), broker="paper")


# ══════════════════════════════════════════════════════════════════════════
# The id threads through every hop
# ══════════════════════════════════════════════════════════════════════════


def test_prepare_stamps_the_outbox_trace_column(oms: DurableOrderManager) -> None:
    """The durable join key: the requested event carries the trace id in its
    column (not just its payload — columns are queryable, payload keys are
    not reliably so across tiers)."""
    context = TraceContext.new()
    oms.prepare_order(
        client_order_id="ord-001",
        strategy_id="momentum-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5.0,
        trace_id=context.trace_id,
    )
    pending = oms.store.outbox_pending(limit=10)
    requested = [e for e in pending if e.idempotency_key == "order:ord-001:requested"]
    assert len(requested) == 1
    assert requested[0].trace_id == context.trace_id


def test_governed_call_carries_the_trace_as_session() -> None:
    """The risk decision joins the trace through the call's session: the
    verdict is bound to the call, the call carries the trace, so the verdict
    is one join from the chain without a second lookup."""
    from communities.c5_execution.adapters import BaseExecutionAdapter
    from kernel.tool_governance import build_execution_guardian
    from schemas.contracts import PortfolioAllocationPlan, StrategySpecification

    class _Adapter(BaseExecutionAdapter):
        def __init__(self) -> None:
            super().__init__(guardian=build_execution_guardian(b"g" * 32))
            self.venue = "paper"

        async def submit(self, plan, quantity, **kwargs):
            raise NotImplementedError

        def positions_snapshot(self):
            return {}

    adapter = _Adapter()
    plan = PortfolioAllocationPlan(
        strategy=StrategySpecification(
            hypothesis_id="h1",
            strategy_id="momentum-1",
            symbol="AAPL",
            action="BUY",
            entry_price=10.0,
            stop_loss_price=9.0,
            take_profit_price=12.0,
            position_size_pct=5.0,
        ),
        approved=True,
        final_position_size_pct=5.0,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )
    call, _ = adapter.govern(plan, 5.0, trace_id="trace-abc-123")
    assert call.session_id == "trace-abc-123"


def test_trace_ids_are_unique_hex() -> None:
    """Correlation ids with structure invite parsing; nothing should parse
    one. Uniqueness is what makes the join sound."""
    first, second = new_trace_id(), new_trace_id()
    assert first != second
    assert all(c in "0123456789abcdef" for c in first)


# ══════════════════════════════════════════════════════════════════════════
# Spans: closed vocabulary, ordered assembly
# ══════════════════════════════════════════════════════════════════════════


def test_span_rejects_empty_trace_and_unknown_stage() -> None:
    """A span without a trace id joins nothing; a stage outside the eleven
    is a hop the chain cannot place. Both refused at construction, not
    discovered missing at query time."""
    context = TraceContext.new()
    with pytest.raises(ValueError, match="without a trace id"):
        Span(trace_id="  ", stage="order", recorded_at="t")
    with pytest.raises(ValueError, match="outside the canonical chain"):
        Span(trace_id=context.trace_id, stage="vibes", recorded_at="t")


def test_recorder_orders_spans_and_reports_gaps() -> None:
    """Gaps are reported, not filled: an invented span would be the chain
    vouching for a hop that never recorded itself."""
    recorder = TraceRecorder()
    context = TraceContext.new()
    recorder.record(context.span("market_event", refs={"symbol": "AAPL"}))
    recorder.record(context.span("order", refs={"order_id": "ord-001"}))
    assert [s.stage for s in recorder.chain(context.trace_id)] == ["market_event", "order"]
    missing = recorder.missing_stages(context.trace_id)
    assert "feature" in missing and "fill" in missing
    assert "market_event" not in missing and "order" not in missing


def test_eleven_canonical_stages_exist_in_order() -> None:
    assert STAGES[0] == "market_event"
    assert STAGES[-1] == "ledger_transaction"
    assert len(STAGES) == 11


# ══════════════════════════════════════════════════════════════════════════
# why_trade: the answer, with its gaps named
# ══════════════════════════════════════════════════════════════════════════


def test_why_trade_assembles_spans_and_order_events(
    oms: DurableOrderManager,
) -> None:
    """Order events (by trace column) plus recorded spans (by chain) in one
    answer: the 'why' with the receipts attached."""
    context = TraceContext.new()
    recorder = TraceRecorder()
    recorder.record(context.span("strategy", refs={"strategy_id": "momentum-1"}))
    recorder.record(
        context.span("authorization", refs={"envelope_id": "env-1"}, note="APPROVE")
    )
    oms.prepare_order(
        client_order_id="ord-001",
        strategy_id="momentum-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5.0,
        trace_id=context.trace_id,
    )
    pending = oms.store.outbox_pending(limit=10)
    answer = why_trade(context.trace_id, recorder=recorder, outbox_events=pending)
    assert answer["trace_id"] == context.trace_id
    assert [s["stage"] for s in answer["stages"]] == ["strategy", "authorization"]
    assert answer["stages"][1]["refs"] == {"envelope_id": "env-1"}
    assert len(answer["outbox_events"]) == 1
    assert "order" in answer["missing_stages"]
    assert "strategy" not in answer["missing_stages"]


def test_why_trade_on_unknown_id_returns_empty_chain() -> None:
    """'Nothing recorded under this id' is itself the finding: raising
    would turn every typo into an incident."""
    answer = why_trade("no-such-trace", recorder=TraceRecorder(), outbox_events=[])
    assert answer["stages"] == []
    assert answer["outbox_events"] == []
    assert answer["missing_stages"] == list(STAGES)


def test_spans_carry_refs_not_payloads() -> None:
    """A span carrying payloads would duplicate every store it joins; keys
    make it an index, which is what a chain is for."""
    context = TraceContext.new()
    span = context.span("fill", refs={"order_id": "ord-001", "fill_id": "f-9"})
    assert span.refs == {"order_id": "ord-001", "fill_id": "f-9"}
    assert "price" not in span.refs
