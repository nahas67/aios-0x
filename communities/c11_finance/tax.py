"""Community 11: Tax lots (FIFO) + jurisdiction rule engine.

Every computation carries its rule citation and a hard
``requires_professional_signoff=True`` flag: the system prepares, humans and
licensed professionals authorize filings (Directives 42/47).
"""

from collections import deque
from datetime import datetime

from schemas.contracts import (
    Disposal,
    TaxComputation,
    TaxLotOpen,
    TradeExecutionReceipt,
)

_LONG_TERM_DAYS_DEFAULT = 365


class LotBook:
    """Per-symbol FIFO lot queues with partial consumption."""

    def __init__(self, long_term_days: int = _LONG_TERM_DAYS_DEFAULT) -> None:
        self.long_term_days = long_term_days
        self._lots: dict[str, deque[TaxLotOpen]] = {}

    def open_from_fill(
        self,
        receipt: TradeExecutionReceipt,
        opened_at: datetime,
        fees_minor_allocatable: int | None = None,
    ) -> TaxLotOpen:
        qty = receipt.filled_quantity
        unit_cost = int(round(receipt.fill_price * 100))
        lot = TaxLotOpen(
            symbol=receipt.symbol,
            opened_at=opened_at,
            qty_original=qty,
            qty_remaining=qty,
            unit_cost_minor=unit_cost,
            fees_minor=fees_minor_allocatable or 0,
            ref_execution_id=receipt.execution_id,
        )
        self._lots.setdefault(receipt.symbol, deque()).append(lot)
        return lot

    def consume(
        self,
        symbol: str,
        quantity: float,
        exit_price: float,
        disposed_at: datetime,
        ref_execution_id_exit: str,
    ) -> list[Disposal]:
        """FIFO-consume lots; raises ValueError when quantity exceeds holdings."""
        remaining_to_close = quantity
        queue = self._lots.get(symbol)
        if not queue:
            raise ValueError(f"no open lots for {symbol}")

        disposals: list[Disposal] = []
        exit_unit_minor = int(round(exit_price * 100))
        while remaining_to_close > 1e-9 and queue:
            lot = queue[0]
            take = min(lot.qty_remaining, remaining_to_close)
            fraction = take / lot.qty_original if lot.qty_original else 0.0
            basis = int(round((lot.unit_cost_minor * take) + lot.fees_minor * fraction))
            proceeds = int(round(exit_unit_minor * take))
            gain = proceeds - basis

            holding_days = max(0, (disposed_at - lot.opened_at).days)
            disposals.append(
                Disposal(
                    lot_id=lot.lot_id,
                    symbol=symbol,
                    disposed_qty=take,
                    basis_minor=basis,
                    proceeds_minor=proceeds,
                    gain_minor=gain,
                    holding_days=holding_days,
                    long_term=holding_days >= self.long_term_days,
                    disposed_at=disposed_at,
                    ref_execution_id_exit=ref_execution_id_exit,
                )
            )
            lot.qty_remaining -= take
            remaining_to_close -= take
            if lot.qty_remaining <= 1e-9:
                queue.popleft()

        if remaining_to_close > 1e-9:
            raise ValueError(f"insufficient lots for {symbol}: short by {remaining_to_close:.6f}")
        return disposals

    def open_qty(self, symbol: str) -> float:
        return sum(lot.qty_remaining for lot in self._lots.get(symbol, ()))


# ------------------------------------------------------------------ rules


class TaxRule:
    """Illustrative advisory rule with citation; NOT legal advice."""

    def __init__(
        self,
        rule_id: str,
        jurisdiction: str,
        citation: str,
        description: str,
        long_term_rate_pct: float,
        short_term_rate_pct: float,
    ) -> None:
        self.rule_id = rule_id
        self.jurisdiction = jurisdiction
        self.citation = citation
        self.description = description
        self.long_term_rate_pct = long_term_rate_pct
        self.short_term_rate_pct = short_term_rate_pct


BUILTIN_RULES: dict[str, TaxRule] = {
    "IN_VDA_FLAT30": TaxRule(
        rule_id="IN_VDA_FLAT30",
        jurisdiction="IN",
        citation="Income-tax Act 1961 s.115BBH (30% flat on VDA transfers); s.115ADH set-off limits",
        description=(
            "India: flat 30% on virtual-digital-asset gains; no expense deduction "
            "beyond cost; losses not set off against other heads."
        ),
        long_term_rate_pct=30.0,
        short_term_rate_pct=30.0,
    ),
    "US_IRC_1222": TaxRule(
        rule_id="US_IRC_1222",
        jurisdiction="US",
        citation="IRC §1222 holding periods; §1(h) LTCG brackets; ordinary rates for STCG",
        description=(
            "United States: long-term vs short-term split by >1-year holding; "
            "simplified bracket placeholders pending taxpayer-specific inputs."
        ),
        long_term_rate_pct=15.0,
        short_term_rate_pct=37.0,
    ),
    "GENERIC_25": TaxRule(
        rule_id="GENERIC_25",
        jurisdiction="GENERIC",
        citation="Placeholder advisory rate - replace with licensed guidance",
        description="Neutral placeholder applied when no jurisdiction is configured.",
        long_term_rate_pct=25.0,
        short_term_rate_pct=25.0,
    ),
}


class TaxEngine:
    """Aggregates disposals under one cited rule; always advisory."""

    def __init__(self, rule: TaxRule) -> None:
        self.rule = rule

    def compute(self, disposals: list[Disposal]) -> TaxComputation:
        long_gain = sum(d.gain_minor for d in disposals if d.long_term)
        short_gain = sum(d.gain_minor for d in disposals if not d.long_term)

        tax_long = max(0, long_gain) * self.rule.long_term_rate_pct / 100.0
        tax_short = max(0, short_gain) * self.rule.short_term_rate_pct / 100.0
        total_taxable = max(0, long_gain) + max(0, short_gain)
        tax_due = int(round(tax_long + tax_short))

        return TaxComputation(
            jurisdiction=self.rule.jurisdiction,
            rule_id=self.rule.rule_id,
            rule_citation=self.rule.citation,
            inputs_summary=(
                f"disposals={len(disposals)} LT_gain={long_gain} ST_gain={short_gain} minor"
            ),
            taxable_gain_minor=total_taxable,
            tax_due_minor=max(0, tax_due),
        )
