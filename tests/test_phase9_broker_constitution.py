"""Phase 9 tests: constitution pinning + CCXT execution contract suite."""

import asyncio
from pathlib import Path

import pytest

from communities.c5_execution.adapters import (
    CcxtExecutionAdapter,
    ExecutionUnavailableError,
)
from core.constitution import (
    ConstitutionViolationError,
    enforce_at_boot,
    verify,
)
from schemas.contracts import PortfolioAllocationPlan, StrategySpecification

# ------------------------------------------------------------- constitution


def test_constitution_verifies_when_pinned(tmp_path: Path) -> None:
    assert verify() is True
    assert enforce_at_boot().startswith("310bc83f")


def test_constitution_tamper_detected(tmp_path: Path) -> None:
    tampered = tmp_path / "CONSTITUTION.md"
    tampered.write_text("# Tampered\n", encoding="utf-8")
    assert verify(tampered) is False
    with pytest.raises(ConstitutionViolationError, match="MISMATCH"):
        enforce_at_boot(tampered)


# ------------------------------------------------------------ ccxt execution


class FakeCcxtClient:
    """Mirrors the ccxt client API surface the adapter relies upon."""

    def __init__(self) -> None:
        self.sandbox_enabled: bool | None = None
        self.orders: list[dict] = []
        self.cancel_calls: list[str | None] = []
        self._next_id = 100

    def set_sandbox_mode(self, flag: bool) -> None:
        self.sandbox_enabled = flag

    def create_order(self, symbol: str, type_: str, side: str, amount: float, price=None):
        order = {
            "id": str(self._next_id),
            "symbol": symbol,
            "type": type_,
            "side": side,
            "amount": amount,
            "filled": amount,
            "average": 101.25 if side == "buy" else 99.75,
            "fee": {"cost": 0.35},
            "status": "closed",
        }
        self._next_id += 1
        self.orders.append(order)
        return order

    def cancel_all_orders(self, symbol: str | None = None) -> list:
        self.cancel_calls.append(symbol)
        return []

    def fetch_positions(self):
        return [
            {"symbol": "BTC/USDT", "contracts": 0.25},
            {"symbol": "ETH/USDT", "contracts": -2.0},
        ]


@pytest.fixture()
def fake_adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[CcxtExecutionAdapter, FakeCcxtClient]:
    from kernel.tool_governance import ToolGuardian

    client = FakeCcxtClient()
    monkeypatch.setattr(
        "communities.c5_execution.adapters._build_exchange",
        lambda exchange_id, options: client,
    )
    adapter = CcxtExecutionAdapter(
        "binance",
        api_key_env="AIOS_T_KEY",
        secret_env="AIOS_T_SECRET",
        env={
            "AIOS_ALLOW_LIVE_EXECUTION": "1",
            "AIOS_EXCHANGE_TESTNET": "1",
            "AIOS_T_KEY": "k",
            "AIOS_T_SECRET": "s",
        },
        symbol_map={"BTC/USD": "BTC/USDT"},
        # Unopinionated: the constitutional cap is the control under test here,
        # and clamping behaviour is covered in test_execution_governance.py.
        guardian=ToolGuardian(b"phase9-test-key"),
    )
    return adapter, client


