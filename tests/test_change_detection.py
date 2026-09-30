"""Change is detected, not labelled (goals G100/G110).

The old EMA engine labelled every bar but detected nothing: a slow drift and
a sudden break produced the same slope readout. These tests pin the two
properties that make detection different from labelling — *when* the evidence
became knowable, and *how long* after the break — plus the disciplines that
keep a detector honest: no alarms before calibration, no alarms on flat data,
deterministic output, and detections consumable as point-in-time features
rather than bare labels.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from communities.c10_world.change_detection import (
    CUSUMConfig,
    OnlineCUSUM,
    segment_series,
    stable_bars,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _stamps(n: int) -> list[datetime]:
    return [T0 + timedelta(hours=i) for i in range(n)]


def _levels(first: float, second: float, n_each: int = 100) -> list[float]:
    """Deterministic two-level series. No randomness: a detector test that
    needs luck to pass is testing the seed, not the detector."""
    return [first] * n_each + [second] * n_each


# ══════════════════════════════════════════════════════════════════════════
# Online CUSUM
# ══════════════════════════════════════════════════════════════════════════


def test_a_sustained_shift_alarms_within_a_bound() -> None:
    """The headline property: a real break is found, soon, in the right
    direction, with the delay recorded rather than hidden."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=30, drift=0.5, threshold=5.0))
    values = [0.5 * (1 if i % 2 else -1) for i in range(30)] + [2.0] * 60
    alarms = detector.run(values, _stamps(len(values)))
    assert len(alarms) >= 1
    first = alarms[0]
    assert first.direction == "up"
    assert 0.5 < first.confidence <= 1.0
    assert first.delay_bars == first.detected_at - first.index
    assert first.delay_bars <= 15
    assert first.available_at == _stamps(len(values))[first.detected_at]


def test_no_alarm_fires_inside_burn_in() -> None:
    """Structural, not statistical: the first ``burn_in`` updates return None
    unconditionally. An alarm before calibration is a false-positive flood
    wearing a detector's clothes."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=30))
    seen: list[object] = []
    for i, value in enumerate([5.0] * 30):
        seen.append(detector.update(value, T0 + timedelta(hours=i)))
    assert seen == [None] * 30
    assert detector.baseline is not None


def test_a_flat_series_never_alarms() -> None:
    """No dispersion, no break to find. Raising would dress a degenerate
    input as a failure; alarming would be a false positive on silence."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=20))
    assert detector.run([3.0] * 120, _stamps(120)) == []


def test_oscillation_inside_the_drift_allowance_never_alarms() -> None:
    """The property the EMA engine lacked: movement inside the drift
    allowance (±k standard deviations) accumulates nothing, ever, while a
    step beyond it alarms. A ramp would eventually trip any threshold if run
    long enough — that is correct behaviour for a process whose mean truly
    moved — so the honest contrast is bounded oscillation versus step, which
    differ in kind rather than in patience."""
    config = CUSUMConfig(burn_in=30, drift=0.5, threshold=5.0)
    burn = [1.0 * (1 if i % 2 else -1) for i in range(30)]
    oscillation = burn + [0.4 * (1 if i % 2 else -1) for i in range(200)]
    assert OnlineCUSUM(config).run(oscillation, _stamps(len(oscillation))) == []
    step = [0.0] * 60 + [2.4] * 60
    assert len(OnlineCUSUM(config).run(step, _stamps(len(step)))) >= 1


def test_output_is_deterministic_given_inputs() -> None:
    """Same series, same alarms, every time. A detector whose output varies
    run to run cannot be certified, because the certification would be of a
    different function each time."""
    values = [0.0] * 50 + [1.5] * 50
    stamps = _stamps(100)
    first = OnlineCUSUM(CUSUMConfig()).run(values, stamps)
    second = OnlineCUSUM(CUSUMConfig()).run(values, stamps)
    assert [(a.index, a.detected_at, a.direction) for a in first] == [
        (b.index, b.detected_at, b.direction) for b in second
    ]


