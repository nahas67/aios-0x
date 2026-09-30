"""Deterministic evaluation harness behind the statistical claim gate.

``core/claim_gate.py`` refuses to present a performance figure without its
provenance (definition, N, coverage, interval, versions, ...). This module
produces those figures honestly: it runs a suite of cases against a subject
callable, counts passes, failures, and execution errors as three separate
outcomes, and attaches a confidence interval to every reported result.

Three accounting rules carry the design, each aimed at one way of inflating
a pass rate:

* an execution error is not a pass and not a fail. It is recorded with its
  message, excluded from the pass-rate denominator, and counted against
  coverage. Dropping errored cases silently is the exact fraud the gate
  exists to prevent, so the runner has no code path that does it.
* coverage is the fraction of the suite that executed to an assertion.
  A ``min_coverage`` bar (1.0 by default: any error fails it) decides
  whether the run as a whole is usable, separately from the score bar.
* versions are pins, not labels. The runner refuses to execute without a
  non-blank model and dataset version, because a result that cannot name
  what produced it and what it ran on is unrepeatable.

The confidence interval is a Wilson score interval whose critical value
comes from :func:`core.quant_statistics.normal_ppf` (method recorded as
``"wilson"`` in the output). No quantile logic is reimplemented here.

Determinism: the execution order is shuffled with ``random.Random(seed)``
and the seed is stored on the result, so the same seed and subject always
yield an identical result. Subjects that need randomness of their own must
seed it themselves; the harness fixes traversal, not callee internals.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.claim_gate import ClaimGateResult, gate_claim
from core.quant_statistics import normal_ppf

__all__ = [
    "CaseResult",
    "ConfidenceInterval",
    "EmptySuiteError",
    "EvalCase",
    "EvaluationResult",
    "SubjectFn",
    "UnpinnedVersionError",
    "predicate_equals",
    "run_suite",
]

#: The subject under test: maps a case's inputs to its actual output.
#: A one-argument callable, so any pure function qualifies.
SubjectFn = Callable[[dict[str, Any]], Any]

#: Decides whether an actual output satisfies the expected one.
PredicateFn = Callable[[Any, Any], bool]

#: Name recorded on every interval this module emits.
CI_METHOD = "wilson"


class EmptySuiteError(ValueError):
    """The suite had no cases. 0/0 is not 100%."""


class UnpinnedVersionError(ValueError):
    """The run named no model or no dataset version. Unrepeatable, refused."""


def predicate_equals(actual: Any, expected: Any) -> bool:
    """Default comparator: plain equality."""
    return bool(actual == expected)


class EvalCase(BaseModel):
    """One evaluation case: inputs, the expected output, and its economics."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: Any = None
    weight: float = Field(default=1.0, ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)


CaseOutcome = Literal["pass", "fail", "error"]


