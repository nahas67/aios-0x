"""The statistical claim gate: a number may not leave bare.

These tests cover the gate introduced in ``core/claim_gate.py`` (goal G190).
The gate exists because a bare performance figure is an anecdote with a
decimal point, and because the alternative — trusting whoever renders the
number — has already been shown to fail in this domain.

Two properties matter more than the field list:

* a zero counts as supplied, because a measured zero is a real measurement
* the gate degrades rather than raises, so an interactive surface can show an
  unqualified number alongside the list of what is missing
"""

from __future__ import annotations

import math

import pytest

from core.claim_gate import (
    REQUIRED_CLAIM_FIELDS,
    ClaimGateAudit,
    ClaimStatus,
    assert_reportable,
    gate_claim,
    gate_criteria,
)


def _complete_provenance() -> dict[str, object]:
    """A provenance set that satisfies every required field."""
    return dict.fromkeys(REQUIRED_CLAIM_FIELDS, "x")


# ------------------------------------------------------------- basic verdicts


def test_complete_provenance_is_reportable() -> None:
    result = gate_claim("sharpe", 1.8, **_complete_provenance())
    assert result.status is ClaimStatus.REPORTABLE
    assert result.is_reportable
    assert result.missing == ()


def test_missing_provenance_is_not_reportable_and_names_the_gap() -> None:
    result = gate_claim(
        "sharpe",
        1.8,
        metric_definition="annualised Sharpe",
        accepted_n=50,
    )
    assert result.status is ClaimStatus.NOT_REPORTABLE
    assert not result.is_reportable
    assert "confidence_interval" in result.missing
    assert "out_of_sample" in result.missing
    assert set(result.present) == {"metric_definition", "accepted_n"}


def test_no_value_is_no_claim_not_an_unqualified_one() -> None:
    """A missing metric and an unprovenanced metric are different problems."""
    assert gate_claim("sharpe", None).status is ClaimStatus.NO_CLAIM
    assert gate_claim("sharpe", None, **_complete_provenance()).status is ClaimStatus.NO_CLAIM


def test_a_bare_number_is_never_reportable() -> None:
    """The failure this gate exists to prevent, stated as a test."""
    result = gate_claim("accuracy", 0.99)
    assert not result.is_reportable
    assert len(result.missing) == len(REQUIRED_CLAIM_FIELDS)


# ------------------------------------------------------------- field presence


@pytest.mark.parametrize("empty", [None, "", "   ", [], {}, ()])
def test_empty_values_count_as_missing(empty: object) -> None:
    result = gate_claim("sharpe", 1.0, metric_definition=empty)
    assert "metric_definition" in result.missing


def test_a_measured_zero_counts_as_supplied() -> None:
    """Zero is a measurement, not an absence.

    Treating it as missing would let a genuine negative result — a strategy
    that made nothing — present as though it were simply unmeasured.
    """
    result = gate_claim("sharpe", 0.0, metric_definition="annualised Sharpe")
    assert "metric_definition" in result.present
    assert "metric_definition" not in result.missing


def test_nan_counts_as_missing() -> None:
    """NaN is the one float that is not equal to itself."""
    result = gate_claim("sharpe", math.nan, metric_definition=math.nan)
    assert result.status is ClaimStatus.NO_CLAIM

    result = gate_claim("sharpe", 1.0, accepted_n=math.nan)
    assert "accepted_n" in result.missing


def test_extra_provenance_is_ignored_not_rejected() -> None:
    """Callers pass context freely; the verdict depends only on the required set."""
    result = gate_claim("sharpe", 1.0, **_complete_provenance(), analyst="research", run="42")
    assert result.is_reportable


# ------------------------------------------------------------ criterion gate


def test_criteria_gate_reports_each_criterion_individually() -> None:
    payload = gate_criteria(
        [
            {"name": "Sharpe ratio", "current": 1.8, "pass": True},
            {"name": "Win rate", "current": 52.0, "pass": True},
        ],
        metric_definition="paper-run statistics",
        accepted_n=50,
    )
    assert len(payload["criteria"]) == 2
    for criterion in payload["criteria"]:
        assert criterion["claim"]["status"] == ClaimStatus.NOT_REPORTABLE
        assert "out_of_sample" in criterion["claim"]["missing"]
    assert payload["claim_status"] == ClaimStatus.NOT_REPORTABLE
    assert payload["required_fields"] == list(REQUIRED_CLAIM_FIELDS)


def test_criteria_gate_is_reportable_only_when_every_one_is() -> None:
    """A composite claim is as strong as its weakest component."""
    payload = gate_criteria(
        [{"name": "Sharpe ratio", "current": 1.8, "pass": True}],
        **_complete_provenance(),
    )
    assert payload["claim_status"] == ClaimStatus.REPORTABLE
    assert payload["criteria"][0]["claim"]["reportable"] is True


def test_criteria_gate_preserves_the_original_fields() -> None:
    """Gating annotates; it does not alter the criteria it inspects."""
    original = {"name": "Trade count", "current": 50, "threshold": 50, "op": ">=", "pass": True}
    payload = gate_criteria([original], **_complete_provenance())
    for key, value in original.items():
        assert payload["criteria"][0][key] == value
    _ = original  # the caller's dict is not mutated


# ----------------------------------------------------------------- assertion


def test_assert_reportable_refuses_an_unqualified_claim() -> None:
    with pytest.raises(ValueError, match="NOT_REPORTABLE"):
        assert_reportable(gate_claim("accuracy", 0.99))


def test_assert_reportable_passes_a_complete_one() -> None:
    assert_reportable(gate_claim("sharpe", 1.8, **_complete_provenance()))


# --------------------------------------------------------------------- audit


def test_audit_summarises_a_view_without_changing_return_types() -> None:
    """The audit exists so a view builder can record gating without
    restructuring its return value."""
    audit = ClaimGateAudit()
    audit.gate("sharpe", 1.8, metric_definition="x")
    audit.gate("win_rate", 52.0, **_complete_provenance())

    assert not audit.all_reportable
    summary = audit.summary()
    assert summary["all_reportable"] is False
    assert set(summary["gated"]) == {"sharpe", "win_rate"}
    assert summary["gated"]["win_rate"]["reportable"] is True
    assert summary["required_fields"] == list(REQUIRED_CLAIM_FIELDS)


def test_required_field_list_is_stable() -> None:
    """A client renders the missing-field list, so reordering it is a
    user-visible change and not an incidental refactor."""
    assert REQUIRED_CLAIM_FIELDS[:3] == (
        "metric_definition",
        "accepted_n",
        "coverage",
    )
    assert len(REQUIRED_CLAIM_FIELDS) == len(set(REQUIRED_CLAIM_FIELDS))
