"""Typed strategy specifications and artifact binding (goal G060).

``StrategyRegistry`` (strategy_registry.py) certifies *artifacts* — versions
of strategies with verdicts. This module specifies them: the parameter space
a strategy may occupy, the factors it may read at pinned versions, and the
hypothesis it tests. The binding check between a spec and an artifact is the
point: an artifact whose parameters violate its spec, whose family or
hypothesis drifted, or whose factors are unpinned is refused at bind time
with each violation named, rather than discovered after certification.

Specs are immutable once registered, for the same reason factors are: a
specification that changes under its id rewrites what every bound artifact
was certified against. A changed spec is a new version.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ParameterSpec",
    "StrategySpec",
    "StrategySpecRegistry",
    "bind_artifact",
]


class ParameterSpec(BaseModel):
    """One parameter's allowed range. Closed interval, inclusive both ends."""

    model_config = {"frozen": True}

    name: str = Field(..., min_length=1)
    kind: str = Field(..., pattern="^(float|int)$")
    minimum: float
    maximum: float

    def check(self, value: Any) -> str | None:
        """The violation, or ``None`` when the value is within spec."""
        if isinstance(value, bool):
            return f"parameter {self.name!r} is a bool, not a {self.kind}"
        if self.kind == "int":
            if not isinstance(value, int):
                return f"parameter {self.name!r} must be an int, got {type(value).__name__}"
        elif not isinstance(value, (int, float)):
            return f"parameter {self.name!r} must be numeric, got {type(value).__name__}"
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return f"parameter {self.name!r} must be finite"
        if not (self.minimum <= number <= self.maximum):
            return (
                f"parameter {self.name!r}={number:g} outside "
                f"[{self.minimum:g}, {self.maximum:g}]"
            )
        return None


class StrategySpec(BaseModel):
    """The specification a strategy artifact binds to."""

    model_config = {"frozen": True}

    strategy_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1)
    hypothesis_id: str = Field(..., min_length=1)
    factors: tuple[tuple[str, str], ...] = Field(
        default=(), description="(factor_id, version) pins; unpinned factors are refused"
    )
    parameters: tuple[ParameterSpec, ...] = ()
    dataset_ref: dict[str, str] = Field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.strategy_id}:{self.version}"

    def check_parameters(self, params: dict[str, Any]) -> list[str]:
        """Every violation in the parameter set, not just the first.

        A single boolean would send the caller fixing one bound at a time
        through repeated certification attempts; the full list lets one
        revision fix everything.
        """
        known = {spec.name: spec for spec in self.parameters}
        violations = [
            f"unknown parameter {name!r}: not in spec {self.ref}"
            for name in params
            if name not in known
        ]
        for name, spec in known.items():
            if name not in params:
                violations.append(f"missing parameter {name!r} required by spec {self.ref}")
                continue
            problem = spec.check(params[name])
            if problem is not None:
                violations.append(problem)
        return violations


class StrategySpecRegistry:
    """Specifications, versioned and immutable. Binding lives in
    :func:`bind_artifact`, which reads both registries but mutates neither."""

    def __init__(self) -> None:
        self._specs: dict[str, StrategySpec] = {}

    def register(self, spec: StrategySpec) -> StrategySpec:
        existing = self._specs.get(spec.ref)
        if existing is not None:
            if existing == spec:
                return existing
            raise ValueError(
                f"strategy spec {spec.ref} already registered with different content. "
                "Register a new version: redefining a spec rewrites what bound "
                "artifacts were certified against."
            )
        self._specs[spec.ref] = spec
        return spec

    def get(self, strategy_id: str, version: str) -> StrategySpec:
        key = f"{strategy_id}:{version}"
        spec = self._specs.get(key)
        if spec is None:
            raise KeyError(f"strategy spec not found: {key!r}")
        return spec

    def registered(self) -> tuple[str, ...]:
        return tuple(self._specs)


def bind_artifact(artifact: Any, spec: StrategySpec) -> list[str]:
    """Check an artifact against its spec. Returns violations, empty when bound.

    Reads the artifact's family, hypothesis, parameters, and dataset ref
    against the spec's. A bound artifact is one the spec describes; anything
    else is a different strategy wearing a certified id, and the violations
    name exactly how it differs.
    """
    violations: list[str] = []
    if artifact.family != spec.family:
        violations.append(
            f"family {artifact.family!r} does not match spec family {spec.family!r}"
        )
    if artifact.hypothesis_id != spec.hypothesis_id:
        violations.append(
            f"hypothesis {artifact.hypothesis_id!r} does not match spec "
            f"hypothesis {spec.hypothesis_id!r}"
        )
    violations.extend(spec.check_parameters(dict(artifact.parameters or {})))
    if spec.dataset_ref:
        artifact_ref = dict(artifact.dataset_ref or {})
        for key, expected in spec.dataset_ref.items():
            if artifact_ref.get(key) != expected:
                violations.append(
                    f"dataset ref {key!r} is {artifact_ref.get(key)!r}, "
                    f"spec requires {expected!r}"
                )
    return violations