class CaseResult(BaseModel):
    """The recorded outcome of one case. Every suite case yields exactly one."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., min_length=1)
    outcome: CaseOutcome
    actual: Any = None
    expected: Any = None
    weight: float = Field(default=1.0, ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    error: str | None = None

    @property
    def executed(self) -> bool:
        """True when the case ran to an assertion (pass or fail, not error)."""
        return self.outcome in ("pass", "fail")

    @property
    def passed(self) -> bool:
        return self.outcome == "pass"


class ConfidenceInterval(BaseModel):
    """A two-sided interval for the case-level pass rate, always present."""

    model_config = ConfigDict(frozen=True)

    method: str = Field(default=CI_METHOD, min_length=1)
    level: float = Field(default=0.95, gt=0.0, lt=1.0)
    lo: float = Field(default=0.0, ge=0.0, le=1.0)
    hi: float = Field(default=1.0, ge=0.0, le=1.0)
    n: int = Field(default=0, ge=0)
    k: int = Field(default=0, ge=0)


def wilson_interval(k: int, n: int, level: float = 0.95) -> ConfidenceInterval:
    """Wilson score interval for k passes in n executed cases.

    The critical value comes from :func:`core.quant_statistics.normal_ppf`.
    With no executed cases there is no information, so the interval is the
    whole unit range rather than a degenerate point.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1); got {level}")
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n; got k={k} n={n}")
    if n == 0:
        return ConfidenceInterval(method=CI_METHOD, level=level, lo=0.0, hi=1.0, n=0, k=0)
    z = normal_ppf(1.0 - (1.0 - level) / 2.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return ConfidenceInterval(
        method=CI_METHOD,
        level=level,
        lo=max(0.0, center - half),
        hi=min(1.0, center + half),
        n=n,
        k=k,
    )


class EvaluationResult(BaseModel):
    """Aggregate outcome of one suite run, plus everything the gate asks for."""

    model_config = ConfigDict(frozen=True)

    suite_name: str = Field(..., min_length=1)
    metric_definition: str = Field(..., min_length=1)
    seed: int
    model_version: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    n_total: int = Field(ge=1)
    n_executed: int = Field(ge=0)
    n_passed: int = Field(ge=0)
    n_failed: int = Field(ge=0)
    n_errors: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    coverage_ok: bool
    point_estimate: float = Field(ge=0.0, le=1.0)
    confidence_interval: ConfidenceInterval
    total_cost_usd: float = Field(ge=0.0)
    experiment_count: int = Field(ge=1)
    time_period: str | None = None
    asset_universe: str | None = None
    regime_coverage: str | None = None
    out_of_sample: bool = False
    max_drawdown: float | None = None
    tail_risk: float | None = None
    passed: bool
    cases: list[CaseResult] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)

    @field_validator("model_version", "dataset_version")
    @classmethod
    def _versions_must_be_pinned(cls, value: str) -> str:
        if not value.strip():
            raise UnpinnedVersionError("model and dataset versions must be non-blank pins")
        return value

    def to_claim_provenance(self) -> dict[str, Any]:
        """Map this result onto the gate's fourteen required fields.

        Fields the harness cannot measure (period, universe, regime split,
        drawdown, tail risk) are emitted as ``None`` when undeclared, so the
        gate names them as gaps instead of the harness inventing them.
        """
        return {
            "metric_definition": self.metric_definition,
            "accepted_n": self.n_executed,
            "coverage": self.coverage,
            "time_period": self.time_period,
            "asset_universe": self.asset_universe,
            "regime_coverage": self.regime_coverage,
            "net_of_cost": {
                "point_estimate_gross": self.point_estimate,
                "total_cost_usd": self.total_cost_usd,
                "cost_disclosed": True,
            },
            "out_of_sample": self.out_of_sample,
            "confidence_interval": {
                "method": self.confidence_interval.method,
                "level": self.confidence_interval.level,
                "lo": self.confidence_interval.lo,
                "hi": self.confidence_interval.hi,
                "n": self.confidence_interval.n,
                "k": self.confidence_interval.k,
            },
            "max_drawdown": self.max_drawdown,
            "tail_risk": self.tail_risk,
            "experiment_count": self.experiment_count,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
        }

    def to_gate_claim(self) -> ClaimGateResult:
        """Gate the point estimate with this result's own provenance."""
        return gate_claim(self.metric_definition, self.point_estimate, **self.to_claim_provenance())


