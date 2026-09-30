"""The evaluation harness behind the statistical claim gate (goal G190).

``core/claim_gate.py`` refuses a bare number; ``evaluation/harness.py`` is the
runner that earns the provenance the gate asks for. Each test below names the
defect it prevents, because a gate whose backing harness can be gamed by
dropping errors, skipping versions, or running zero cases is decoration.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.claim_gate import ClaimStatus
from evaluation.harness import (
    EmptySuiteError,
    EvalCase,
    UnpinnedVersionError,
    run_suite,
)


def _cases() -> list[EvalCase]:
    return [
        EvalCase(case_id="c1", inputs={"x": 1}, expected=2),
        EvalCase(case_id="c2", inputs={"x": 2}, expected=4),
        EvalCase(case_id="c3", inputs={"x": 3}, expected=6),
        EvalCase(case_id="c4", inputs={"x": 4}, expected=8),
    ]


def _double(inputs: dict[str, Any]) -> Any:
    return inputs["x"] * 2


def _full_context() -> dict[str, Any]:
    """Every declaration the gate requires that the harness cannot measure."""
    return {
        "time_period": "2024-01-01/2024-12-31 daily bars",
        "asset_universe": "S&P 500 constituents as of 2024-01-01",
        "regime_coverage": "bull, bear, and range subperiods",
        "out_of_sample": True,
        "max_drawdown": 3.5,
        "tail_risk": 0.02,
        "experiment_count": 3,
    }


# ------------------------------------------------------- gate integration


def test_complete_result_passes_the_gate() -> None:
    """Defect: a harness that cannot satisfy its own gate is decoration."""
    result = run_suite(
        _cases(),
        _double,
        seed=7,
        model_version="m-1",
        dataset_version="d-1",
        **_full_context(),  # type: ignore[arg-type]
    )
    assert result.passed
    gated = result.to_gate_claim()
    assert gated.status is ClaimStatus.REPORTABLE
    assert gated.missing == ()


def test_missing_provenance_is_rejected_at_the_gate() -> None:
    """Defect: undeclared period/universe/drawdown quoted as a result."""
    result = run_suite(_cases(), _double, seed=7, model_version="m-1", dataset_version="d-1")
    gated = result.to_gate_claim()
    assert gated.status is ClaimStatus.NOT_REPORTABLE
    assert "time_period" in gated.missing
    assert "asset_universe" in gated.missing
    assert "max_drawdown" in gated.missing


# ------------------------------------------------------- confidence interval


def test_every_reported_result_carries_a_named_interval() -> None:
    """Defect: a bare point estimate presented as a measurement."""
    result = run_suite(
        _cases(), _double, seed=7, model_version="m-1", dataset_version="d-1"
    )
    interval = result.confidence_interval
    assert interval.method == "wilson"
    assert interval.n == 4 and interval.k == 4
    assert interval.lo <= result.point_estimate <= interval.hi
    provenance = result.to_claim_provenance()
    assert provenance["confidence_interval"]["method"] == "wilson"


def test_interval_covers_uncertainty_on_mixed_outcomes() -> None:
    """Defect: an interval that collapses to the point estimate."""
    cases = [
        EvalCase(case_id="a", inputs={"x": 1}, expected=1),
        EvalCase(case_id="b", inputs={"x": 2}, expected=999),
    ]
    result = run_suite(
        cases,
        lambda inputs: inputs["x"],
        seed=3,
        model_version="m-1",
        dataset_version="d-1",
    )
    assert result.point_estimate == 0.5
    assert result.confidence_interval.lo < 0.5 < result.confidence_interval.hi


# ------------------------------------------------------- version pins


@pytest.mark.parametrize("model_version,dataset_version", [("", "d-1"), ("m-1", "   "), ("", "")])
def test_unpinned_versions_refuse_to_run(model_version: str, dataset_version: str) -> None:
    """Defect: a result without versions is unrepeatable but quotable."""
    with pytest.raises(UnpinnedVersionError):
        run_suite(
            _cases(),
            _double,
            seed=7,
            model_version=model_version,
            dataset_version=dataset_version,
        )


# ------------------------------------------------------- error accounting


def test_execution_errors_are_neither_passes_nor_fails() -> None:
    """Defect: errored cases silently dropped, inflating the pass rate."""
    cases = [
        EvalCase(case_id="ok1", inputs={"x": 1}, expected=2),
        EvalCase(case_id="ok2", inputs={"x": 2}, expected=4),
        EvalCase(case_id="boom", inputs={"x": 3}, expected=6),
    ]

    def flaky(inputs: dict[str, Any]) -> Any:
        if inputs["x"] == 3:
            raise RuntimeError("fixture exploded")
        return inputs["x"] * 2

    result = run_suite(cases, flaky, seed=11, model_version="m-1", dataset_version="d-1")
    assert result.n_errors == 1
    assert result.n_failed == 0
    assert result.n_executed == 2
    assert result.coverage == pytest.approx(2 / 3)
    assert result.cases[2].outcome == "error"
    assert "RuntimeError" in (result.cases[2].error or "")
    # The rate over executed cases is 1.0, yet the run must not pass:
    # coverage below the bar vetoes it.
    assert result.point_estimate == 1.0
    assert not result.coverage_ok
    assert not result.passed


def test_failed_assertions_count_separately_from_errors() -> None:
    """Defect: a wrong answer and a crashed run scored as the same thing."""
    cases = [
        EvalCase(case_id="wrong", inputs={"x": 1}, expected=999),
        EvalCase(case_id="crash", inputs={"x": 2}, expected=4),
    ]

    def subject(inputs: dict[str, Any]) -> Any:
        if inputs["x"] == 2:
            raise ValueError("nope")
        return inputs["x"]

    result = run_suite(cases, subject, seed=5, model_version="m-1", dataset_version="d-1")
    assert result.n_failed == 1
    assert result.n_errors == 1
    assert result.n_passed == 0
    assert result.point_estimate == 0.0


# ------------------------------------------------------- determinism


def test_same_seed_and_subject_give_identical_results() -> None:
    """Defect: an evaluation nobody can reproduce is an anecdote."""
    first = run_suite(_cases(), _double, seed=42, model_version="m-1", dataset_version="d-1")
    second = run_suite(_cases(), _double, seed=42, model_version="m-1", dataset_version="d-1")
    assert first == second
    assert first.execution_order == second.execution_order


# ------------------------------------------------------- empty suite


def test_empty_suite_is_refused() -> None:
    """Defect: 0/0 reported as 100%."""
    with pytest.raises(EmptySuiteError):
        run_suite([], _double, seed=1, model_version="m-1", dataset_version="d-1")


def test_total_failure_reports_zero_coverage_not_a_score() -> None:
    """Defect: a run where nothing executed quoted at face value."""
    result = run_suite(
        _cases(),
        lambda inputs: (_ for _ in ()).throw(RuntimeError("all down")),
        seed=9,
        model_version="m-1",
        dataset_version="d-1",
        min_coverage=0.5,
    )
    assert result.n_executed == 0
    assert result.coverage == 0.0
    assert not result.coverage_ok
    assert not result.passed
    assert (result.confidence_interval.lo, result.confidence_interval.hi) == (0.0, 1.0)
