"""Institutional memory tiering: M0 (working) through M9 (constitutional/long-shadow).

Each tier carries a FROZEN config: retention horizon, decay half-life (or None
for tiers that never decay), promotion threshold, and demotion rule. Configs
are frozen at import time — no agent path can retune a horizon or half-life.

Headline gate: records labelled ``Criticality.SAFETY`` NEVER decay and NEVER
expire, regardless of tier. The safety check lives inside the salience and
expiry functions themselves (not in callers), so no caller can forget it.

Decay is a pure function of ``(age, half-life, criticality, access_count)``:
deterministic, stdlib only, no clocks inside. Callers pass ``now`` explicitly
as epoch seconds, which also keeps tests free of sleep-waits.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

#: Salience floor for SAFETY-critical records. ``salience_score`` returns the
#: record's full base score for SAFETY regardless of age, so this floor always
#: holds even when the clock is advanced past every tier half-life.
SAFETY_SALIENCE_FLOOR: float = 1.0

#: Fractional salience boost per access, applied as ``1 + ACCESS_BOOST *
#: log1p(access_count)``. Small enough that a heavily-read stale record can
#: never outrank a fresh one on accessed-count alone.
ACCESS_BOOST: float = 0.05


class Criticality(StrEnum):
    ROUTINE = "ROUTINE"
    IMPORTANT = "IMPORTANT"
    SAFETY = "SAFETY"


class MemoryTier(StrEnum):
    M0 = "M0"
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"
    M6 = "M6"
    M7 = "M7"
    M8 = "M8"
    M9 = "M9"


class TierConfig(BaseModel, frozen=True):
    """Frozen per-tier policy. ``None`` horizon means retain indefinitely."""

    tier: MemoryTier
    retention_horizon_seconds: float | None
    half_life_seconds: float | None
    promotion_threshold: float = Field(ge=0.0, le=1.0)
    demotion_rule: str


def _h(days: float) -> float:
    return days * 24.0 * 3600.0


TIER_TABLE: dict[MemoryTier, TierConfig] = {
    MemoryTier.M0: TierConfig(
        tier=MemoryTier.M0,
        retention_horizon_seconds=4.0 * 3600.0,
        half_life_seconds=30.0 * 60.0,
        promotion_threshold=0.90,
        demotion_rule="expire silently past horizon; never demote (nothing below M0)",
    ),
    MemoryTier.M1: TierConfig(
        tier=MemoryTier.M1,
        retention_horizon_seconds=_h(1.0),
        half_life_seconds=6.0 * 3600.0,
        promotion_threshold=0.85,
        demotion_rule="demote to M0 while salience < 0.25, else expire past horizon",
    ),
    MemoryTier.M2: TierConfig(
        tier=MemoryTier.M2,
        retention_horizon_seconds=_h(7.0),
        half_life_seconds=_h(2.0),
        promotion_threshold=0.80,
        demotion_rule="demote to M1 while salience < 0.25, else expire past horizon",
    ),
    MemoryTier.M3: TierConfig(
        tier=MemoryTier.M3,
        retention_horizon_seconds=_h(30.0),
        half_life_seconds=_h(10.0),
        promotion_threshold=0.75,
        demotion_rule="demote to M2 while salience < 0.20, else expire past horizon",
    ),
    MemoryTier.M4: TierConfig(
        tier=MemoryTier.M4,
        retention_horizon_seconds=_h(90.0),
        half_life_seconds=_h(30.0),
        promotion_threshold=0.70,
        demotion_rule="demote to M3 while salience < 0.20, else expire past horizon",
    ),
    MemoryTier.M5: TierConfig(
        tier=MemoryTier.M5,
        retention_horizon_seconds=_h(180.0),
        half_life_seconds=_h(60.0),
        promotion_threshold=0.65,
        demotion_rule="demote to M4 while salience < 0.15, else expire past horizon",
    ),
    MemoryTier.M6: TierConfig(
        tier=MemoryTier.M6,
        retention_horizon_seconds=_h(365.0),
        half_life_seconds=_h(120.0),
        promotion_threshold=0.60,
        demotion_rule="demote to M5 while salience < 0.15, else expire past horizon",
    ),
    MemoryTier.M7: TierConfig(
        tier=MemoryTier.M7,
        retention_horizon_seconds=_h(730.0),
        half_life_seconds=_h(365.0),
        promotion_threshold=0.50,
        demotion_rule="never auto-demote; human review only",
    ),
    MemoryTier.M8: TierConfig(
        tier=MemoryTier.M8,
        retention_horizon_seconds=None,
        half_life_seconds=None,
        promotion_threshold=0.90,
        demotion_rule="never demote; constitutional amendment only",
    ),
    MemoryTier.M9: TierConfig(
        tier=MemoryTier.M9,
        retention_horizon_seconds=None,
        half_life_seconds=None,
        promotion_threshold=1.0,
        demotion_rule="terminal tier; never demotes, never expires",
    ),
}


class MemoryRecord(BaseModel, frozen=True):
    """One tiered memory record. ``created_at`` is epoch seconds."""

    record_id: str
    tier: MemoryTier
    criticality: Criticality
    created_at: float
    base_score: float = Field(default=1.0, ge=0.0)
    access_count: int = Field(default=0, ge=0)


def get_tier_config(tier: MemoryTier) -> TierConfig:
    """Return the frozen config for a tier (KeyError on unknown tier)."""
    return TIER_TABLE[tier]


def salience_score(
    *,
    age_seconds: float,
    half_life_seconds: float | None,
    criticality: Criticality,
    access_count: int,
    base_score: float = 1.0,
) -> float:
    """Pure decay function: exponential half-life decay with an access boost.

    - SAFETY criticality returns ``base_score`` unchanged (never decays).
    - ``half_life_seconds=None`` means no decay (constitutional tiers).
    - Non-positive ages are treated as zero (clock skew is not decay).
    """
    if criticality is Criticality.SAFETY:
        return base_score
    age = max(0.0, age_seconds)
    if half_life_seconds is None or half_life_seconds <= 0.0 or age <= 0.0:
        decay = 1.0
    else:
        decay = 0.5 ** (age / half_life_seconds)
    boost = 1.0 + ACCESS_BOOST * math.log1p(max(0, access_count))
    return base_score * decay * boost


def record_salience(record: MemoryRecord, now: float) -> float:
    """Salience of a record at time ``now`` (epoch seconds)."""
    config = TIER_TABLE[record.tier]
    return salience_score(
        age_seconds=now - record.created_at,
        half_life_seconds=config.half_life_seconds,
        criticality=record.criticality,
        access_count=record.access_count,
        base_score=record.base_score,
    )


def is_expired(record: MemoryRecord, now: float) -> bool:
    """True when a record is past its tier retention horizon.

    SAFETY records never expire; tiers with ``None`` horizon never expire.
    """
    if record.criticality is Criticality.SAFETY:
        return False
    horizon = TIER_TABLE[record.tier].retention_horizon_seconds
    if horizon is None:
        return False
    return (now - record.created_at) > horizon


def meets_promotion_threshold(signal_strength: float, tier: MemoryTier) -> bool:
    """True when ``signal_strength`` clears the tier's promotion threshold."""
    return signal_strength >= TIER_TABLE[tier].promotion_threshold


