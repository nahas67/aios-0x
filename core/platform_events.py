"""Typed platform events (Phase D): the control plane's orchestration stream.

The prototype had trading events (data_acquired, order_filled). The original
architecture demands PLATFORM events — hypothesis lifecycle, experiment
lifecycle, promotion lifecycle — that let the control plane orchestrate
without scraping business topics.

Wire names follow the ADR-002 namespace convention:
``aios.platform.<event_name>``.

Design note: one validated ``PlatformEvent`` model discriminated by
``PlatformEventType`` rather than a dozen near-identical classes. The type is
the contract; factories enforce which fields each event requires. Every event
carries its actor, object reference, reason and any decision receipt ids, so
the stream alone answers WHO did WHAT to WHICH object and WHY.

Publishing through the normal event bus means the runner's audit logger
subscribes automatically: platform events land in the hash-chained log for
free, tamper-evident like everything else.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PlatformEventType(StrEnum):
    """Canonical platform lifecycle events (original architecture §18)."""

    DATASET_VERSION_CREATED = "aios.platform.dataset_version_created"
    EXPERIMENT_STARTED = "aios.platform.experiment_started"
    EXPERIMENT_COMPLETED = "aios.platform.experiment_completed"
    HYPOTHESIS_CREATED = "aios.platform.hypothesis_created"
    HYPOTHESIS_REJECTED = "aios.platform.hypothesis_rejected"
    EVALUATION_COMPLETED = "aios.platform.evaluation_completed"
    ORDER_REQUESTED = "aios.platform.order_requested"
    ORDER_AUTHORIZED = "aios.platform.order_authorized"
    ORDER_DENIED = "aios.platform.order_denied"
    RISK_DECISION_MADE = "aios.platform.risk_decision_made"
    EXECUTION_COMPLETED = "aios.platform.execution_completed"
    POST_MORTEM_CREATED = "aios.platform.post_mortem_created"
    PROMOTION_APPROVED = "aios.platform.promotion_approved"
    PROMOTION_DENIED = "aios.platform.promotion_denied"
    ROLLBACK_TRIGGERED = "aios.platform.rollback_triggered"


class PlatformEvent(BaseModel):
    """A typed, auditable platform lifecycle event."""

    event_type: PlatformEventType
    actor_id: str
    object_type: str
    object_id: str
    reason: str = ""
    occurred_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    receipt_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _make(
    event_type: PlatformEventType,
    actor_id: str,
    object_type: str,
    object_id: str,
    reason: str,
    receipt_ids: list[str] | None = None,
    **metadata: Any,
) -> PlatformEvent:
    return PlatformEvent(
        event_type=event_type,
        actor_id=actor_id,
        object_type=object_type,
        object_id=object_id,
        reason=reason,
        receipt_ids=receipt_ids or [],
        metadata=metadata,
    )


# ------------------------------------------------------------- constructors


def dataset_version_created(
    dataset_id: str, version: str, content_hash: str, actor_id: str = "c1-data-fabric"
) -> PlatformEvent:
    return _make(
        PlatformEventType.DATASET_VERSION_CREATED,
        actor_id,
        "dataset",
        f"{dataset_id}:{version}",
        f"dataset {dataset_id}@{version} registered+validated+activated",
        content_hash=content_hash,
    )


def experiment_started(experiment_id: str, dataset_version: str, seed: int) -> PlatformEvent:
    return _make(
        PlatformEventType.EXPERIMENT_STARTED,
        "system",
        "experiment",
        experiment_id,
        "replay experiment started",
        dataset_version=dataset_version,
        random_seed=seed,
    )


def experiment_completed(experiment_id: str, result_summary: dict[str, Any]) -> PlatformEvent:
    return _make(
        PlatformEventType.EXPERIMENT_COMPLETED,
        "system",
        "experiment",
        experiment_id,
        "replay experiment completed",
        **result_summary,
    )


def hypothesis_created(hypothesis_id: str, symbol: str, statement: str) -> PlatformEvent:
    return _make(
        PlatformEventType.HYPOTHESIS_CREATED,
        "c2-research",
        "hypothesis",
        hypothesis_id,
        statement[:200],
        symbol=symbol,
    )


def hypothesis_rejected(hypothesis_id: str, pnl: float) -> PlatformEvent:
    return _make(
        PlatformEventType.HYPOTHESIS_REJECTED,
        "system",
        "hypothesis",
        hypothesis_id,
        f"postmortem outcome; realized_pnl={pnl:+.2f} contradicted the thesis",
        realized_pnl=pnl,
    )


def evaluation_completed(strategy_id: str, exit_reason: str, realized_pnl: float) -> PlatformEvent:
    return _make(
        PlatformEventType.EVALUATION_COMPLETED,
        "system",
        "strategy",
        strategy_id,
        f"exit {exit_reason}; realized_pnl={realized_pnl:+.2f}",
        realized_pnl=realized_pnl,
    )


def order_requested(plan_id: str, strategy_id: str, action: str, symbol: str) -> PlatformEvent:
    return _make(
        PlatformEventType.ORDER_REQUESTED,
        "c5-execution",
        "strategy",
        strategy_id,
        f"plan {plan_id[:8]} {action} {symbol}",
        plan_id=plan_id,
        action=action,
        symbol=symbol,
    )


def order_authorized(
    plan_id: str, strategy_id: str, receipt_id: str | None = None
) -> PlatformEvent:
    return _make(
        PlatformEventType.ORDER_AUTHORIZED,
        "kernel.authority",
        "strategy",
        strategy_id,
        f"authority ALLOW for plan {plan_id[:8]}",
        receipt_ids=[receipt_id] if receipt_id else [],
        plan_id=plan_id,
    )


def order_denied(
    strategy_id: str, reason: str, receipt_ids: list[str] | None = None, source: str = "kernel.authority"
) -> PlatformEvent:
    return _make(
        PlatformEventType.ORDER_DENIED,
        source,
        "strategy",
        strategy_id,
        reason,
        receipt_ids=receipt_ids or [],
    )


def risk_decision_made(
    decision: str, strategy_id: str, reason: str, receipt_id: str | None = None
) -> PlatformEvent:
    return _make(
        PlatformEventType.RISK_DECISION_MADE,
        "c9-governor",
        "strategy",
        strategy_id,
        f"{decision}: {reason}",
        receipt_ids=[receipt_id] if receipt_id else [],
        decision=decision,
    )


def execution_completed(
    execution_id: str, symbol: str, fill_price: float, quantity: float, venue: str
) -> PlatformEvent:
    return _make(
        PlatformEventType.EXECUTION_COMPLETED,
        "c5-execution",
        "execution",
        execution_id,
        f"filled {quantity:g} {symbol} @ {fill_price:g} on {venue}",
        symbol=symbol,
        fill_price=fill_price,
        quantity=quantity,
        venue=venue,
    )


def post_mortem_created(
    postmortem_id: str, hypothesis_id: str, symbol: str
) -> PlatformEvent:
    return _make(
        PlatformEventType.POST_MORTEM_CREATED,
        "c6-observation",
        "postmortem",
        postmortem_id,
        f"postmortem for hypothesis {hypothesis_id}",
        symbol=symbol,
        hypothesis_id=hypothesis_id,
    )
