"""Intervals earn their coverage from held-out data (goal G110).

Split-conformal prediction earns coverage from a calibration sample the
predictor never trained on. These tests pin the guarantee and, more
importantly, the failure mode: intervals fitted on training residuals are
narrower than honest ones by construction, which is why the separation lives
in the caller's pipeline and why this suite demonstrates the collapse
empirically rather than merely documenting it.
"""

from __future__ import annotations

import math
import random

import pytest

from core.conformal import conformal_interval, conformal_quantile, coverage_of


def _residuals(n: int, scale: float, seed: int) -> list[float]:
    """Deterministic pseudo-Gaussian residuals via a seeded generator.

    Seeded, so the test is reproducible; Box-Muller, so the tails behave.
    A test that needs luck to pass is testing the seed, not the interval.
    """
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        u1 = max(rng.random(), 1e-12)
        u2 = rng.random()
        out.append(math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2) * scale)
    return out


# ══════════════════════════════════════════════════════════════════════════
# The guarantee
# ══════════════════════════════════════════════════════════════════════════


def test_empirical_coverage_holds_at_the_stated_rate() -> None:
    """The property conformal prediction exists to provide: over fresh
    exchangeable draws, the interval covers at approximately 1 − α.

    Tolerance is honest, not generous: ±0.04 at n=2000 reflects binomial
    noise around 0.90, and a tighter bound would fail good intervals on luck.
    """
    calibration = _residuals(500, 1.0, seed=11)
    interval = conformal_interval(0.0, calibration, alpha=0.10)
    fresh = _residuals(2000, 1.0, seed=12)
    coverage = coverage_of(interval, fresh)
    assert coverage == pytest.approx(0.90, abs=0.04)


def test_the_finite_sample_correction_is_present() -> None:
    """ceil((n+1)(1−α))/n, not the raw empirical quantile: without it the
    guarantee sags at small n, which is exactly when it is most needed."""
    residuals = [float(i) for i in range(1, 11)]
    # n=10, alpha=0.10: rank = ceil(11 * 0.9) = 10 -> the max, 10.0.
    assert conformal_quantile(residuals, 0.10) == pytest.approx(10.0)
    # alpha=0.50: rank = ceil(11 * 0.5) = 6 -> 6.0, not the median 5.5.
    assert conformal_quantile(residuals, 0.50) == pytest.approx(6.0)


def test_intervals_widen_with_uncertainty() -> None:
    """A wider residual distribution earns a wider interval. An interval
    method that did not respond to dispersion would be a constant wearing
    mathematics' clothes."""
    tight = conformal_interval(0.0, _residuals(300, 0.5, seed=1))
    loose = conformal_interval(0.0, _residuals(300, 2.0, seed=1))
    assert loose.width > 2.0 * tight.width


def test_the_interval_carries_its_provenance() -> None:
    """An interval without its method, n, and alpha is a pair of numbers,
    not a claim. Reproducibility requires the inputs the guarantee depends on."""
    interval = conformal_interval(1.5, _residuals(100, 1.0, seed=3), alpha=0.05)
    assert interval.n_calibration == 100
    assert interval.alpha == pytest.approx(0.05)
    assert "split-conformal" in interval.method
    assert interval.contains(1.5) is True
    assert interval.width == pytest.approx(2.0 * interval.quantile)


# ══════════════════════════════════════════════════════════════════════════
# The failure mode, demonstrated rather than documented
# ══════════════════════════════════════════════════════════════════════════


def test_training_residuals_produce_dishonest_intervals() -> None:
    """Why the split matters, empirically: residuals from data the predictor
    fit are smaller than honest ones, so their interval undercovers fresh
    data. This test is the reason the separation lives in the caller's
    pipeline — no function here can tell the two apart, so the suite shows
    the cost of confusing them."""
    honest = _residuals(500, 1.0, seed=21)
    # A predictor that memorised half its training set: training residuals
    # near zero, fresh residuals full scale.
    memorised = [r * 0.1 for r in _residuals(500, 1.0, seed=22)]
    honest_interval = conformal_interval(0.0, honest)
    dishonest_interval = conformal_interval(0.0, memorised)
    assert dishonest_interval.width < 0.5 * honest_interval.width
    fresh = _residuals(2000, 1.0, seed=23)
    assert coverage_of(dishonest_interval, fresh) < 0.5


# ══════════════════════════════════════════════════════════════════════════
# Degenerate inputs are refused
# ══════════════════════════════════════════════════════════════════════════


def test_an_empty_calibration_set_is_refused() -> None:
    """An interval from no residuals is a guess with error bars drawn on."""
    with pytest.raises(ValueError, match="at least 2 residuals"):
        conformal_quantile([], 0.10)


def test_a_single_residual_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 2 residuals"):
        conformal_quantile([0.5], 0.10)


def test_alpha_outside_unit_interval_is_refused() -> None:
    for bad in (0.0, 1.0, -0.1, 2.0):
        with pytest.raises(ValueError, match="alpha must lie"):
            conformal_quantile([0.1, 0.2, 0.3], bad)


def test_non_finite_residuals_are_refused() -> None:
    """A NaN is a failed prediction, not a large one. Folding it into a
    quantile would launder the failure into width."""
    with pytest.raises(ValueError, match="must all be finite"):
        conformal_quantile([0.1, float("nan"), 0.3], 0.10)
    with pytest.raises(ValueError, match="must all be finite"):
        conformal_quantile([0.1, float("inf"), 0.3], 0.10)


def test_a_non_finite_point_prediction_is_refused() -> None:
    """No interval centers on NaN."""
    with pytest.raises(ValueError, match="must be finite"):
        conformal_interval(float("nan"), [0.1, 0.2], 0.10)


def test_coverage_of_nothing_is_undefined() -> None:
    interval = conformal_interval(0.0, [0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="undefined"):
        coverage_of(interval, [])
