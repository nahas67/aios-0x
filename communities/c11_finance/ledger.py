"""Community 11: Double-entry ledger in integer minor units.

Invariant: the trial balance ALWAYS sums to zero - every posting debits one
account and credits another by identical amounts. Floats are converted to
integer cents exactly once at posting boundaries.
"""

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import Posting


def to_minor(amount: float) -> int:
    """Convert float major units to integer minor units (banker-safe rounding)."""
    return int(round(amount * 100))


class DoubleEntryLedger:
    """In-memory books with a hard zero-sum invariant."""

    def __init__(self, event_bus: BaseEventBus | None = None) -> None:
        self.event_bus = event_bus
        self.postings: list[Posting] = []

    async def post(
        self,
        debit_account: str,
        credit_account: str,
        amount_minor: int,
        memo: str = "",
        refs: dict[str, str] | None = None,
    ) -> Posting:
        if amount_minor <= 0:
            raise ValueError("posting amount must be positive minor units")
        if debit_account == credit_account:
            raise ValueError("debit and credit accounts must differ")
        posting = Posting(
            debit_account=debit_account,
            credit_account=credit_account,
            amount_minor=amount_minor,
            memo=memo,
            refs=refs or {},
        )
        self.postings.append(posting)
        if self.event_bus is not None:
            await self.event_bus.publish(EventTopic.LEDGER_POSTED, posting)
        return posting

    def balances(self) -> dict[str, int]:
        """Net per account: debits increase, credits decrease."""
        out: dict[str, int] = {}
        for p in self.postings:
            out[p.debit_account] = out.get(p.debit_account, 0) + p.amount_minor
            out[p.credit_account] = out.get(p.credit_account, 0) - p.amount_minor
        return {k: v for k, v in sorted(out.items())}

    def trial_balance_total(self) -> int:
        """MUST be zero; nonzero means corrupted books (caller should halt)."""
        return sum(self.balances().values())

    # ------------------------------------------------- trading book entries

    async def post_fill_open(
        self,
        symbol: str,
        fill_price: float,
        quantity: float,
        fees: float,
        execution_id: str,
    ) -> list[Posting]:
        cost = to_minor(fill_price * quantity)
        fees_c = to_minor(fees)
        out = [
            await self.post(
                f"ASSET:{symbol}",
                "CASH",
                cost,
                memo="open position at cost",
                refs={"execution_id": execution_id},
            )
        ]
        if fees_c > 0:
            out.append(
                await self.post(
                    "EXPENSE:FEES",
                    "CASH",
                    fees_c,
                    memo="entry fees",
                    refs={"execution_id": execution_id},
                )
            )
        return out

    async def post_exit_close(
        self,
        symbol: str,
        basis_released_minor: int,
        proceeds_minor: int,
        realized_pnl_minor: int,
        execution_id: str,
    ) -> list[Posting]:
        out = [
            await self.post(
                "CASH",
                f"ASSET:{symbol}",
                basis_released_minor,
                memo="release cost basis",
                refs={"execution_id": execution_id},
            )
        ]
        if realized_pnl_minor > 0:
            out.append(
                await self.post(
                    "CASH",
                    "INCOME:REALIZED_PNL",
                    realized_pnl_minor,
                    memo="realized gain",
                    refs={"execution_id": execution_id},
                )
            )
        elif realized_pnl_minor < 0:
            out.append(
                await self.post(
                    "EXPENSE:REALIZED_LOSS",
                    "CASH",
                    -realized_pnl_minor,
                    memo="realized loss",
                    refs={"execution_id": execution_id},
                )
            )
        _ = proceeds_minor  # informational; CASH legs already net via basis+pnl
        return out
