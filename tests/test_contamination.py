"""Contamination is measured, not declared (goal G080, final piece).

The certification firewall ended with two booleans it believed:
``look_ahead=False`` and ``survivorship_bias=False``. This suite covers the
detectors that replaced them, and the property that matters most:

**A detector that never ran is not a detector that found nothing.**

``CertificationEvidence`` defaults the three contamination verdicts to ``None``,
and ``None`` fails. A caller who skips the detector therefore cannot pass by
default — which is the same class of fix as the cost check refusing a backtest
whose net and gross series are identical.

Survivorship deserves particular attention. It is detectable only as an
*absence*, so the query it needs reaches superseded identities. A lookup over
current beliefs is structurally blind to the instruments it is looking for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.contamination import (
    ContaminationReport,
    ObservationTiming,
    PanelTiming,
    SurvivorshipReport,
    detect_look_ahead,
    detect_panel_leakage,
    detect_survivorship,
)
from core.security_master import ActionType, CorporateAction
from kernel.strategy_registry import CertificationEvidence

T0 = datetime(2024, 1, 1, tzinfo=UTC)
DAY = timedelta(days=1)


def _timing(
    obs_id: str = "o1",
    decision: datetime | None = None,
    feature: datetime | None = None,
    label: datetime | None = None,
) -> ObservationTiming:
    return ObservationTiming(
        observation_id=obs_id,
        decision_time=decision or T0,
        feature_available_at=feature or T0,
        label_available_at=label,
    )


# ══════════════════════════════════════════════════════════════════════════
# Look-ahead
# ══════════════════════════════════════════════════════════════════════════


def test_a_correctly_timed_panel_is_clean() -> None:
    report = detect_look_ahead([_timing(f"o{i}", T0 + i * DAY, T0 + i * DAY) for i in range(50)])
    assert report.clean is True
    assert report.contaminated == 0
    assert report.rate == 0.0


def test_a_feature_from_the_future_is_contamination() -> None:
    """The direct case: the input was not knowable when the decision was made."""
    report = detect_look_ahead([_timing(feature=T0 + 30 * DAY)])
    assert report.clean is False
    assert report.contaminated == 1
    assert report.findings[0].reason.startswith("feature became knowable")


def test_the_lag_is_reported_in_seconds() -> None:
    """A finding a reviewer cannot size is a finding they cannot triage."""
    report = detect_look_ahead([_timing(feature=T0 + 2 * DAY)])
    assert report.findings[0].lag == pytest.approx(2 * 86400)


def test_a_label_not_formed_at_decision_time_is_contamination() -> None:
    """A training label overlapping the test window is the subtler form."""
    report = detect_look_ahead([_timing(feature=T0, label=T0 + 5 * DAY)])
    assert report.clean is False
    assert "training window" in report.findings[0].reason


def test_exactly_at_decision_time_is_clean() -> None:
    """Knowable at the decision is usable. The boundary is inclusive."""
    assert detect_look_ahead([_timing(feature=T0, decision=T0)]).clean is True


def test_an_empty_observation_set_is_clean_and_zero_rate() -> None:
    report = detect_look_ahead([])
    assert report.clean is True
    assert report.rate == 0.0
    assert "no look-ahead in 0 observation" in report.summary()


def test_look_ahead_findings_are_capped_but_the_count_is_exact() -> None:
    """Readable output, honest count. A truncated count would understate."""
    observations = [_timing(f"o{i}", feature=T0 + DAY) for i in range(50)]
    report = detect_look_ahead(observations)
    assert report.contaminated == 50
    assert len(report.findings) == 20


def test_the_summary_names_the_first_failure() -> None:
    report = detect_look_ahead([_timing(feature=T0 + DAY)])
    assert "1 of 1" in report.summary()
    assert "not knowable" in report.summary()


def test_a_clean_report_says_so() -> None:
    assert "no look-ahead" in detect_look_ahead([_timing()]).summary()


# ══════════════════════════════════════════════════════════════════════════
# Panel composition
# ══════════════════════════════════════════════════════════════════════════


def test_a_complete_panel_is_clean() -> None:
    report = detect_panel_leakage([PanelTiming(T0, ("a", "b", "c"), ())])
    assert report.clean is True


def test_an_uneven_panel_leaks_the_future() -> None:
    """Every row can be correctly timed while the *set* of rows encodes the future.

    A cross-section assembled so that only instruments with news have data is
    the panel's composition acting as an oracle, and no per-row check sees it.
    """
    report = detect_panel_leakage([PanelTiming(T0, ("a", "b"), ("c", "d", "e"))])
    assert report.clean is False
    assert "panel composition leaks" in report.findings[0].reason


def test_panel_coverage_is_the_ready_fraction() -> None:
    panel = PanelTiming(T0, ("a", "b", "c"), ("d",))
    assert panel.coverage == pytest.approx(0.75)
    assert panel.is_complete is False


def test_an_empty_panel_has_no_coverage() -> None:
    assert PanelTiming(T0, (), ()).coverage == 0.0


# ══════════════════════════════════════════════════════════════════════════
# Survivorship
# ══════════════════════════════════════════════════════════════════════════


def _delisting(instrument_id: str, at: datetime) -> CorporateAction:
    return CorporateAction(
        action_id=f"delist-{instrument_id}",
        instrument_id=instrument_id,
        action_type=ActionType.DELISTING,
        announced_at=at - 30 * DAY,
        effective_at=at,
        source="fixture",
    )


def _symbol_change(instrument_id: str, at: datetime, new: str) -> CorporateAction:
    return CorporateAction(
        action_id=f"sym-{instrument_id}",
        instrument_id=instrument_id,
        action_type=ActionType.SYMBOL_CHANGE,
        announced_at=at - 30 * DAY,
        effective_at=at,
        new_ticker=new,
        source="fixture",
    )


def test_a_window_with_no_delistings_carries_no_signal() -> None:
    """An honest negative: nothing left, so nothing can be excluded."""
    report = detect_survivorship(["a", "b"], [], window_start=T0, window_end=T0 + 365 * DAY)
    assert report.disappeared_in_window == 0
    assert report.is_clean is True
    assert report.exclusion_rate == 0.0
    assert "no instrument delisted" in report.summary()


def test_a_delisting_absent_from_the_universe_is_survivorship_bias() -> None:
    """The signature: it died during the test, and it was never in the test."""
    report = detect_survivorship(
        ["survivor-a", "survivor-b"],
        [_delisting("corpse-1", T0 + 100 * DAY)],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.is_clean is False
    assert report.excluded_from_universe == 1
    assert report.findings[0].instrument_id == "corpse-1"
    assert "survivors" in report.summary()


def test_a_delisting_present_in_the_universe_is_not_bias() -> None:
    """The strategy held it to the end. That is the whole point of the check."""
    report = detect_survivorship(
        ["held-1", "held-2"],
        [_delisting("held-1", T0 + 100 * DAY)],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.is_clean is True


def test_a_single_omitted_bankruptcy_still_counts() -> None:
    """One omitted failure can invert a conclusion; the rate is not a threshold."""
    report = detect_survivorship(
        ["a", "b", "c", "d"],
        [_delisting("gone", T0 + DAY)],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.exclusion_rate == pytest.approx(1.0)
    assert report.is_clean is False


def test_actions_outside_the_window_are_ignored() -> None:
    """A delisting before the test says nothing about the test's survivorship."""
    report = detect_survivorship(
        ["a"],
        [_delisting("gone", T0 - 500 * DAY)],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.disappeared_in_window == 0
    assert report.is_clean is True


def test_a_split_does_not_count_as_disappearance() -> None:
    """A split changes the share count, not whether the instrument exists."""
    from decimal import Decimal

    from core.security_master import CorporateAction as CA

    split = CA(
        action_id="split-1",
        instrument_id="a",
        action_type=ActionType.SPLIT,
        announced_at=T0,
        effective_at=T0 + DAY,
        ratio_old=Decimal(1),
        ratio_new=Decimal(4),
        source="fixture",
    )
    report = detect_survivorship(
        ["a"], [split], window_start=T0, window_end=T0 + 365 * DAY
    )
    assert report.disappeared_in_window == 0


def test_a_symbol_change_joined_on_the_new_ticker_drops_the_history() -> None:
    """The subtle one: the instrument is "present" but its pre-rename series is gone.

    A backtest keyed on the post-rename ticker silently discards everything
    before the rename, which looks like a clean start rather than a truncation.
    """
    report = detect_survivorship(
        ["acme", "other"],
        [_symbol_change("acme", T0 + 100 * DAY, "ACME2")],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.is_clean is False
    assert report.findings[0].successor == "ACME2"


def test_a_symbol_change_where_both_tickers_are_tested_is_clean() -> None:
    report = detect_survivorship(
        ["acme", "ACME2"],
        [_symbol_change("acme", T0 + 100 * DAY, "ACME2")],
        window_start=T0,
        window_end=T0 + 365 * DAY,
    )
    assert report.is_clean is True


def test_findings_are_capped_but_the_count_is_exact() -> None:
    actions = [_delisting(f"gone-{i}", T0 + i * DAY) for i in range(40)]
    report = detect_survivorship(["a"], actions, window_start=T0, window_end=T0 + 365 * DAY)
    assert report.excluded_from_universe == 40
    assert len(report.findings) == 20


def test_the_exclusion_rate_is_relative_to_what_disappeared() -> None:
    """Two of four disappearing instruments missing is 50%, not 50% of the universe."""
    actions = [
        _delisting("kept-1", T0 + DAY),
        _delisting("kept-2", T0 + 2 * DAY),
        _delisting("gone-1", T0 + 3 * DAY),
        _delisting("gone-2", T0 + 4 * DAY),
    ]
    report = detect_survivorship(
        ["kept-1", "kept-2"], actions, window_start=T0, window_end=T0 + 365 * DAY
    )
    assert report.exclusion_rate == pytest.approx(0.5)
    assert report.tested_universe_size == 2


# ══════════════════════════════════════════════════════════════════════════
# A detector that never ran is not a detector that found nothing
# ══════════════════════════════════════════════════════════════════════════


def test_unrun_detectors_default_to_unknown_not_clean() -> None:
    """The property that closes the loop on this goal."""
    evidence = CertificationEvidence()
    assert evidence.look_ahead_clean is None
    assert evidence.survivorship_clean is None
    assert evidence.panel_clean is None
    assert evidence.contamination_measured is False


def test_a_partially_run_detector_set_still_fails() -> None:
    """Running two of three is not a clean bill."""
    evidence = CertificationEvidence(look_ahead_clean=True, survivorship_clean=True)
    assert evidence.contamination_measured is False


def test_evidence_from_reports_carries_the_detector_verdicts() -> None:
    look_ahead = detect_look_ahead([_timing()])
    survivorship = detect_survivorship(
        ["a"], [], window_start=T0, window_end=T0 + 365 * DAY
    )
    panel = detect_panel_leakage([PanelTiming(T0, ("a",), ())])
    evidence = CertificationEvidence.from_contamination(
        look_ahead, survivorship, panel=panel
    )
    assert evidence.contamination_measured is True


def test_evidence_from_a_dirty_report_carries_the_finding_text() -> None:
    """A certification record states the evidence, not just a conclusion."""
    look_ahead = detect_look_ahead([_timing(feature=T0 + DAY)])
    survivorship = detect_survivorship(
        ["a"], [_delisting("gone", T0 + DAY)], window_start=T0, window_end=T0 + 365 * DAY
    )
    evidence = CertificationEvidence.from_contamination(look_ahead, survivorship)
    assert evidence.contamination_measured is False
    assert "not knowable" in evidence.look_ahead_detail
    assert "survivors" in evidence.survivorship_detail


def test_omitting_a_report_is_recorded_as_not_run() -> None:
    """Not "clean", and not silently absent."""
    evidence = CertificationEvidence.from_contamination(
        detect_look_ahead([_timing()]), None
    )
    assert evidence.survivorship_detail == "not run"
    assert evidence.contamination_measured is False


# ══════════════════════════════════════════════════════════════════════════
# Report shape
# ══════════════════════════════════════════════════════════════════════════


def test_reports_serialise_for_the_audit_record() -> None:
    report = detect_look_ahead([_timing(feature=T0 + DAY)])
    payload = report.as_dict()
    assert payload["checked"] == 1
    assert payload["contaminated"] == 1
    assert payload["clean"] is False
    assert payload["findings"][0]["observation_id"] == "o1"


def test_an_empty_report_is_constructible() -> None:
    """Callers build empty reports; the type must accept it."""
    assert ContaminationReport(checked=0, contaminated=0).clean is True
    assert SurvivorshipReport(
        tested_universe_size=5, disappeared_in_window=0, excluded_from_universe=0
    ).is_clean is True
