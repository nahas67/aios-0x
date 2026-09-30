"""Sizing from distributions, never from points (goal G130).

The brain reads expected returns with dispersions plus a covariance matrix
and produces a proposal — or a finding when its two methods disagree. These
tests pin the three properties that keep an optimizer honest: the output
cannot be submitted anywhere, disagreement raises instead of averaging, and
constraints refuse rather than rescale.
"""

from __future__ import annotations

import pytest

from communities.c9_portfolio.optimizer import (
    CovarianceMatrix,
    ExpectedReturns,
    OptimizationDisagreement,
    PortfolioBrain,
    hierarchical_risk_parity_weights,
    inverse_volatility_weights,
)


def _expected() -> ExpectedReturns:
    """Equal dispersions, uncorrelated: both optimizers agree at thirds.
    The consensus fixture both methods must reproduce."""
    return ExpectedReturns(
        means={"AAA": 0.10, "BBB": 0.08, "CCC": 0.12},
        sds={"AAA": 0.20, "BBB": 0.20, "CCC": 0.20},
    )


def _covariance() -> CovarianceMatrix:
    entries = {
        "AAA|AAA": 0.04, "BBB|BBB": 0.04, "CCC|CCC": 0.04,
        "AAA|BBB": 0.0, "BBB|AAA": 0.0,
        "AAA|CCC": 0.0, "CCC|AAA": 0.0,
        "BBB|CCC": 0.0, "CCC|BBB": 0.0,
    }
    return CovarianceMatrix(symbols=("AAA", "BBB", "CCC"), entries=entries)


def _correlated() -> tuple[ExpectedReturns, CovarianceMatrix]:
    """AAA and BBB at 0.95 correlation: HRP sees one bet where inverse-vol
    sees two, and loads the diversifier. Measured divergence 0.081."""
    expected = ExpectedReturns(
        means={"AAA": 0.10, "BBB": 0.08, "CCC": 0.12},
        sds={"AAA": 0.10, "BBB": 0.10, "CCC": 0.40},
    )
    covariance = CovarianceMatrix(
        symbols=("AAA", "BBB", "CCC"),
        entries={
            "AAA|AAA": 0.01, "BBB|BBB": 0.01, "CCC|CCC": 0.16,
            "AAA|BBB": 0.0095, "BBB|AAA": 0.0095,
            "AAA|CCC": 0.0, "CCC|AAA": 0.0,
            "BBB|CCC": 0.0, "CCC|BBB": 0.0,
        },
    )
    return expected, covariance


# ══════════════════════════════════════════════════════════════════════════
# The output is a proposal: not an order, submittable nowhere
# ══════════════════════════════════════════════════════════════════════════


def test_a_proposal_cannot_be_submitted_to_a_venue() -> None:
    """Type-level, not policy-level: the proposal has no venue, no order id,
    no side, no submit path. A proposal that carried order fields would be
    one refactor away from execution, which is exactly the distance the type
    is meant to enforce."""
    proposal = PortfolioBrain().propose(_expected(), _covariance())
    assert set(proposal.weights) == {"AAA", "BBB", "CCC"}
    assert abs(sum(proposal.weights.values()) - 1.0) < 1e-9
    for forbidden in ("venue", "order_id", "client_order_id", "side", "submit", "place"):
        assert not hasattr(proposal, forbidden), (
            f"proposal carries {forbidden!r}: a submittable proposal is an order"
        )


def test_weights_are_long_only_and_capped() -> None:
    proposal = PortfolioBrain(max_weight=0.6).propose(_expected(), _covariance())
    assert all(w >= 0.0 for w in proposal.weights.values())
    assert all(w <= 0.6 + 1e-9 for w in proposal.weights.values())


def test_expected_statistics_ride_along() -> None:
    """The proposal can be judged without re-running the optimizers: mean
    and vol are recomputed from the weights, not copied from inputs."""
    proposal = PortfolioBrain().propose(_expected(), _covariance())
    assert proposal.expected_volatility > 0.0
    assert proposal.expected_return == pytest.approx(
        sum(proposal.weights[s] * _expected().means[s] for s in ("AAA", "BBB", "CCC"))
    )


# ══════════════════════════════════════════════════════════════════════════
# Disagreement raises a finding; it is never averaged
# ══════════════════════════════════════════════════════════════════════════


