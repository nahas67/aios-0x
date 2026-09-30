"""The factory's artifacts are typed, versioned, and honest (goal G060).

Hypothesis to factor to feature to model to backtest, with a typed registry
for each artifact class. These tests pin the three properties that keep the
chain from lying: factors that cannot emit inside warmup or across gaps,
specs that refuse violating artifacts at bind time, and reports in which
every shipped number is declared and every undeclared figure is cut rather
than shipped.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kernel.factors import (
    FactorDefinition,
    FactorRegistry,
    compute_factor,
    effective_warmup,
)
from kernel.strategies import ParameterSpec, StrategySpec, StrategySpecRegistry, bind_artifact
from research.reporting import NumberKind, ReportedNumber, ResearchReport

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _stamps(n: int) -> list[datetime]:
    return [T0 + timedelta(days=i) for i in range(n)]


def _momentum(version: str = "v1", lookback: int = 20) -> FactorDefinition:
    return FactorDefinition(
        factor_id="momentum",
        version=version,
        family="momentum",
        description="20-day return",
        inputs=("close",),
        warmup_bars=21,
        lookback=lookback,
        formula_ref="close[i]/close[i-20]-1",
        code_hash="test-hash",
    )


# ══════════════════════════════════════════════════════════════════════════
# A factor cannot emit inside its own warmup window
# ══════════════════════════════════════════════════════════════════════════


def test_warmup_positions_are_none_not_nan() -> None:
    """The gate: no value on a bar the factor cannot justify. ``None`` marks
    the unjustifiable positions; NaN would flow downstream as a number."""
    closes = [100.0 + i for i in range(30)]
    values = compute_factor(_momentum(), closes, _stamps(30))
    assert len(values) == 30
    assert all(v is None for v in values[:20])
    assert all(v is not None for v in values[20:])
    first = values[20]
    assert first is not None
    assert first.value == pytest.approx(120.0 / 100.0 - 1.0)
    assert first.available_at == _stamps(30)[20]
    assert first.index == 20


def test_declared_warmup_can_only_raise_the_bar() -> None:
    """The intrinsic need (lookback+1) is a floor: a definition claiming a
    shorter warmup than its own arithmetic requires would certify its own
    inadequacy."""
    short = _momentum().model_copy(update={"warmup_bars": 1})
    assert effective_warmup(short) == 21
    assert effective_warmup(_momentum()) == 21


def test_a_gap_bar_poisons_every_window_containing_it() -> None:
    """No interpolation: a missing bar is a missing observation, and any
    window reaching over it emits nothing. Interpolating would fabricate the
    prices the factor claims to summarise."""
    closes: list[float | None] = [100.0 + i for i in range(30)]
    closes[25] = None
    values = compute_factor(_momentum(), closes, _stamps(30))
    assert all(v is None for v in values[:20])
    # Windows ending at bars 25..29 all contain the gap at 25.
    assert all(v is None for v in values[25:30])
    # Bars 20..24 have complete windows behind the gap.
    assert all(v is not None for v in values[20:25])


def test_misaligned_inputs_are_refused() -> None:
    """A factor over a misaligned join locates values in the wrong time."""
    with pytest.raises(ValueError, match="misaligned join"):
        compute_factor(_momentum(), [1.0, 2.0], _stamps(3))


def test_zero_base_price_emits_nothing() -> None:
    """Division by a zero base is undefined, not zero: emitting 0.0 would
    dress 'cannot compute' as 'no momentum'."""
    closes = [0.0] * 21 + [100.0] * 9
    values = compute_factor(_momentum(), closes, _stamps(30))
    assert all(v is None for v in values)


def test_zscore_against_flat_context_is_undefined() -> None:
    """No dispersion, no deviation: a z-score against a flat context is
    undefined, and emitting 0.0 would dress 'cannot measure' as 'perfectly
    average'."""
    definition = FactorDefinition(
        factor_id="z",
        version="v1",
        family="mean_reversion",
        description="z",
        warmup_bars=11,
        lookback=10,
        formula_ref="z",
    )
    values = compute_factor(definition, [5.0] * 30, _stamps(30))
    assert all(v is None for v in values)


