"""The slow tier proposes; it never publishes (goal G120).

The offline sweep over certified strategies and measured regimes is the slow
reasoner's whole job: per pair, either a derived size with its basis or a
named refusal. Proposals are not policies — a viable candidate still needs
bounds from a human and registration through the governed path. What the
sweep contributes is coverage: every measured regime gets an answer, and a
refusal is reviewable evidence rather than silence.

The properties that matter: viable candidates carry the same basis the
publish path would bind; unknown regime names are reported as taxonomy gaps
rather than filtered out (a measurement the proposer cannot map is a regime
nobody watches); and the sweep never invents a regime the verdict did not
measure.
"""

from __future__ import annotations

import pytest

from core.backtest import RegimeSlice
from kernel.bootstrap import create_kernel
from kernel.playbook import Regime, propose_candidates
from kernel.strategy_registry import CertificationEvidence, StrategyRegistry


@pytest.fixture()
def registry() -> StrategyRegistry:
    return StrategyRegistry(create_kernel().provenance)


def _evidence(**overrides: object) -> CertificationEvidence:
    fields: dict[str, object] = {
        "look_ahead_clean": True,
        "panel_clean": True,
        "survivorship_clean": True,
        "gross_sharpe": 2.1,
        "net_sharpe": 1.6,
        "n_trades": 180,
        "cost_bps": 6.0,
        "participation": 0.03,
        "capacity_ceiling_usd": 5_000_000.0,
        "required_notional_usd": 100_000.0,
        "stress_scenarios_run": 3,
        "worst_stress_sharpe": 0.4,
        "execution_latency_bars": 2,
        "execution_partial_fill_ratio": 0.95,
        "execution_rejected_rate": 0.001,
    }
    fields.update(overrides)
    return CertificationEvidence(**fields)  # type: ignore[arg-type]


def _register(registry: StrategyRegistry) -> None:
    registry.register(
        strategy_id="momentum-1",
        version="v1",
        hypothesis_id="hyp-1",
        family="momentum",
        dataset_ref={"dataset_id": "bars", "version": "v1"},
    )


def _verdict(registry: StrategyRegistry, regimes: dict[str, RegimeSlice]):
    _register(registry)
    return registry.build_verdict(
        "momentum-1",
        "v1",
        2.1,
        140,
        n_observations=500,
        pbo=0.10,
        evidence=_evidence(),
        regime_performance=regimes,
    )


def test_viable_regimes_propose_derived_sizes(registry: StrategyRegistry) -> None:
    """Each passing regime yields a candidate with action plus basis — the
    same derivation publishing uses, so a proposal that becomes a playbook
    changes nothing about the size."""
    verdict = _verdict(
        registry,
        {
            "trending_up": RegimeSlice("trending_up", 1.4, 300),
            "range_bound": RegimeSlice("range_bound", 0.3, 200),
        },
    )
    assert verdict.verdict == "CERTIFIED"
    candidates = propose_candidates(
        verdict=verdict, evidence=_evidence(), book_size_usd=1_000_000.0
    )
    assert len(candidates) == 2
    assert all(c.viable for c in candidates)
    assert {c.regime for c in candidates} == {Regime.TRENDING_UP, Regime.RANGE_BOUND}
    for candidate in candidates:
        assert candidate.action is not None and candidate.basis is not None
        assert candidate.basis.verify(candidate.action) is True
        assert "momentum-1" in candidate.describe()


def test_unmeasured_regimes_are_refused_with_reasons(
    registry: StrategyRegistry,
) -> None:
    """A sweep that silently dropped failing regimes would report coverage
    it does not have. Refusals carry the derivation's reason, so the review
    sees what the numbers would not support."""
    verdict = _verdict(
        registry,
        {
            "trending_up": RegimeSlice("trending_up", 1.4, 300),
            "crisis": RegimeSlice("crisis", -0.8, 120),
        },
    )
    assert verdict.verdict == "CERTIFIED_WITH_LIMITS"
    # WITH_LIMITS refuses wholesale at derive time; propose surfaces per-regime
    # outcomes only for CERTIFIED verdicts. Here the sweep still runs each
    # regime through derivation and records the shared refusal.
    candidates = propose_candidates(
        verdict=verdict, evidence=_evidence(), book_size_usd=1_000_000.0
    )
    assert len(candidates) == 2
    assert all(not c.viable for c in candidates)
    assert all("CERTIFIED_WITH_LIMITS" in c.refused_reason for c in candidates)


def test_unknown_regime_names_are_taxonomy_gaps_not_filters(
    registry: StrategyRegistry,
) -> None:
    """A measured regime the taxonomy cannot name must be reported, not
    dropped: filtering it would hide a state the strategy demonstrably
    visits."""
    verdict = _verdict(
        registry, {"melt_up": RegimeSlice("melt_up", 1.1, 150)}
    )
    (candidate,) = propose_candidates(
        verdict=verdict, evidence=_evidence(), book_size_usd=1_000_000.0
    )
    assert candidate.viable is False
    assert candidate.regime is None
    assert "not a known regime" in candidate.refused_reason


def test_no_measured_regimes_proposes_nothing(registry: StrategyRegistry) -> None:
    """A verdict with no decomposition yields no candidates rather than a
    guess. An empty sweep is information: nothing measured, nothing proposed."""
    _register(registry)
    verdict = registry.build_verdict(
        "momentum-1", "v1", 2.1, 140, n_observations=500, pbo=0.10, evidence=_evidence()
    )
    assert propose_candidates(
        verdict=verdict, evidence=_evidence(), book_size_usd=1_000_000.0
    ) == []


def test_proposals_require_a_verdict(registry: StrategyRegistry) -> None:
    """A sweep over anything else is a sweep over uncertified numbers."""
    with pytest.raises(TypeError, match="CertificationVerdict"):
        propose_candidates(
            verdict="CERTIFIED", evidence=_evidence(), book_size_usd=1_000_000.0
        )