def salience_for(metadata: dict[str, Any], now: float) -> float | None:
    """Salience of a vector-store document from its metadata, or ``None`` to
    exclude it (expired). The ``SalienceFunction`` the recall path injects.

    Metadata keys: ``tier`` (M0..M9), ``criticality``, ``created_at`` (epoch
    seconds), ``access_count``, ``base_score``. Documents without tier
    metadata — everything stored before tiering existed — score neutral 1.0:
    recall degrades open (show the document) rather than closed (hide it) on
    metadata faults, and only computable expiry excludes. Unparseable tier or
    criticality names likewise fall back to neutral rather than raising
    inside a search: one bad document must not fail the whole recall.
    """
    raw_tier = metadata.get("tier")
    raw_created = metadata.get("created_at")
    if raw_tier is None or raw_created is None:
        return 1.0
    try:
        tier = MemoryTier(str(raw_tier))
    except ValueError:
        return 1.0
    try:
        created_at = float(raw_created)
    except (TypeError, ValueError):
        return 1.0
    try:
        criticality = Criticality(str(metadata.get("criticality", Criticality.ROUTINE.value)))
    except ValueError:
        return 1.0
    try:
        access_count = int(metadata.get("access_count", 0))
    except (TypeError, ValueError):
        access_count = 0
    try:
        base_score = float(metadata.get("base_score", 1.0))
    except (TypeError, ValueError):
        base_score = 1.0
    record = MemoryRecord(
        record_id=str(metadata.get("doc_id", "")),
        tier=tier,
        criticality=criticality,
        created_at=created_at,
        base_score=max(0.0, base_score),
        access_count=max(0, access_count),
    )
    if is_expired(record, now):
        return None
    return record_salience(record, now)


def rank_by_salience(records: list[MemoryRecord], now: float) -> list[MemoryRecord]:
    """Records ordered most-salient first at time ``now`` (stable sort)."""
    scored = [(record_salience(record, now), index, record) for index, record in enumerate(records)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record for _, _, record in scored]