def test_marginal_evidence_alarms_with_spacing_then_goes_quiet() -> None:
    """After an alarm the sums reset: the next alarm needs fresh
    accumulation, not inherited momentum. A shift just strong enough to trip
    the threshold therefore alarms every few bars rather than every bar —
    that spacing is the refractory period made observable — and the return
    to the calibrated mean is silence, because a return to baseline is the
    null, not a downward break."""
    burn = [0.5 * (1 if i % 2 else -1) for i in range(30)]
    series = burn + [1.5] * 25 + [0.0] * 70
    detector = OnlineCUSUM(CUSUMConfig(burn_in=30, drift=0.5, threshold=5.0))
    alarms = detector.run(series, _stamps(len(series)))
    assert len(alarms) >= 2
    assert all(a.direction == "up" for a in alarms)
    gaps = [b.detected_at - a.detected_at for a, b in zip(alarms, alarms[1:], strict=False)]
    assert all(gap >= 2 for gap in gaps)
    assert alarms[-1].detected_at < 30 + 25 + 5


def test_sustained_alarms_point_forward_not_back() -> None:
    """A shift that stays shifted keeps alarming — each bar is new evidence
    against the frozen baseline. What must hold is ordering: no alarm may
    locate its break before a previous alarm's detection, or the detector is
    revising history it already reported."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=30, drift=0.5, threshold=5.0))
    alarms = detector.run([0.0] * 30 + [3.0] * 90, _stamps(120))
    assert len(alarms) >= 1
    for earlier, later in zip(alarms, alarms[1:], strict=False):
        assert later.index >= earlier.detected_at
    assert all(a.direction == "up" for a in alarms)


def test_non_finite_values_are_refused_not_absorbed() -> None:
    """An inf or NaN folded into a cumulative sum poisons every later bar.
    Refusing stops the chain at the source."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=5))
    for i in range(5):
        detector.update(0.0, T0 + timedelta(hours=i))
    with pytest.raises(ValueError, match="not finite"):
        detector.update(float("nan"), T0 + timedelta(hours=5))


def test_unordered_time_is_refused() -> None:
    """A break located against unordered time is mislocated: the delay and
    the available_at would describe an order that never happened."""
    detector = OnlineCUSUM(CUSUMConfig(burn_in=2))
    detector.update(0.0, T0)
    detector.update(0.0, T0 + timedelta(hours=1))
    with pytest.raises(ValueError, match="non-decreasing"):
        detector.update(0.0, T0)


# ══════════════════════════════════════════════════════════════════════════
# Offline segmentation
# ══════════════════════════════════════════════════════════════════════════


def test_a_two_level_series_segments_at_the_break() -> None:
    """Retrospective detection finds the known break within a few bars, with
    high confidence and the discovery honestly dated at the sample end."""
    values = _levels(0.0, 5.0)
    stamps = _stamps(len(values))
    points = segment_series(values, stamps)
    assert len(points) == 1
    point = points[0]
    assert abs(point.index - 100) <= 3
    assert point.direction == "up"
    assert point.confidence > 0.9
    assert point.detected_at == len(values) - 1
    assert point.available_at == stamps[-1]
    assert point.delay_bars == (len(values) - 1) - point.index


def test_a_flat_series_has_no_break_to_find() -> None:
    assert segment_series([2.0] * 100, _stamps(100)) == []


def test_a_short_series_cannot_host_a_break() -> None:
    """Fewer than two minimum segments is not a failure; it is a series with
    no room for a break. Raising would dress shortness as an error."""
    assert segment_series([0.0] * 5 + [1.0] * 5, _stamps(10)) == []


def test_misaligned_inputs_are_refused() -> None:
    """A series whose stamps do not match its values is a join error, and a
    segmentation over a misaligned join locates breaks in the wrong time."""
    with pytest.raises(ValueError, match="values but.*timestamps"):
        segment_series([0.0] * 10, _stamps(9))


def test_two_breaks_are_both_found_in_order() -> None:
    values = [0.0] * 60 + [4.0] * 60 + [1.0] * 60
    points = segment_series(values, _stamps(len(values)), max_breaks=5)
    assert len(points) == 2
    assert [p.index for p in points] == sorted(p.index for p in points)
    assert abs(points[0].index - 60) <= 4
    assert abs(points[1].index - 120) <= 4


def test_noise_does_not_segment() -> None:
    """The penalty must earn its keep: structureless jitter around one level
    is not a break. A segmenter that cuts noise manufactures regimes.

    The fixture is alternating ±0.01 — deliberately not a sine wave, which
    genuinely has non-constant mean and is rightly segmentable. White-noise
    jitter has no level to find, so every candidate split has the same SSE
    as no split and the penalty refuses them all.
    """
    values = [0.01 * (1 if i % 2 else -1) for i in range(200)]
    assert segment_series(values, _stamps(200)) == []


