"""Investment Book of Record (IBOR): the canonical answer to "what do we own?".

Master-spec §27: every question about holdings, cash, reservations, live orders,
exposure and P&L has exactly ONE authoritative source — this book — and no agent
may keep a competing copy of portfolio truth.

Properties enforced here:

- **Exactly-once ingest**: fills are applied through the deterministic store,
  whose fill identity (``fill_id`` / ``broker_execution_id``) makes a
  re-delivered venue callback a no-op. A duplicate can never double a position.
- **Reconstructible**: :meth:`rebuild` recomputes the book from the immutable
  fill ledger and reports any divergence from live state, so restart recovery
  and disaster drills have a machine-checkable answer.
- **Reservations are explicit** (§27 "what cash is reserved?"): buying power is
  settled cash minus live reservations, never a guessed number.
- **Honest marks**: when no mark exists for a symbol, market value is reported as
  None and NAV is flagged ``marks_complete=False`` rather than fabricating a
  price (§75).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from core.financial_kernel import (
    BaseFinancialStore,
    CashReservation,
    DurableOrder,
    Fill,
    OutboxEvent,
    PositionRecord,
)
from schemas.contracts import generate_uuid

logger = logging.getLogger(__name__)


class BookPosition(BaseModel):
    """One position with honest valuation state."""

    symbol: str
    quantity: float
    avg_cost: float
    mark_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float = 0.0
    currency: str = "USD"


class BookCash(BaseModel):
    """Cash that is settled, reserved and therefore actually available."""

    account_id: str
    currency: str
    settled_minor: int
    reserved_minor: int

    # A computed field, not a plain property: buying power is the single most
    # important number on this object, and ``model_dump()`` (what the API and the
    # operator surface receive) silently omits plain properties. Leaving it as a
    # property meant the Book of Record endpoint never reported available cash.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def available_minor(self) -> int:
        return self.settled_minor - self.reserved_minor


class BookSnapshot(BaseModel):
    """Point-in-time canonical portfolio state (§27)."""

    snapshot_id: str = Field(default_factory=generate_uuid)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    account_id: str
    cash: list[BookCash] = Field(default_factory=list)
    positions: list[BookPosition] = Field(default_factory=list)
    open_orders: list[DurableOrder] = Field(default_factory=list)
    nav: float | None = None
    gross_exposure: float | None = None
    net_exposure: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float | None = None
    fills_applied: int = 0
    marks_complete: bool = False

    def position_for(self, symbol: str) -> BookPosition | None:
        return next((p for p in self.positions if p.symbol == symbol), None)


class RebuildReport(BaseModel):
    """Proof that live book state equals state rebuilt from the fill ledger."""

    ok: bool
    checked_positions: int
    divergences: list[str] = Field(default_factory=list)
    detail: str = ""


class InvestmentBookOfRecord:
    """The single authoritative investment book (§27)."""

    def __init__(
        self,
        store: BaseFinancialStore,
        mark_provider: Callable[[str], float | None] | None = None,
        account_id: str = "default",
    ) -> None:
        self.store = store
        self._mark_provider = mark_provider
        self.account_id = account_id

    # ----------------------------------------------------------------- ingest

    def ingest_fill(
        self, fill: Fill, events: tuple[OutboxEvent, ...] = ()
    ) -> bool:
        """Apply a venue fill exactly once; False when it was already applied."""
        applied = self.store.apply_fill(fill, events)
        if not applied:
            logger.info("IBOR: fill %s already applied; no state change", fill.fill_id)
        return applied

    def reserve_cash(
        self,
        amount_minor: int,
        currency: str = "USD",
        reason: str = "",
        order_id: str | None = None,
    ) -> CashReservation:
        return self.store.reserve_cash(
            CashReservation(
                account_id=self.account_id,
                currency=currency,
                amount_minor=amount_minor,
                reason=reason,
                order_id=order_id,
            )
        )

    def release_cash(self, reservation_id: str) -> CashReservation:
        return self.store.release_cash(reservation_id)

    # ------------------------------------------------------------------ marks

    def mark_price(self, symbol: str) -> float | None:
        if self._mark_provider is None:
            return None
        try:
            return self._mark_provider(symbol)
        except Exception:  # pragma: no cover - defensive; a bad mark is not a crash
            logger.warning("IBOR: mark provider failed for %s", symbol, exc_info=True)
            return None

    # ---------------------------------------------------------------- snapshot

    def snapshot(self, currencies: tuple[str, ...] = ("USD",)) -> BookSnapshot:
        """Build the canonical book, honestly reporting unknown valuations."""
        positions_raw = self.store.positions(self.account_id)
        cash = [
            BookCash(
                account_id=self.account_id,
                currency=currency,
                settled_minor=self.store.cash_balance_minor(self.account_id, currency),
                reserved_minor=self.store.reserved_cash_minor(self.account_id, currency),
            )
            for currency in currencies
        ]
        positions: list[BookPosition] = []
        marks_complete = True
        gross = 0.0
        net = 0.0
        unrealized = 0.0
        for raw in positions_raw:
            mark = self.mark_price(raw.symbol)
            if mark is None:
                marks_complete = False
                positions.append(self._unmarked_position(raw))
                continue
            market_value = round(raw.quantity * mark, 6)
            asset_unrealized = round((mark - raw.avg_cost) * raw.quantity, 6)
            gross += abs(market_value)
            net += market_value
            unrealized += asset_unrealized
            positions.append(
                BookPosition(
                    symbol=raw.symbol,
                    quantity=raw.quantity,
                    avg_cost=raw.avg_cost,
                    mark_price=mark,
                    market_value=market_value,
                    unrealized_pnl=asset_unrealized,
                    realized_pnl=raw.realized_pnl,
                    currency=raw.currency,
                )
            )
        cash_value = sum(c.settled_minor for c in cash) / 100.0
        # NAV is marked cash + marked position value; with any mark missing it
        # is reported as unknown rather than invented (§75).
        nav = round(cash_value + net, 6) if marks_complete else None
        return BookSnapshot(
            account_id=self.account_id,
            cash=cash,
            positions=positions,
            open_orders=self.store.open_orders(self.account_id),
            nav=nav,
            gross_exposure=round(gross, 6) if marks_complete else None,
            net_exposure=round(net, 6) if marks_complete else None,
            realized_pnl=round(sum(p.realized_pnl for p in positions), 6),
            unrealized_pnl=round(unrealized, 6) if marks_complete else None,
            fills_applied=len(
                [f for f in self.store.fills() if f.account_id == self.account_id]
            ),
            marks_complete=marks_complete,
        )

    @staticmethod
    def _unmarked_position(raw: PositionRecord) -> BookPosition:
        return BookPosition(
            symbol=raw.symbol,
            quantity=raw.quantity,
            avg_cost=raw.avg_cost,
            mark_price=None,
            market_value=None,
            unrealized_pnl=None,
            realized_pnl=raw.realized_pnl,
            currency=raw.currency,
        )

    # ----------------------------------------------------------- reconstruction

    def rebuild(self) -> RebuildReport:
        """Recompute the book from the fill ledger and compare to live state."""
        stored = {p.symbol: p for p in self.store.positions(self.account_id)}
        rebuilt = {p.symbol: p for p in self.store.rebuild_positions(self.account_id)}
        divergences: list[str] = []
        for symbol in sorted(set(stored) | set(rebuilt)):
            live = stored.get(symbol)
            replay = rebuilt.get(symbol)
            if live is None or replay is None:
                divergences.append(f"{symbol}: present in only one source")
                continue
            if abs(live.quantity - replay.quantity) > 1e-9:
                divergences.append(
                    f"{symbol}: quantity live={live.quantity} rebuilt={replay.quantity}"
                )
            if abs(live.realized_pnl - replay.realized_pnl) > 1e-6:
                divergences.append(
                    f"{symbol}: realized pnl live={live.realized_pnl} "
                    f"rebuilt={replay.realized_pnl}"
                )
        return RebuildReport(
            ok=not divergences,
            checked_positions=len(stored),
            divergences=divergences,
            detail=(
                "book equals the immutable fill ledger"
                if not divergences
                else "; ".join(divergences)
            ),
        )