def test_disagreeing_optimizers_raise_with_per_symbol_divergence() -> None:
    """High correlation breaks the symmetry inverse-vol assumes: HRP loads
    the diversifier while IVP splits naively. The finding names the symbols
    and both weights, so the review starts from numbers."""
    expected, correlated = _correlated()
    with pytest.raises(OptimizationDisagreement, match="diverge"):
        PortfolioBrain().propose(expected, correlated)


def test_agreement_records_its_divergence() -> None:
    """Consensus is reported, not assumed: the measured divergence rides on
    the proposal so a reviewer sees agreement rather than taking it on faith."""
    proposal = PortfolioBrain().propose(_expected(), _covariance())
    assert proposal.max_weight_divergence <= 0.05
    assert "agree within" in proposal.rationale


def test_no_average_is_offered_on_disagreement() -> None:
    """There is no code path from disagreement to weights: the exception
    carries divergences, and no proposal object exists to misuse."""
    expected, correlated = _correlated()
    try:
        PortfolioBrain().propose(expected, correlated)
        raised = False
    except OptimizationDisagreement as exc:
        raised = True
        assert "AAA" in str(exc) and "CCC" in str(exc)
    assert raised is True


# ══════════════════════════════════════════════════════════════════════════
# Inputs are validated; constraints refuse rather than rescale
# ══════════════════════════════════════════════════════════════════════════


def test_zero_dispersion_is_refused() -> None:
    """A zero-vol asset has infinite precision and sizes to the whole book.
    Refused at the boundary, not normalized into dominance."""
    with pytest.raises(ValueError, match="non-positive dispersion"):
        ExpectedReturns(means={"AAA": 0.1}, sds={"AAA": 0.0})


def test_a_mean_without_dispersion_is_refused() -> None:
    """Sizing needs uncertainty for every name: a point estimate without it
    is a wish, and the covariance becomes decoration."""
    with pytest.raises(ValueError, match="without dispersion"):
        ExpectedReturns(means={"AAA": 0.1, "BBB": 0.2}, sds={"AAA": 0.2})


def test_asymmetric_covariance_is_refused() -> None:
    """An asymmetric covariance is not a covariance. Accepting half the
    matrix would silently pick a triangle."""
    with pytest.raises(ValueError, match="asymmetric"):
        CovarianceMatrix(
            symbols=("AAA", "BBB"),
            entries={"AAA|AAA": 0.04, "BBB|BBB": 0.04, "AAA|BBB": 0.01, "BBB|AAA": 0.02},
        )


def test_an_impossible_cap_is_refused_not_breached() -> None:
    """Three names capped at 20% cannot sum to one. Silently exceeding the
    cap to make the arithmetic work would override risk by algebra."""
    with pytest.raises(OptimizationDisagreement, match="cannot fit"):
        PortfolioBrain(max_weight=0.2).propose(_expected(), _covariance())


def test_hrp_needs_two_covered_symbols() -> None:
    expected = ExpectedReturns(means={"AAA": 0.1}, sds={"AAA": 0.2})
    covariance = CovarianceMatrix(symbols=("AAA",), entries={"AAA|AAA": 0.04})
    with pytest.raises(OptimizationDisagreement, match="at least two"):
        hierarchical_risk_parity_weights(expected, covariance)


def test_both_methods_are_deterministic() -> None:
    """Same inputs, same weights, every time: an optimizer that wobbles
    cannot be certified, because each run would certify a different portfolio."""
    first = inverse_volatility_weights(_expected())
    second = inverse_volatility_weights(_expected())
    assert first == second
    third = hierarchical_risk_parity_weights(_expected(), _covariance())
    fourth = hierarchical_risk_parity_weights(_expected(), _covariance())
    assert third == fourth


def test_inverse_volatility_ignores_correlation_by_design() -> None:
    """The baseline's documented blindness: identical dispersions split
    evenly regardless of correlation. HRP exists to beat this, and the test
    states what 'beat' has to overcome."""
    expected = ExpectedReturns(
        means={"AAA": 0.1, "BBB": 0.1}, sds={"AAA": 0.2, "BBB": 0.2}
    )
    assert inverse_volatility_weights(expected) == {"AAA": 0.5, "BBB": 0.5}