def test_invalid_parameters_are_refused() -> None:
    values, stamps = _levels(0.0, 1.0), _stamps(200)
    with pytest.raises(ValueError, match="max_breaks"):
        segment_series(values, stamps, max_breaks=-1)
    with pytest.raises(ValueError, match="min_segment_len"):
        segment_series(values, stamps, min_segment_len=1)


# ══════════════════════════════════════════════════════════════════════════
# stable_bars and feature conversion
# ══════════════════════════════════════════════════════════════════════════


def test_stable_bars_counts_since_the_last_break() -> None:
    values = _levels(0.0, 5.0)
    (point,) = segment_series(values, _stamps(len(values)))
    assert stable_bars([point], 150) == 150 - point.index
    assert stable_bars([point], point.index) == 0


def test_stable_bars_without_a_break_is_the_whole_history() -> None:
    """No sentinel: a sentinel would force every caller to invent the same
    convention, and callers inventing conventions is how 'stable' comes to
    mean three different things."""
    assert stable_bars([], 42) == 43


def test_stable_bars_refuses_negative_index() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        stable_bars([], -1)


def test_feed_is_quiet_until_the_detector_fires() -> None:
    """Silence is normal output: most bars change nothing, and a feed that
    emitted constantly would be a label stream wearing feature clothes."""
    from communities.c10_world.change_detection import CUSUMConfig, RegimeFeed

    feed = RegimeFeed(CUSUMConfig(burn_in=10), name="trend")
    stamps = _stamps(40)
    assert all(feed.update(0.0, stamp) == () for stamp in stamps[:10])
    assert feed.breaks == ()


def test_feed_emits_stamped_features_on_a_break() -> None:
    """The live path to the router: a break becomes observations stamped
    with when it became knowable, consumable by a RegimeCondition."""
    from communities.c10_world.change_detection import CUSUMConfig, RegimeFeed

    feed = RegimeFeed(CUSUMConfig(burn_in=10, drift=0.5, threshold=5.0), name="trend")
    stamps = _stamps(60)
    emitted: list = []
    for i, stamp in enumerate(stamps):
        emitted.extend(feed.update(0.0 if i < 30 else 3.0, stamp))
    assert len(feed.breaks) >= 1
    assert emitted
    assert {f.name for f in emitted} == {
        "trend_confidence",
        "trend_delay_bars",
        "trend_direction",
    }
    assert all(f.available_at <= stamps[-1] for f in emitted)


def test_feed_stability_counts_since_the_last_break() -> None:
    """The gate's regime input, straight from the feed."""
    from communities.c10_world.change_detection import CUSUMConfig, RegimeFeed

    feed = RegimeFeed(CUSUMConfig(burn_in=10, drift=0.5, threshold=5.0), name="trend")
    stamps = _stamps(60)
    for i, stamp in enumerate(stamps):
        feed.update(0.0 if i < 30 else 3.0, stamp)
    assert feed.stability(59) == 59 - feed.breaks[-1].index


def test_feed_requires_a_name_and_one_detector_per_stream() -> None:
    """Unnamed features are unauditable; mixed streams locate breaks in a
    series that never existed. Both refused or structured at construction."""
    from communities.c10_world.change_detection import CUSUMConfig, RegimeFeed

    with pytest.raises(ValueError, match="needs a name"):
        RegimeFeed(CUSUMConfig(), name="")
    feed = RegimeFeed(CUSUMConfig(), name="a")
    feed.reset()
    assert feed.breaks == ()
    assert feed.stability(5) == 6


def test_detections_become_point_in_time_features() -> None:
    """The anti-look-ahead property: detections convert to features stamped
    with when they became knowable, consumable by a RegimeCondition without
    ever becoming a bare label."""
    from kernel.playbook import Observation

    values = _levels(0.0, 5.0)
    stamps = _stamps(len(values))
    (point,) = segment_series(values, stamps)
    ticks = point.to_feature_observations("vol_break")
    assert {f.name for f in ticks} == {
        "vol_break_confidence",
        "vol_break_delay_bars",
        "vol_break_direction",
    }
    observation = Observation(
        as_of=stamps[-1], features={f.name: f for f in ticks}
    )
    assert all(f.available_at <= observation.as_of for f in ticks)
    with pytest.raises(ValueError, match="non-empty"):
        point.to_feature_observations("")