def test_zscore_fires_on_an_outlier() -> None:
    definition = FactorDefinition(
        factor_id="z",
        version="v1",
        family="mean_reversion",
        description="z",
        warmup_bars=11,
        lookback=10,
        formula_ref="z",
    )
    closes = [100.0] * 20 + [130.0] * 10
    values = compute_factor(definition, closes, _stamps(30))
    scored = [v for v in values if v is not None]
    assert scored
    # The break bar scores high; later bars decay as the outlier joins the
    # context — the z-score measures surprise against the recent past, and a
    # sustained new level stops being surprising. Asserting all bars stay
    # extreme would mistake a level for an ever-renewing shock.
    assert scored[0].value > 2.0


def test_realized_vol_of_a_flat_series_is_zero() -> None:
    """Zero dispersion here IS defined (no movement is a measurement), unlike
    the z-score case: the distinction is whether the quantity needs
    dispersion to mean anything."""
    definition = FactorDefinition(
        factor_id="vol",
        version="v1",
        family="volatility",
        description="vol",
        warmup_bars=11,
        lookback=10,
        formula_ref="stdev",
    )
    values = compute_factor(definition, [100.0] * 30, _stamps(30))
    scored = [v for v in values if v is not None]
    assert scored
    assert all(v.value == pytest.approx(0.0) for v in scored)


def test_unknown_family_is_refused() -> None:
    definition = FactorDefinition(
        factor_id="x",
        version="v1",
        family="astrology",
        description="x",
        formula_ref="x",
    )
    with pytest.raises(ValueError, match="not served by this fabric"):
        compute_factor(definition, [1.0] * 30, _stamps(30))


# ══════════════════════════════════════════════════════════════════════════
# Factors are immutable once registered
# ══════════════════════════════════════════════════════════════════════════


def test_reregistering_identical_content_is_a_no_op() -> None:
    registry = FactorRegistry()
    first = registry.register(_momentum())
    assert registry.register(_momentum()) is first


def test_redefining_a_registered_factor_is_refused() -> None:
    """A changed factor is a new version: redefining a pinned factor
    rewrites what every pinned backtest computed."""
    registry = FactorRegistry()
    registry.register(_momentum())
    with pytest.raises(ValueError, match="new version"):
        registry.register(_momentum().model_copy(update={"lookback": 50}))


def test_unknown_factor_lookup_fails() -> None:
    with pytest.raises(KeyError, match="factor not found"):
        FactorRegistry().get("nope", "v1")


def test_registry_compute_resolves_then_computes() -> None:
    registry = FactorRegistry()
    registry.register(_momentum())
    values = registry.compute("momentum", "v1", [100.0 + i for i in range(30)], _stamps(30))
    assert sum(v is not None for v in values) == 10


def test_factor_values_carry_content_keys() -> None:
    """Same computation, same key: pins are checkable without recomputation."""
    registry = FactorRegistry()
    registry.register(_momentum())
    first = registry.compute("momentum", "v1", [100.0 + i for i in range(30)], _stamps(30))
    second = registry.compute("momentum", "v1", [100.0 + i for i in range(30)], _stamps(30))
    keys = lambda vs: [v.content_key() for v in vs if v is not None]  # noqa: E731
    assert keys(first) == keys(second)


# ══════════════════════════════════════════════════════════════════════════
# Specs bind artifacts, or refuse them with names
# ══════════════════════════════════════════════════════════════════════════


def _spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="momentum-1",
        version="v1",
        family="momentum",
        hypothesis_id="hyp-1",
        factors=(("momentum", "v1"),),
        parameters=(
            ParameterSpec(name="lookback", kind="int", minimum=5, maximum=100),
            ParameterSpec(name="threshold", kind="float", minimum=0.0, maximum=1.0),
        ),
        dataset_ref={"dataset_id": "bars", "version": "v1"},
    )


def _artifact(**overrides) -> object:
    from types import SimpleNamespace

    params: dict[str, object] = {"lookback": 20, "threshold": 0.3}
    params.update(overrides.pop("parameters", {}))
    return SimpleNamespace(
        family=overrides.pop("family", "momentum"),
        hypothesis_id=overrides.pop("hypothesis_id", "hyp-1"),
        parameters=params,
        dataset_ref=overrides.pop("dataset_ref", {"dataset_id": "bars", "version": "v1"}),
    )


