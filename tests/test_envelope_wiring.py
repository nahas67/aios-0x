"""No venue submit without a sealed envelope (goal G140, wiring).

The firewall engine (`core/capital_firewall.py`) answers whether an order may
exist; these tests prove the execution path asks. Two boundaries, both
conditional on configuration so every pre-existing caller keeps working:

*OMS prepare (booking half).* A firewall-bound `DurableOrderManager` demands
the envelope plus the identity fields the verdict needs, evaluates *before*
persisting, persists nothing on REJECT, and persists the approved quantity on
REDUCE. The verdict and envelope id ride in the outbox payload, so the
authorization is auditable without a schema change.

*Adapter submit (venue half).* A secret-bound adapter verifies the envelope
(signature plus quantity/notional scope) before `govern()` runs. An order
that may not exist is refused before a verdict is even computed for it —
the two boundaries answer different questions, and a refusal at the first
must not depend on the second.

All signing keys below are single-character repetitions: test-only key
material with no production value, following the existing test convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from communities.c5_execution.adapters import (
    BaseExecutionAdapter,
    ExecutionUnavailableError,
)
from communities.c5_execution.oms import DurableOrderManager, OrderBlocked
from core.authorization import AuthorizationEnvelope
from core.capital_firewall import CapitalFirewall, issue
from core.contamination import SurvivorshipReport
from core.financial_kernel import SqliteFinancialStore
from core.security_master import AssetClass, InstrumentIdentity, SecurityMaster
from core.security_master_store import build_sqlite_security_master_store
from kernel.tool_governance import build_execution_guardian
from schemas.contracts import (
    OrderSide,
    OrderStatus,
    PortfolioAllocationPlan,
    StrategySpecification,
    TradeExecutionReceipt,
)

SEAL_KEY = "k" * 32
WRONG_KEY = "x" * 32
GUARD_KEY = b"g" * 32
T0 = datetime(2024, 6, 3, 14, 30, tzinfo=UTC)


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
def master(tmp_path: Path) -> SecurityMaster:
    store = build_sqlite_security_master_store(tmp_path / "sec.db")
    security = SecurityMaster(store)
    security.upsert(_identity())
    return security


class _Oracle:
    """Certification oracle under test control."""

    def __init__(self, certified: bool = True) -> None:
        self.certified = certified

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        return object() if self.certified else None

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        return self.certified


def _clean_universe() -> SurvivorshipReport:
    return SurvivorshipReport(
        tested_universe_size=1, disappeared_in_window=0, excluded_from_universe=0
    )


@pytest.fixture()
def firewall(master: SecurityMaster) -> CapitalFirewall:
    return CapitalFirewall(master=master, oracle=_Oracle(), venue_allowlist={"paper"})


@pytest.fixture()
def oms(tmp_path: Path, firewall: CapitalFirewall) -> DurableOrderManager:
    store = SqliteFinancialStore(tmp_path / "fin.db")
    return DurableOrderManager(
        store, broker="paper", firewall=firewall, firewall_secret=SEAL_KEY
    )


def _envelope(
    *,
    max_quantity: float = 10.0,
    max_notional: float = 100.0,
    secret: str = SEAL_KEY,
    client_order_id: str = "ord-001",
) -> AuthorizationEnvelope:
    return issue(
        strategy_id="momentum-1",
        strategy_version="v1",
        client_order_id=client_order_id,
        instrument_id="US0378331005",
        max_quantity=max_quantity,
        max_notional_usd=max_notional,
        issuer="test",
        secret=secret,
        ttl_seconds=3600.0,
    )


def _firewall_kwargs(envelope: AuthorizationEnvelope) -> dict[str, Any]:
    return {
        "envelope": envelope,
        "instrument_id": "US0378331005",
        "mic": "XNAS",
        "price": 10.0,
        "strategy_version": "v1",
        "survivorship": _clean_universe(),
    }


# ══════════════════════════════════════════════════════════════════════════
# OMS prepare: the booking half
# ══════════════════════════════════════════════════════════════════════════


def test_prepare_without_an_envelope_persists_nothing(
    oms: DurableOrderManager,
) -> None:
    """A firewall-bound OMS with no envelope is a closed door, not an open
    one. The refusal names the missing inputs, and the store holds no order
    afterwards — a refused order never enters the book, not even as
    PENDING_NEW."""
    with pytest.raises(OrderBlocked, match="missing firewall inputs"):
        oms.prepare_order(
            client_order_id="ord-001",
            strategy_id="momentum-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5.0,
        )
    assert oms.store.order("ord-001") is None


def test_prepare_with_a_forged_envelope_persists_nothing(
    oms: DurableOrderManager,
) -> None:
    """A signature made with another key is not an authorization. The
    firewall names the failed check, and again nothing is persisted."""
    with pytest.raises(OrderBlocked, match="REJECT"):
        oms.prepare_order(
            client_order_id="ord-001",
            strategy_id="momentum-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5.0,
            **_firewall_kwargs(_envelope(secret=WRONG_KEY)),
        )
    assert oms.store.order("ord-001") is None


def test_a_passing_order_persists_with_its_authorization(
    oms: DurableOrderManager,
) -> None:
    """The happy path, end to end through the real firewall: $50 notional
    against the $100 cap, live identity, certified strategy, clean universe.
    The outbox payload carries the envelope id and verdict, which is the
    audit join that makes the authorization checkable after the fact."""
    envelope = _envelope()
    stored = oms.prepare_order(
        client_order_id="ord-001",
        strategy_id="momentum-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5.0,
        **_firewall_kwargs(envelope),
    )
    assert stored.status is OrderStatus.PENDING_NEW
    assert stored.quantity == pytest.approx(5.0)
    pending = oms.store.outbox_pending(limit=10)
    requested = [e for e in pending if e.idempotency_key == "order:ord-001:requested"]
    assert len(requested) == 1
    authorization = requested[0].payload.get("authorization")
    assert authorization is not None
    assert authorization["envelope_id"] == envelope.envelope_id
    assert authorization["verdict"] == "APPROVE"


def test_a_rejected_order_names_its_checks_and_persists_nothing(
    tmp_path: Path, master: SecurityMaster
) -> None:
    """Revoked certification mid-flight: the strategy the envelope was issued
    for is no longer certified, so the order dies naming the check."""
    firewall = CapitalFirewall(
        master=master, oracle=_Oracle(certified=False), venue_allowlist={"paper"}
    )
    store = SqliteFinancialStore(tmp_path / "fin.db")
    bound = DurableOrderManager(
        store, broker="paper", firewall=firewall, firewall_secret=SEAL_KEY
    )
    with pytest.raises(OrderBlocked, match="strategy_certified|REJECT"):
        bound.prepare_order(
            client_order_id="ord-001",
            strategy_id="momentum-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5.0,
            **_firewall_kwargs(_envelope()),
        )
    assert store.order("ord-001") is None


def test_a_reduce_verdict_persists_the_approved_quantity(
    oms: DurableOrderManager,
) -> None:
    """$500 requested against the $100 constitutional cap: the firewall
    reduces rather than rejects, and the book holds the approved size — never
    the requested one. Execution may only reduce; the OMS is where that
    becomes durable fact."""
    stored = oms.prepare_order(
        client_order_id="ord-001",
        strategy_id="momentum-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=50.0,
        **_firewall_kwargs(_envelope(max_quantity=50.0)),
    )
    assert stored.quantity == pytest.approx(10.0)
    pending = oms.store.outbox_pending(limit=10)
    requested = [e for e in pending if e.idempotency_key == "order:ord-001:requested"]
    assert requested[0].payload["authorization"]["verdict"] == "REDUCE"


def test_an_unconfigured_oms_behaves_exactly_as_before(tmp_path: Path) -> None:
    """Backward compatibility is a property, not an assumption: no firewall
    means no envelope required and no behaviour change. Every pre-existing
    caller depends on this."""
    store = SqliteFinancialStore(tmp_path / "fin.db")
    plain = DurableOrderManager(store, broker="paper")
    stored = plain.prepare_order(
        client_order_id="ord-001",
        strategy_id="momentum-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5.0,
    )
    assert stored.status is OrderStatus.PENDING_NEW
    assert stored.quantity == pytest.approx(5.0)


# ══════════════════════════════════════════════════════════════════════════
# Adapter submit: the venue half
# ══════════════════════════════════════════════════════════════════════════


class _SecretBoundAdapter(BaseExecutionAdapter):
    """Minimal venue double behind the envelope boundary."""

    def __init__(self, secret: str | None) -> None:
        super().__init__(
            guardian=build_execution_guardian(GUARD_KEY), envelope_secret=secret
        )
        self.venue = "paper"
        self.submissions: list[tuple[str, float]] = []

    async def submit(
        self, plan: PortfolioAllocationPlan, quantity: float, **kwargs: Any
    ) -> TradeExecutionReceipt | None:
        self._require_envelope(plan, quantity, kwargs.get("envelope"))
        governed, _ = self.govern(plan, quantity)
        self.submissions.append((plan.strategy.symbol, quantity))
        return TradeExecutionReceipt(
            execution_id="exec-1",
            strategy_id=plan.strategy.strategy_id,
            symbol=plan.strategy.symbol,
            fill_price=plan.strategy.entry_price,
            filled_quantity=quantity,
            slippage=0.0,
            fees=0.0,
            venue=self.venue,
            is_simulated=True,
        )

    def positions_snapshot(self) -> dict[str, float]:
        return {}


def _plan(symbol: str = "AAPL", entry_price: float = 10.0) -> PortfolioAllocationPlan:
    return PortfolioAllocationPlan(
        strategy=StrategySpecification(
            hypothesis_id="h1",
            strategy_id="momentum-1",
            symbol=symbol,
            action="BUY",
            entry_price=entry_price,
            stop_loss_price=9.0,
            take_profit_price=12.0,
            position_size_pct=5.0,
        ),
        approved=True,
        final_position_size_pct=5.0,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


def test_submit_without_an_envelope_never_reaches_the_venue() -> None:
    """The gate as literally stated: a secret-bound adapter with no envelope
    refuses before govern() runs, so the venue double records nothing. The
    refusal happens before a verdict is computed, because an order that may
    not exist needs no shaping."""
    import asyncio

    adapter = _SecretBoundAdapter(SEAL_KEY)
    with pytest.raises(ExecutionUnavailableError, match="requires an authorization envelope"):
        asyncio.run(adapter.submit(_plan(), 5.0))
    assert adapter.submissions == []


def test_submit_with_a_forged_envelope_never_reaches_the_venue() -> None:
    import asyncio

    adapter = _SecretBoundAdapter(SEAL_KEY)
    with pytest.raises(ExecutionUnavailableError, match="does not verify"):
        asyncio.run(adapter.submit(_plan(), 5.0, envelope=_envelope(secret=WRONG_KEY)))
    assert adapter.submissions == []


def test_submit_beyond_envelope_scope_is_refused() -> None:
    """Scope is quantity AND notional: 5 units at $10 against a 4-unit
    envelope fails on quantity; 5 units at $10 against a $40 envelope fails
    on notional. Either dimension over is over."""
    import asyncio

    adapter = _SecretBoundAdapter(SEAL_KEY)
    with pytest.raises(ExecutionUnavailableError, match="exceeds envelope maximum"):
        asyncio.run(adapter.submit(_plan(), 5.0, envelope=_envelope(max_quantity=4.0)))
    with pytest.raises(ExecutionUnavailableError, match="exceeds envelope maximum"):
        asyncio.run(
            adapter.submit(_plan(), 5.0, envelope=_envelope(max_quantity=10.0, max_notional=40.0))
        )
    assert adapter.submissions == []


def test_submit_with_a_covering_envelope_proceeds() -> None:
    import asyncio

    adapter = _SecretBoundAdapter(SEAL_KEY)
    receipt = asyncio.run(adapter.submit(_plan(), 5.0, envelope=_envelope()))
    assert receipt is not None
    assert adapter.submissions == [("AAPL", 5.0)]


def test_an_unbound_adapter_needs_no_envelope() -> None:
    """No secret configured, no boundary armed: legacy behaviour unchanged."""
    import asyncio

    adapter = _SecretBoundAdapter(None)
    receipt = asyncio.run(adapter.submit(_plan(), 5.0))
    assert receipt is not None
    assert adapter.submissions == [("AAPL", 5.0)]
