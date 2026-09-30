"""One correlation chain per trade, every hop carrying it (goal G210).

"Why did this trade happen" is eleven hops: market_event → feature →
inference → evidence → strategy → proposal → risk_decision → authorization →
order → fill → ledger_transaction. Today each hop is logged somewhere with
nothing joining them — ``trace_id`` is a nullable outbox column nobody sets —
so the question is answered by grep across six stores, which is how an answer
becomes a story.

This module is the join key plus the assembly. :class:`TraceContext` mints
and carries one id; :class:`TraceRecorder` orders spans per trace;
:func:`why_trade` renders the chain from outbox events and recorded spans and
names the stages with nothing to say. The OpenTelemetry SDK stays deferred
(deliberate: a vendor SDK in the hot path is a dependency the deterministic
core has not earned); what lands here is the correlation discipline OTel
would carry, in stdlib, so adopting it later changes transport rather than
semantics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

__all__ = [
    "STAGES",
    "Span",
    "TraceContext",
    "TraceRecorder",
    "new_trace_id",
    "why_trade",
]

#: The canonical eleven hops, in order. Closed: a stage outside this
#: vocabulary is a hop the chain cannot place, and placing it anyway would
#: invent an ordering the architecture never defined.
STAGES: tuple[str, ...] = (
    "market_event",
    "feature",
    "inference",
    "evidence",
    "strategy",
    "proposal",
    "risk_decision",
    "authorization",
    "order",
    "fill",
    "ledger_transaction",
)

StageName = Literal[
    "market_event",
    "feature",
    "inference",
    "evidence",
    "strategy",
    "proposal",
    "risk_decision",
    "authorization",
    "order",
    "fill",
    "ledger_transaction",
]


def new_trace_id() -> str:
    """Mint a correlation id. Hex, no dashes: an id with structure invites
    parsing, and nothing should parse a correlation id."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Span:
    """One hop's record: what stage, when, and what it points at.

    ``refs`` are join keys (order_id, envelope_id, claim_id, decision
    digest) — never payloads. A span carrying payloads would duplicate every
    store it joins; a span carrying keys is an index, which is what a chain
    is for.
    """

    trace_id: str
    stage: str
    recorded_at: str
    refs: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("a span without a trace id joins nothing")
        if self.stage not in STAGES:
            raise ValueError(
                f"stage {self.stage!r} is outside the canonical chain; "
                f"known: {', '.join(STAGES)}"
            )


@dataclass(frozen=True)
class TraceContext:
    """The correlation id travelling with one trade's lifecycle."""

    trace_id: str

    @classmethod
    def new(cls) -> TraceContext:
        return cls(new_trace_id())

    def span(
        self, stage: str, *, refs: dict[str, str] | None = None, note: str = "",
        recorded_at: str | None = None,
    ) -> Span:
        return Span(
            trace_id=self.trace_id,
            stage=stage,
            recorded_at=recorded_at or datetime.now(UTC).isoformat(),
            refs=dict(refs or {}),
            note=note,
        )


class TraceRecorder:
    """Ordered spans per trace, in memory. The durable join key is the
    outbox ``trace_id`` column; this recorder is the assembly buffer for the
    current process — ``why_trade`` joins both."""

    def __init__(self) -> None:
        self._spans: dict[str, list[Span]] = {}

    def record(self, span: Span) -> Span:
        self._spans.setdefault(span.trace_id, []).append(span)
        return span

    def chain(self, trace_id: str) -> list[Span]:
        return list(self._spans.get(trace_id, []))

    def stages_present(self, trace_id: str) -> list[str]:
        seen: list[str] = []
        for span in self.chain(trace_id):
            if span.stage not in seen:
                seen.append(span.stage)
        return [stage for stage in STAGES if stage in seen]

    def missing_stages(self, trace_id: str) -> list[str]:
        """Canonical stages with no span. Gaps are reported rather than
        filled: an invented span would be the chain vouching for a hop that
        never recorded itself."""
        present = set(self.stages_present(trace_id))
        return [stage for stage in STAGES if stage not in present]

    def clear(self, trace_id: str) -> None:
        self._spans.pop(trace_id, None)


def why_trade(
    trace_id: str,
    *,
    recorder: TraceRecorder,
    outbox_events: list[Any] | None = None,
) -> dict[str, Any]:
    """Answer why a trade happened: ordered stages with their refs, the
    outbox events carrying this trace, and the stages still silent.

    Unknown trace ids return an empty chain, not an error: "nothing recorded
    under this id" is itself the finding, and raising would turn every typo
    into an incident.
    """
    spans = recorder.chain(trace_id)
    events = [
        event for event in (outbox_events or [])
        if getattr(event, "trace_id", None) == trace_id
    ]
    return {
        "trace_id": trace_id,
        "stages": [
            {"stage": span.stage, "recorded_at": span.recorded_at,
             "refs": dict(span.refs), "note": span.note}
            for span in spans
        ],
        "outbox_events": [
            {"event_type": str(getattr(event, "event_type", "")),
             "idempotency_key": str(getattr(event, "idempotency_key", ""))}
            for event in events
        ],
        "missing_stages": recorder.missing_stages(trace_id),
    }