def _require_pin(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UnpinnedVersionError(
            f"{name} must be a non-blank version pin; got {value!r}. "
            "A result without versions is unrepeatable."
        )
    return value


def run_suite(
    cases: Sequence[EvalCase],
    subject: SubjectFn,
    *,
    seed: int,
    model_version: str,
    dataset_version: str,
    suite_name: str = "suite",
    metric_definition: str | None = None,
    predicate: PredicateFn | None = None,
    pass_threshold: float = 1.0,
    min_coverage: float = 1.0,
    ci_level: float = 0.95,
    experiment_count: int = 1,
    time_period: str | None = None,
    asset_universe: str | None = None,
    regime_coverage: str | None = None,
    out_of_sample: bool = False,
    max_drawdown: float | None = None,
    tail_risk: float | None = None,
) -> EvaluationResult:
    """Run every case against ``subject`` and aggregate the outcome.

    Args:
        cases: The suite. Must be non-empty; every entry appears exactly
            once in the result, including cases that raise.
        subject: Maps a case's inputs to its actual output. An exception is
            recorded as an ``error`` outcome, never raised and never dropped.
        seed: Fixes the execution order. Same seed plus same subject gives
            an identical result.
        model_version / dataset_version: Required pins; blank refuses to run.
        predicate: Pass/fail comparator; defaults to equality. A comparator
            that raises turns that case into an error, not a pass.
        pass_threshold: Minimum weighted pass rate for ``passed``.
        min_coverage: Minimum executed fraction for ``coverage_ok``.
            Defaults to 1.0: any execution error fails the run.
        ci_level: Two-sided level for the Wilson interval.
        experiment_count: How many experiment runs this result aggregates.
            Repeating selection across unreported runs without raising this
            count is the bias the deflated Sharpe ratio corrects for.
        time_period / asset_universe / regime_coverage / max_drawdown /
            tail_risk: Caller declarations the harness cannot measure. Left
            unset, the gate reports them missing rather than assumed.
    """
    if len(cases) == 0:
        raise EmptySuiteError("refusing to run an empty suite: 0/0 is not 100%")
    _require_pin("model_version", model_version)
    _require_pin("dataset_version", dataset_version)
    if not 0.0 <= pass_threshold <= 1.0:
        raise ValueError(f"pass_threshold must be in [0, 1]; got {pass_threshold}")
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError(f"min_coverage must be in [0, 1]; got {min_coverage}")
    if not 0.0 < ci_level < 1.0:
        raise ValueError(f"ci_level must be in (0, 1); got {ci_level}")
    if experiment_count < 1:
        raise ValueError(f"experiment_count must be at least 1; got {experiment_count}")

    check: PredicateFn = predicate if predicate is not None else predicate_equals
    order = list(cases)
    random.Random(seed).shuffle(order)

    results: list[CaseResult] = []
    for case in order:
        try:
            actual = subject(dict(case.inputs))
            outcome: CaseOutcome = "pass" if bool(check(actual, case.expected)) else "fail"
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    outcome=outcome,
                    actual=actual,
                    expected=case.expected,
                    weight=case.weight,
                    cost_usd=case.cost_usd,
                )
            )
        except Exception as exc:  # noqa: BLE001 - recorded per case, never raised
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    outcome="error",
                    actual=None,
                    expected=case.expected,
                    weight=case.weight,
                    cost_usd=case.cost_usd,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    by_id = {result.case_id: result for result in results}
    ordered = [by_id[case.case_id] for case in cases]
    executed = [result for result in ordered if result.executed]
    n_passed = sum(1 for result in executed if result.outcome == "pass")
    n_failed = sum(1 for result in executed if result.outcome == "fail")
    n_errors = sum(1 for result in ordered if result.outcome == "error")
    n_total = len(cases)
    n_executed = len(executed)
    coverage = n_executed / n_total if n_total else 0.0

    scored_weight = sum(result.weight for result in executed if result.outcome == "pass")
    total_weight = sum(result.weight for result in executed)
    point = scored_weight / total_weight if total_weight > 0.0 else 0.0

    interval = wilson_interval(n_passed, n_executed, ci_level)
    total_cost = round(sum(result.cost_usd for result in ordered if result.executed), 8)
    coverage_ok = coverage >= min_coverage
    passed = point >= pass_threshold and coverage_ok

    return EvaluationResult(
        suite_name=suite_name,
        metric_definition=metric_definition or f"weighted pass rate over suite {suite_name}",
        seed=seed,
        model_version=model_version,
        dataset_version=dataset_version,
        n_total=n_total,
        n_executed=n_executed,
        n_passed=n_passed,
        n_failed=n_failed,
        n_errors=n_errors,
        coverage=round(coverage, 6),
        coverage_ok=coverage_ok,
        point_estimate=round(point, 6),
        confidence_interval=interval,
        total_cost_usd=total_cost,
        experiment_count=experiment_count,
        time_period=time_period,
        asset_universe=asset_universe,
        regime_coverage=regime_coverage,
        out_of_sample=out_of_sample,
        max_drawdown=max_drawdown,
        tail_risk=tail_risk,
        passed=passed,
        cases=ordered,
        execution_order=[case.case_id for case in order],
    )


def cases_from_mappings(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_key: str = "expected",
    inputs_key: str | None = None,
) -> list[EvalCase]:
    """Build suite cases from plain row mappings (e.g. loaded golden files).

    Each row needs a ``case_id``; the expected value is read from
    ``expected_key`` and the inputs are either the nested mapping at
    ``inputs_key`` or all remaining keys. ``weight`` and ``cost_usd`` ride
    along when present, defaulting otherwise.
    """
    built: list[EvalCase] = []
    for row in rows:
        data = dict(row)
        try:
            case_id = str(data.pop("case_id"))
        except KeyError as exc:
            raise ValueError(f"suite row without a case_id: {dict(row)!r}") from exc
        if inputs_key is not None:
            raw_inputs = data.pop(inputs_key, {})
            if not isinstance(raw_inputs, Mapping):
                raise ValueError(f"case {case_id!r}: inputs must be a mapping")
            inputs = dict(raw_inputs)
        else:
            inputs = {
                key: value
                for key, value in data.items()
                if key not in (expected_key, "weight", "cost_usd")
            }
        expected = data.pop(expected_key, None)
        built.append(
            EvalCase(
                case_id=case_id,
                inputs=inputs,
                expected=expected,
                weight=float(data.pop("weight", 1.0)),
                cost_usd=float(data.pop("cost_usd", 0.0)),
            )
        )
    return built
