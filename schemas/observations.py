"""Point-in-time feature observations (schema contract).

A feature value with the moment it became knowable, plus one feature's
availability relative to one decision. This lives in schemas (rather than in
the playbook module that first defined it) because communities may depend on
schema contracts but never on kernel modules, and the regime detector in
communities/c10_world must emit the same observations the router in
kernel/playbook consumes. One definition, depended on from both sides,
instead of two shapes that agree by convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["FeatureObservation", "FeatureTiming"]


@dataclass(frozen=True)
class FeatureObservation:
    """One named value, with when it became knowable.

    ``available_at`` is the join key rather than the value's own timestamp:
    a feature computed at 09:00 from a bar published at 09:30 is contaminated
    even though the computation ran first. Frozen, because an observation is
    evidence: mutating it after the fact rewrites what was known when.
    """

    name: str
    value: float
    available_at: datetime

    def as_timing(self, decision_time: datetime) -> FeatureTiming:
        return FeatureTiming(
            feature_name=self.name, available_at=self.available_at, decision_time=decision_time
        )


@dataclass(frozen=True)
class FeatureTiming:
    """One feature's availability relative to one decision.

    Shaped to be passed directly to the contamination detector, so a
    selection is audited with the same check that audits a backtest rather
    than with a second, weaker one.
    """

    feature_name: str
    available_at: datetime
    decision_time: datetime

    @property
    def is_look_ahead(self) -> bool:
        return self.available_at > self.decision_time
