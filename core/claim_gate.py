"""The statistical claim gate: a performance number may not leave the process bare.

A bare accuracy figure is not a measurement, it is an anecdote with a decimal
point. The vNext architecture requires that any performance claim be reported
with its definition, accepted sample size, coverage, time period, asset
universe, regime coverage, net-of-cost result, out-of-sample result, confidence
interval, drawdown, tail risk, experiment count, and model and dataset
versions.

This module makes that requirement executable at the boundary where numbers
become visible to an operator. It does not compute any of those fields: it
records which are present, which are missing, and refuses to mark a claim
reportable while any required field is unknown.

The design is deliberately permissive about *how* a claim is assembled and
strict about whether it may be presented. A caller that has none of the
provenance still gets a response; it gets one labelled NOT REPORTABLE, with the
missing fields named. That is the difference between a gate and a wall: the
gate changes what the system is willing to assert, not what it is able to
compute.

This is the W0 implementation of goal G190. It is the gate itself, not the
evidence ledger behind it (G040) — a claim here can be structurally complete
while the underlying evidence is thin, and that is a separate problem with a
separate gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

#: Fields a performance claim must carry before it may be presented as a
#: result. Order is the order they should be filled in during a research pass,
#: cheapest and most disqualifying first.
REQUIRED_CLAIM_FIELDS: tuple[str, ...] = (
    "metric_definition",
    "accepted_n",
    "coverage",
    "time_period",
    "asset_universe",
    "regime_coverage",
    "net_of_cost",
    "out_of_sample",
    "confidence_interval",
    "max_drawdown",
    "tail_risk",
    "experiment_count",
    "model_version",
    "dataset_version",
)

#: Fields whose absence is disqualifying but whose presence alone is not
#: sufficient. A confidence interval with no metric definition describes
#: nothing; a definition with no interval cannot be acted on. Both must be
#: present, which is what requiring all of them achieves.
_ALL_REQUIRED = frozenset(REQUIRED_CLAIM_FIELDS)


class ClaimStatus(StrEnum):
    """Whether a claim may be presented as a result."""

    #: Every required field is present and non-null.
    REPORTABLE = "REPORTABLE"
    #: One or more required fields are unknown. The number may be shown, but
    #: only alongside the gap list.
    NOT_REPORTABLE = "NOT_REPORTABLE"
    #: No metric was supplied at all.
    NO_CLAIM = "NO_CLAIM"


@dataclass(frozen=True)
class ClaimGateResult:
    """Outcome of gating one performance claim."""

    status: ClaimStatus
    value: Any
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def is_reportable(self) -> bool:
        return self.status is ClaimStatus.REPORTABLE

    def as_dict(self) -> dict[str, Any]:
        """Serialisable form, safe to attach to an API response."""
        return {
            "status": str(self.status),
            "reportable": self.is_reportable,
            "present": list(self.present),
            "missing": list(self.missing),
        }


def _is_present(value: Any) -> bool:
    """Whether a field counts as supplied.

    ``None``, empty strings, empty collections, and NaN are all "unknown".
    A zero is present: a measured value of zero is a real measurement, and
    treating it as missing would let a genuine negative result masquerade as
    an absent one.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return value == value  # NaN is the only float that is not itself
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return bool(value)
    return True


def gate_claim(metric: str, value: Any, **provenance: Any) -> ClaimGateResult:
    """Gate one performance claim.

    Args:
        metric: Name of the metric, e.g. ``"sharpe"`` or ``"win_rate"``.
        value: The measured value. May be ``None``, which yields NO_CLAIM.
        **provenance: Candidate claim fields. Names outside
            :data:`REQUIRED_CLAIM_FIELDS` are ignored rather than rejected, so
            a caller may pass extra context without changing the verdict.

    Returns:
        A :class:`ClaimGateResult` naming exactly which required fields were
        supplied and which were not.
    """
    if not _is_present(value):
        return ClaimGateResult(status=ClaimStatus.NO_CLAIM, value=value)

    present = tuple(
        name for name in REQUIRED_CLAIM_FIELDS if _is_present(provenance.get(name))
    )
    missing = tuple(name for name in REQUIRED_CLAIM_FIELDS if name not in present)
    status = ClaimStatus.REPORTABLE if not missing else ClaimStatus.NOT_REPORTABLE
    return ClaimGateResult(status=status, value=value, present=present, missing=missing)


def gate_criteria(criteria: list[dict[str, Any]], **provenance: Any) -> dict[str, Any]:
    """Gate a list of threshold criteria returned as one aggregate claim.

    Used by endpoints that report several figures together (a graduation
    check, a scorecard). Each criterion is gated individually so a client can
    see which specific figure is unqualified, and the envelope carries the
    aggregate status.
    """
    gated: list[dict[str, Any]] = []
    all_reportable = True
    for criterion in criteria:
        single = gate_claim(
            str(criterion.get("name", "unnamed")),
            criterion.get("current"),
            **provenance,
        )
        all_reportable = all_reportable and single.is_reportable
        gated.append({**criterion, "claim": single.as_dict()})
    return {
        "criteria": gated,
        "claim_status": (
            ClaimStatus.REPORTABLE if all_reportable else ClaimStatus.NOT_REPORTABLE
        ),
        "required_fields": list(REQUIRED_CLAIM_FIELDS),
    }


def assert_reportable(result: ClaimGateResult) -> None:
    """Raise when a claim may not be presented as a result.

    For use at a boundary that has no way to degrade gracefully, such as a
    publication step. Interactive surfaces should attach
    :meth:`ClaimGateResult.as_dict` instead of refusing to answer.
    """
    if not result.is_reportable:
        raise ValueError(
            f"claim {result.status}: missing required provenance "
            f"{list(result.missing)}. A performance figure may not be reported without it."
        )


@dataclass
class ClaimGateAudit:
    """Accumulates gate outcomes so a response can carry an honest summary.

    Views that report many figures across several endpoints use this to record
    what was gated without threading a return value through every builder.
    """

    results: list[tuple[str, ClaimGateResult]] = field(default_factory=list)

    def record(self, metric: str, result: ClaimGateResult) -> ClaimGateResult:
        self.results.append((metric, result))
        return result

    def gate(self, metric: str, value: Any, **provenance: Any) -> ClaimGateResult:
        return self.record(metric, gate_claim(metric, value, **provenance))

    @property
    def all_reportable(self) -> bool:
        return all(result.is_reportable for _, result in self.results)

    def summary(self) -> dict[str, Any]:
        return {
            "all_reportable": self.all_reportable,
            "gated": {
                metric: result.as_dict() for metric, result in self.results
            },
            "required_fields": list(REQUIRED_CLAIM_FIELDS),
        }


__all__ = [
    "REQUIRED_CLAIM_FIELDS",
    "ClaimGateAudit",
    "ClaimGateResult",
    "ClaimStatus",
    "assert_reportable",
    "gate_claim",
    "gate_criteria",
]
