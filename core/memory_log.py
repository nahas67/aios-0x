"""Trading memory log: pending→resolved decision state machine with reflection.

Ported from TradingAgents (TauricResearch) memory.py, adapted for AIOS-0X's
hash-chained store. The protocol:

Phase A (pending):   decision stored, no outcome yet
Phase B (resolved):  outcome arrives → reflection appended → retrievable

Two-tier retrieval: n_same most recent resolved same-symbol entries (full),
n_cross most recent cross-symbol entries (reflection-only, decision truncated).
Pending entries are never pruned. Reflections are budgeted at 2-4 sentences —
token-cost-aware lessons, not essays.
"""

import re
from dataclasses import dataclass
from typing import Any

ENTRY_DELIMITER = "\n\n<!-- ENTRY_END -->\n\n"
_TAG_RE = re.compile(
    r"\[(?P<date>[^|]+)\|(?P<symbol>[^|]+)\|(?P<action>[^|]+)\|(?P<status>[^\]]+)\]"
)


@dataclass
class MemoryEntry:
    date: str
    symbol: str
    action: str
    status: str  # "pending" | "+X.X%" | "-X.X%"
    decision: str
    reflection: str = ""
    alpha: str = ""
    holding_days: str = ""


class TradingMemoryLog:
    """Append-only decision log with two-phase lifecycle and two-tier retrieval."""

    def __init__(
        self,
        max_entries: int = 200,
        reflect_fn: Any = None,
    ) -> None:
        self._entries: list[MemoryEntry] = []
        self._max_entries = max_entries
        self._reflect_fn = reflect_fn  # async (decision, raw_return, alpha) -> str

    def store_decision(self, symbol: str, trade_date: str, action: str, decision: str) -> None:
        """Phase A: store a pending decision. Idempotent per symbol+date."""
        tag = f"[{trade_date} | {symbol} | {action} | pending]"
        for e in self._entries:
            if e.symbol == symbol and e.date == trade_date and e.status == "pending":
                return  # idempotent
        self._entries.append(
            MemoryEntry(
                date=trade_date, symbol=symbol, action=action, status="pending", decision=decision
            )
        )
        self._rotate()

    async def update_with_outcome(
        self,
        symbol: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int = 5,
    ) -> str | None:
        """Phase B: resolve a pending entry with outcome + reflection."""
        for e in self._entries:
            if e.symbol == symbol and e.date == trade_date and e.status == "pending":
                sign = "+" if raw_return >= 0 else ""
                e.status = f"{sign}{raw_return:.1f}%"
                e.alpha = f"{alpha_return:+.1f}%"
                e.holding_days = str(holding_days)
                if self._reflect_fn:
                    e.reflection = await self._reflect_fn(e.decision, raw_return, alpha_return)
                return e.reflection
        return None

    def get_past_context(self, symbol: str, n_same: int = 5, n_cross: int = 3) -> str:
        """Two-tier retrieval: same-symbol full, cross-symbol reflection-only."""
        resolved = [e for e in self._entries if e.status != "pending"]
        same = [e for e in resolved if e.symbol == symbol][-n_same:]
        cross = [e for e in resolved if e.symbol != symbol][-n_cross:]

        blocks: list[str] = []
        for e in reversed(same):  # most recent first
            blocks.append(self._format_full(e))
        for e in reversed(cross):
            blocks.append(self._format_reflection_only(e))
        return "\n\n".join(blocks)

    def pending_count(self) -> int:
        return sum(1 for e in self._entries if e.status == "pending")

    def _format_full(self, e: MemoryEntry) -> str:
        return (
            f"[{e.date} | {e.symbol} | {e.action} | {e.status} | {e.alpha} | {e.holding_days}d]\n"
            f"DECISION:\n{e.decision}\n" + (f"REFLECTION:\n{e.reflection}" if e.reflection else "")
        )

    def _format_reflection_only(self, e: MemoryEntry) -> str:
        truncated = e.decision[:300] + ("..." if len(e.decision) > 300 else "")
        return (
            f"[{e.date} | {e.symbol} | {e.action} | {e.status}]\n"
            f"DECISION (truncated): {truncated}\n"
            + (f"REFLECTION:\n{e.reflection}" if e.reflection else "")
        )

    def _rotate(self) -> None:
        """Prune oldest resolved entries beyond max; never prune pending."""
        resolved = [e for e in self._entries if e.status != "pending"]
        pending = [e for e in self._entries if e.status == "pending"]
        if len(resolved) > self._max_entries:
            self._entries = pending + resolved[-self._max_entries :]


def build_reflection_prompt(
    decision: str, raw_return: float, alpha_return: float, benchmark: str = "SPY"
) -> str:
    """Budget the reflection for reinjection — 2-4 sentences, not an essay."""
    return (
        f"You are reflecting on a completed trading decision for the purpose of "
        f"organizational learning. Your output will be stored verbatim in a "
        f"decision log and re-read by future analysts, so every word must earn "
        f"its place.\n\n"
        f"DECISION:\n{decision}\n\n"
        f"OUTCOME: raw return {raw_return:+.1f}%, alpha vs {benchmark} {alpha_return:+.1f}%\n\n"
        f"Reflect in exactly 2-4 sentences of plain prose covering, in order:\n"
        f"1. Was the call correct (cite alpha vs {benchmark})?\n"
        f"2. Which specific part of the thesis held or failed?\n"
        f"3. One concrete lesson for future decisions.\n\n"
        f"Output ONLY the reflection prose. No headers, no bullet points."
    )