def _plan(action: str = "BUY", entry: float = 100.0, size: float = 10.0) -> PortfolioAllocationPlan:
    spec = StrategySpecification(
        hypothesis_id="h",
        symbol="BTC/USD",
        action=action,  # type: ignore[arg-type]
        entry_price=entry,
        stop_loss_price=entry * (0.97 if action == "BUY" else 1.03),
        take_profit_price=entry * (1.06 if action == "BUY" else 0.94),
        position_size_pct=size,
    )
    return PortfolioAllocationPlan(
        strategy=spec,
        approved=True,
        final_position_size_pct=size,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


def test_testnet_sandbox_engaged_and_market_order_routed(fake_adapter) -> None:
    adapter, client = fake_adapter
    assert adapter.testnet is True
    assert client.sandbox_enabled is True

    receipt = asyncio.run(adapter.submit(_plan(), quantity=0.5))

    assert receipt is not None
    assert len(client.orders) == 1
    sent = client.orders[0]
    assert sent["symbol"] == "BTC/USDT"
    assert sent["type"] == "market" and sent["side"] == "buy"

    # Receipt mapped from venue response; NOT simulated (real venue semantics)
    assert receipt.is_simulated is False
    assert receipt.venue.endswith("testnet")
    assert receipt.fill_price == pytest.approx(101.25)
    assert receipt.filled_quantity == pytest.approx(0.5)
    assert receipt.slippage == pytest.approx(1.25)
    assert receipt.fees == pytest.approx(0.35)


def test_sell_side_routing_and_cap_enforcement(fake_adapter) -> None:
    adapter, client = fake_adapter

    with pytest.raises(ExecutionUnavailableError, match="micro-live cap"):
        asyncio.run(adapter.submit(_plan(entry=50000.0), quantity=1.0))

    sell_receipt = asyncio.run(adapter.submit(_plan(action="SELL"), quantity=0.4))
    assert sell_receipt is not None
    assert client.orders[-1]["side"] == "sell"
    assert sell_receipt.fill_price == pytest.approx(99.75)


def test_positions_snapshot_maps_symbols_back(fake_adapter) -> None:
    adapter, _client = fake_adapter
    snapshot = adapter.positions_snapshot()
    assert snapshot["BTC/USD"] == pytest.approx(0.25)
    assert snapshot["ETH/USDT"] == pytest.approx(-2.0)


def test_ccxt_positions_snapshot_branches_on_side_not_just_contracts() -> None:
    """A short must not be reported as a long (defect #71).

    The base class documents "Shorts are negative" and PaperExecutionAdapter
    implements it, but real venues do not hand over a signed ``contracts``:
    ccxt's ``gate`` applies ``Precise.string_abs(size)``, and Deribit's OpenAPI
    defines ``size`` as a quote-currency magnitude carrying direction in a
    separate field. So the adapter has to consult ``side`` itself.

    The client below returns exactly the shape ccxt produces for a Gate short.
    """
    from kernel.tool_governance import ToolGuardian

    class UnsignedShortClient:
        """Mirrors ccxt: unsigned ``contracts``, direction in ``side``."""

        def set_sandbox_mode(self, flag: bool) -> None:
            self.sandbox = flag

        def fetch_positions(self) -> list[dict[str, object]]:
            return [
                {"symbol": "BTC/USDT:USDT", "contracts": 2.0, "side": "long"},
                {"symbol": "ETH/USDT:USDT", "contracts": 3.0, "side": "short"},
            ]

    client = UnsignedShortClient()
    adapter = CcxtExecutionAdapter(
        "gate",
        api_key_env="AIOS_T_KEY",
        secret_env="AIOS_T_SECRET",
        env={
            "AIOS_ALLOW_LIVE_EXECUTION": "1",
            "AIOS_EXCHANGE_TESTNET": "1",
            "AIOS_T_KEY": "k",
            "AIOS_T_SECRET": "s",
        },
        client_builder=lambda exchange_id, options: client,
        guardian=ToolGuardian(b"phase9-sign-test-key"),
    )

    snapshot = adapter.positions_snapshot()

    assert snapshot["BTC/USDT:USDT"] == pytest.approx(2.0)
    assert snapshot["ETH/USDT:USDT"] == pytest.approx(-3.0), (
        "a short reported positive is a phantom long: reconciliation diverges "
        "permanently and G240's zero-violation gate could never pass"
    )


def test_real_money_blocked_without_constitution_gate(fake_adapter) -> None:
    from kernel.tool_governance import ToolGuardian

    # Same env but requesting LIVE venue: must refuse without approval flag
    with pytest.raises(ExecutionUnavailableError, match="CONSTITUTION"):
        CcxtExecutionAdapter(
            "binance",
            api_key_env="K",
            secret_env="S",
            env={
                "AIOS_ALLOW_LIVE_EXECUTION": "1",
                "AIOS_EXCHANGE_TESTNET": "0",
                "K": "k",
                "S": "s",
            },
            guardian=ToolGuardian(b"phase9-test-key"),
        )


def test_cancel_all_delegates_with_symbol_mapping(fake_adapter) -> None:
    adapter, client = fake_adapter
    asyncio.run(adapter.cancel_all_orders("BTC/USD"))
    assert client.cancel_calls == ["BTC/USDT"]
