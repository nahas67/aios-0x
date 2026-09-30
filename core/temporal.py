"""Point-in-time time authority: six clocks, one ordering (vNext goal G030).

A financial system that records one timestamp per observation cannot answer the
question "was this knowable at decision time?". It can answer when the row was
written, which is a different question, and conflating the two is look-ahead by
construction. Every backtest that joins a price to a decision on a single
timestamp is therefore suspect until the join key is proven to be the knowable
time rather than the write time.

This module is the answer. A TemporalInstant carries the six clocks the vNext
architecture requires, in the order they must occur:

event_time
    When the event happened in the world (the bar closed, the filing was signed).
source_time
    When the source recorded it (the exchange stamped the trade, the SEC accepted).
available_at
    When it became knowable to a consumer (the feed published, the filing hit EDGAR).
received_at
    When AIOS received it (the fetcher returned, the socket delivered).
processed_at
    When AIOS finished processing it (validation, normalisation, storage).
sequence
    Monotonic tiebreaker within one producer, so two events with identical
    clocks still have a total order.

The ordering event_time <= source_time <= available_at <= received_at <=
processed_at is enforced at construction. A violation is a caller bug, not a
data problem, so it raises rather than warns.

The second half of the module is the look-ahead tripwire. ``assert_no_lookahead``
refuses to return data whose knowable time is after the decision time, and
``filter_as_of`` applies the same rule to a collection. Both raise or exclude
rather than warn, because a warning in a research pipeline becomes a footnote
in a report that nobody reads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

__all__ = [
    "LookaheadViolation",
    "TemporalInstant",
    "assert_no_lookahead",
    "filter_as_of",
    "is_as_of_unknown",
]

T = TypeVar("T")


class LookaheadViolation(ValueError):
    """A query asked for data that was not knowable at the decision time.

    Raised rather than warned. A warning in a research pipeline becomes a
    footnote nobody reads, and the backtest that follows it is wrong in exactly
    the way that looks like skill.
    """


@dataclass(frozen=True)
class TemporalInstant:
    """Six clocks for one observation, in the order they must occur."""

    event_time: datetime
    source_time: datetime
    available_at: datetime
    received_at: datetime
    processed_at: datetime
    sequence: int = 0

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        ordered = [
            ("event_time", self.event_time),
            ("source_time", self.source_time),
            ("available_at", self.available_at),
            ("received_at", self.received_at),
            ("processed_at", self.processed_at),
        ]
        for (first_name, first), (second_name, second) in zip(ordered, ordered[1:], strict=False):
            if second < first:
                raise ValueError(
                    f"{second_name} ({second.isoformat()}) precedes {first_name} "
                    f"({first.isoformat()}). Clocks must be non-decreasing in the order "
                    "event_time <= source_time <= available_at <= received_at <= processed_at."
                )

    @property
    def knowable_at(self) -> datetime:
        """When a decision-maker could first have used this observation."""
        return self.available_at

    def is_knowable_at(self, as_of: datetime) -> bool:
        """True when this observation was knowable at the decision time."""
        return self.available_at <= as_of

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_time": self.event_time.isoformat(),
            "source_time": self.source_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "sequence": self.sequence,
        }


def assert_no_lookahead(
    knowable_at: datetime | None,
    as_of: datetime,
    what: str = "observation",
) -> None:
    """Refuse data whose knowable time is after the decision time.

    ``None`` is the honest unknown: a row that cannot say when it became
    knowable cannot prove it was knowable, so it is refused with the same
    error rather than admitted on trust.
    """
    if knowable_at is None:
        raise LookaheadViolation(
            f"{what} has no knowable time (available_at is unknown) and cannot be "
            f"used at {as_of.isoformat()}. Backfill available_at or exclude the row."
        )
    if knowable_at > as_of:
        raise LookaheadViolation(
            f"{what} became knowable at {knowable_at.isoformat()} which is after the "
            f"decision time {as_of.isoformat()}. Using it would be look-ahead."
        )


def filter_as_of(
    items: list[T],
    as_of: datetime,
    knowable_fn: Callable[[T], datetime | None],
) -> list[T]:
    """Return only the items knowable at the decision time.

    Items with an unknown knowable time are excluded, not included. An unknown
    timestamp is not "probably fine"; it is the absence of the proof this
    function exists to require.
    """
    kept: list[T] = []
    for item in items:
        knowable = knowable_fn(item)
        if knowable is not None and knowable <= as_of:
            kept.append(item)
    return kept


def is_as_of_unknown(knowable_at: datetime | None) -> bool:
    """True when a row cannot prove when it became knowable."""
    return knowable_at is None