def test_a_matching_artifact_binds_clean() -> None:
    assert bind_artifact(_artifact(), _spec()) == []


def test_each_violation_is_named() -> None:
    """Not just the first: one revision should fix everything, not play
    whack-a-mole through repeated certification attempts."""
    violations = bind_artifact(
        _artifact(
            family="mean_reversion",
            hypothesis_id="hyp-2",
            parameters={"lookback": 500, "threshold": 0.3, "extra": 1},
            dataset_ref={"dataset_id": "bars", "version": "v2"},
        ),
        _spec(),
    )
    assert any("family" in v for v in violations)
    assert any("hypothesis" in v for v in violations)
    assert any("lookback" in v and "outside" in v for v in violations)
    assert any("unknown parameter" in v for v in violations)
    assert any("dataset ref" in v for v in violations)


def test_a_bool_is_not_an_int() -> None:
    """Python's bool subclasses int; a spec that accepted True as lookback
    1 would certify nonsense parameters."""
    assert bind_artifact(_artifact(parameters={"lookback": True, "threshold": 0.3}), _spec()) != []


def test_non_finite_parameters_are_refused() -> None:
    assert bind_artifact(
        _artifact(parameters={"lookback": 20, "threshold": float("nan")}), _spec()
    ) != []


def test_missing_parameters_are_named() -> None:
    from types import SimpleNamespace

    partial = SimpleNamespace(
        family="momentum",
        hypothesis_id="hyp-1",
        parameters={"lookback": 20},
        dataset_ref={"dataset_id": "bars", "version": "v1"},
    )
    violations = bind_artifact(partial, _spec())
    assert any("missing parameter" in v and "threshold" in v for v in violations)


def test_spec_reregistration_rules() -> None:
    registry = StrategySpecRegistry()
    spec = _spec()
    assert registry.register(spec) is spec
    assert registry.register(_spec()) is spec
    with pytest.raises(ValueError, match="new version"):
        registry.register(spec.model_copy(update={"family": "other"}))
    with pytest.raises(KeyError, match="not found"):
        registry.get("nope", "v1")
    assert registry.registered() == ("momentum-1:v1",)


# ══════════════════════════════════════════════════════════════════════════
# Every shipped number is declared; the rest is cut
# ══════════════════════════════════════════════════════════════════════════


def test_declared_numbers_ship_with_kind_and_source() -> None:
    report = ResearchReport(title="t")
    report.add(ReportedNumber("sharpe", 1.8, NumberKind.DERIVED, "backtest v3"))
    report.add(ReportedNumber("n", 240.0, NumberKind.COUNTED, "trial log"))
    rendered = report.render()
    assert rendered["counts"] == {"shipped": 2, "cut": 0}
    assert rendered["numbers"][0]["kind"] == "derived"


def test_undeclared_figures_are_cut_not_shipped() -> None:
    """The gate: a figure the report cannot stand behind never reaches the
    output, and the output says what was cut. Cutting is the default, not a
    review step."""
    report = ResearchReport(title="t")
    report.add(ReportedNumber("sharpe", 1.8, NumberKind.DERIVED, "backtest v3"))
    report.add_raw("whisper_number", 9.9, reason="no source yet")
    rendered = report.render()
    assert rendered["counts"] == {"shipped": 1, "cut": 1}
    assert rendered["cut"] == ["whisper_number"]
    assert all(n["label"] != "whisper_number" for n in rendered["numbers"])


def test_a_number_without_a_source_is_refused() -> None:
    """A declaration without somewhere to check it is decoration."""
    with pytest.raises(ValueError, match="no source"):
        ReportedNumber("x", 1.0, NumberKind.OBSERVED, "  ")


def test_an_unnamed_number_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a label"):
        ReportedNumber(" ", 1.0, NumberKind.COUNTED, "log")


def test_all_five_kinds_are_shippable() -> None:
    report = ResearchReport(title="t")
    for kind in NumberKind:
        report.add(ReportedNumber(kind.value, 1.0, kind, "test"))
    assert report.render()["counts"] == {"shipped": 5, "cut": 0}
