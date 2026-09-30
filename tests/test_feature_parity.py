"""Feature fabric parity: offline batch matches online serving (goal G090).

The fabric's claim is that both paths call one transform, so these tests
state the observable consequences: exact agreement on integer-safe
transforms, agreement within a stated epsilon on float ones, warmup as a
named refusal rather than silent NaN, serving state that survives a restart,
and bit-for-bit recomputation from (data, code-hash, config).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.feature_store import (
    EXACT_PARITY_TOLERANCE,
    FLOAT_PARITY_TOLERANCE,
    Bar,
    CodeHashMismatch,
    FeatureConfig,
    OfflineStore,
    OnlineSnapshot,
    OnlineStore,
    WarmupRefusal,
    check_offline_online_parity,
    code_hash_for,
    warmup_bars,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(closes: list[float]) -> list[Bar]:
    return [
        Bar(close=c, available_at=T0 + timedelta(minutes=i)) for i, c in enumerate(closes)
    ]


def _float_closes(n: int = 60) -> list[float]:
    # Deterministic, non-trivial: trend plus a repeating ripple that keeps
    # extrema and smoothing honest without any randomness to seed.
    return [100.0 + i * 0.37 + (i % 7) * 0.23 - (i % 3) * 0.11 for i in range(n)]


def _int_closes(n: int = 40) -> list[float]:
    return [float(10 + ((i * 7) % 23)) for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════
# Parity: exact on integer-safe transforms, within epsilon on float ones
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("feature", ["rolling_sum", "momentum", "rolling_max", "rolling_min"])
def test_parity_exact_on_integer_safe_transforms(feature: str) -> None:
    """Comparisons and integral addition admit no rounding: epsilon is 0."""
    bars = _bars(_int_closes())
    config = FeatureConfig(feature=feature, period=5)
    report = check_offline_online_parity(
        bars,
        feature_id="f",
        version="v1",
        config=config,
        tolerance=EXACT_PARITY_TOLERANCE,
    )
    assert report.passed is True
    assert report.max_abs_diff == 0.0
    assert report.tolerance == 0.0
    assert report.n_compared == report.offline_emitted == report.online_emitted
    assert report.n_compared > 0


@pytest.mark.parametrize("feature", ["sma", "ema"])
def test_parity_within_epsilon_on_float_transforms(feature: str) -> None:
    bars = _bars(_float_closes())
    config = FeatureConfig(feature=feature, period=8)
    report = check_offline_online_parity(
        bars,
        feature_id="f",
        version="v1",
        config=config,
        tolerance=FLOAT_PARITY_TOLERANCE,
    )
    assert report.passed is True
    assert report.max_abs_diff <= FLOAT_PARITY_TOLERANCE
    assert report.n_compared == report.offline_emitted == report.online_emitted


def test_parity_report_records_its_epsilon() -> None:
    """A parity claim without its epsilon cannot be re-checked, so the report
    carries the tolerance it ran under — and a zero tolerance on a float
    transform still reports honestly rather than rounding up to pass."""
    bars = _bars(_float_closes())
    config = FeatureConfig(feature="sma", period=8)
    strict = check_offline_online_parity(
        bars, feature_id="f", version="v1", config=config, tolerance=0.0
    )
    assert strict.tolerance == 0.0
    assert strict.max_abs_diff <= FLOAT_PARITY_TOLERANCE
    loose = check_offline_online_parity(
        bars, feature_id="f", version="v1", config=config, tolerance=1e-9
    )
    assert loose.tolerance == 1e-9
    assert loose.passed is True


def test_parity_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="tolerance"):
        check_offline_online_parity(
            _bars(_int_closes()),
            feature_id="f",
            version="v1",
            config=FeatureConfig(feature="sma", period=3),
            tolerance=-1.0,
        )


# ══════════════════════════════════════════════════════════════════════════
# Warmup: named refusal, never silent NaN
# ══════════════════════════════════════════════════════════════════════════


def test_online_warmup_is_a_named_refusal() -> None:
    store = OnlineStore(
        feature_id="sma_c", version="v1", config=FeatureConfig(feature="sma", period=4)
    )
    bars = _bars([1.0, 2.0, 3.0])
    for seen, bar in enumerate(bars, start=1):
        with pytest.raises(WarmupRefusal) as exc_info:
            store.update(bar)
        refusal = exc_info.value
        assert refusal.needed == 4
        assert refusal.seen == seen
        assert "sma" in str(refusal)
    tick = store.update(_bars([4.0])[0].model_copy(update={"available_at": T0 + timedelta(minutes=3)}))
    assert tick.value == pytest.approx((1.0 + 2.0 + 3.0 + 4.0) / 4)


def test_momentum_needs_one_extra_bar() -> None:
    assert warmup_bars("momentum", 5) == 6
    assert warmup_bars("sma", 5) == 5
    store = OnlineStore(
        feature_id="m", version="v1", config=FeatureConfig(feature="momentum", period=2)
    )
    bars = _bars([10.0, 11.0])
    for bar in bars:
        with pytest.raises(WarmupRefusal):
            store.update(bar)
    tick = store.update(
        Bar(close=13.0, available_at=T0 + timedelta(minutes=2))
    )
    assert tick.value == pytest.approx(3.0)


def test_offline_warmup_positions_are_none_never_nan() -> None:
    result = OfflineStore(
        feature_id="e", version="v1", config=FeatureConfig(feature="ema", period=5)
    ).compute(_bars(_float_closes(12)))
    assert result.values[:4] == [None, None, None, None]
    assert result.values[4] is not None
    for value in result.values:
        assert value is None or value == value  # no NaN anywhere


def test_online_ticks_carry_available_at() -> None:
    bars = _bars([1.0, 2.0, 3.0, 4.0, 5.0])
    store = OnlineStore(
        feature_id="s", version="v1", config=FeatureConfig(feature="rolling_sum", period=2)
    )
    ticks = []
    for bar in bars:
        try:
            ticks.append(store.update(bar))
        except WarmupRefusal:
            continue
    assert [t.available_at for t in ticks] == [b.available_at for b in bars[1:]]
    assert [t.index for t in ticks] == [1, 2, 3, 4]


def test_online_refuses_out_of_knowable_order() -> None:
    """Serving a bar older than the last served one would hand downstream a
    sequence whose knowable times run backwards — a point-in-time join on
    that sequence is meaningless, so the store refuses the bar."""
    store = OnlineStore(
        feature_id="s", version="v1", config=FeatureConfig(feature="sma", period=1)
    )
    store.update(Bar(close=1.0, available_at=T0 + timedelta(minutes=5)))
    with pytest.raises(ValueError, match="knowable order"):
        store.update(Bar(close=2.0, available_at=T0 + timedelta(minutes=1)))


def test_bar_without_available_at_is_rejected() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Bar.model_validate({"close": 1.0})


# ══════════════════════════════════════════════════════════════════════════
# Restart: serving state survives the process
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("feature", ["sma", "ema", "momentum", "rolling_max"])
def test_online_state_round_trip_resumes_identically(feature: str) -> None:
    """Snapshot mid-stream, restore into a fresh store, and require the rest
    of the served sequence — values and knowable times — to match the
    uninterrupted run tick for tick."""
    closes = _float_closes()
    bars = _bars(closes)
    config = FeatureConfig(feature=feature, period=6)
    reference = OnlineStore(feature_id="f", version="v1", config=config)
    ref_ticks = []
    for bar in bars:
        try:
            ref_ticks.append(reference.update(bar))
        except WarmupRefusal:
            continue

    cut = 25
    interrupted = OnlineStore(feature_id="f", version="v1", config=config)
    for bar in bars[:cut]:
        try:
            interrupted.update(bar)
        except WarmupRefusal:
            continue
    payload = interrupted.snapshot().model_dump_json()
    resumed = OnlineStore.restore(OnlineSnapshot.model_validate_json(payload))
    resumed_ticks = []
    for bar in bars[cut:]:
        resumed_ticks.append(resumed.update(bar))

    # Ticks after the cut must equal the reference run's ticks at same index.
    continued = [t for t in ref_ticks if t.index >= cut]
    assert len(resumed_ticks) == len(continued) > 0
    for got, want in zip(resumed_ticks, continued, strict=True):
        assert got.index == want.index
        assert got.available_at == want.available_at
        assert got.value == want.value


def test_snapshot_is_json_and_carries_config() -> None:
    store = OnlineStore(
        feature_id="f", version="v3", config=FeatureConfig(feature="ema", period=4)
    )
    for bar in _bars([1.0, 2.0, 3.0, 4.0, 5.0]):
        try:
            store.update(bar)
        except WarmupRefusal:
            continue
    snap = OnlineSnapshot.model_validate_json(store.snapshot().model_dump_json())
    assert snap.config.feature == "ema"
    assert snap.config.period == 4
    assert snap.n_seen == 5
    assert snap.ema_state is not None


# ══════════════════════════════════════════════════════════════════════════
# Recomputation from (data, code-hash, config)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("feature", ["sma", "ema", "momentum", "rolling_sum"])
def test_recompute_reproduces_offline_bit_for_bit(feature: str) -> None:
    bars = _bars(_float_closes())
    store = OfflineStore(
        feature_id="f", version="v1", config=FeatureConfig(feature=feature, period=7)
    )
    first = store.compute(bars)
    second = store.recompute(bars, code_hash=first.code_hash)
    assert second.code_hash == first.code_hash
    assert second.values == first.values
    assert second.available_at == first.available_at


def test_recompute_refuses_a_foreign_code_hash() -> None:
    store = OfflineStore(
        feature_id="f", version="v1", config=FeatureConfig(feature="sma", period=3)
    )
    with pytest.raises(CodeHashMismatch):
        store.recompute(_bars([1.0, 2.0, 3.0, 4.0]), code_hash="deadbeef")


def test_code_hash_is_stable_and_config_scoped() -> None:
    left = code_hash_for(FeatureConfig(feature="sma", period=5))
    assert left == code_hash_for(FeatureConfig(feature="sma", period=5))
    assert left != code_hash_for(FeatureConfig(feature="sma", period=6))
    assert left != code_hash_for(FeatureConfig(feature="ema", period=5))


def test_registry_linkage_records_but_never_executes() -> None:
    """The fabric depends on the FeatureRegistry shape only: it records the
    registered computation hash for audit linkage while the arithmetic stays
    the shared transform."""
    from kernel.bootstrap import create_kernel
    from kernel.provenance import ProvenanceGraph
    from kernel.registries import FeatureRegistry

    kernel = create_kernel()
    registry = FeatureRegistry(kernel.provenance)
    assert isinstance(kernel.provenance, ProvenanceGraph)
    fv = registry.register(
        feature_id="sma_close",
        version="v1",
        definition="simple moving average over closes",
        dataset_ref={"dataset_id": "bars", "version": "v1"},
        computation_code="def compute(bars): return sma(bars, 5)",
    )
    result = OfflineStore(
        feature_id="sma_close",
        version="v1",
        config=FeatureConfig(feature="sma", period=5),
    ).compute(_bars(_float_closes(10)), feature_version=fv)
    assert result.registry_computation_hash == fv.computation_hash
    # And parity still holds for the linked computation.
    report = check_offline_online_parity(
        _bars(_float_closes()),
        feature_id="sma_close",
        version="v1",
        config=FeatureConfig(feature="sma", period=5),
        tolerance=FLOAT_PARITY_TOLERANCE,
    )
    assert report.passed is True


def test_offline_is_deterministic_across_instances() -> None:
    bars = _bars(_float_closes())
    kwargs = {"feature_id": "f", "version": "v1", "config": FeatureConfig(feature="ema", period=9)}
    first = OfflineStore(**kwargs).compute(bars)
    second = OfflineStore(**kwargs).compute(bars)
    assert first.values == second.values
    assert first.code_hash == second.code_hash


# ══════════════════════════════════════════════════════════════════════════
# The decision path performs no network I/O outside the market feed
# ══════════════════════════════════════════════════════════════════════════


def test_decision_path_modules_make_no_network_calls() -> None:
    """A feature computation that phones home is not deterministic: its
    output depends on whatever answered. Checked structurally, because the
    failure is an import appearing in a diff, and no behavioural test routes
    traffic through a module that was never supposed to call out."""
    import pathlib
    import re

    network = re.compile(
        r"\b(socket|urllib|requests|httpx|http\.client|urlopen|urlretrieve"
        r"|create_connection|getaddrinfo|WebSocket|websocket)\b"
    )
    import ast

    offenders = []
    for rel in (
        "core/feature_store.py",
        "core/temporal.py",
        "core/contamination.py",
        "kernel/playbook.py",
        "kernel/factors.py",
        "core/decision_gate.py",
        "core/conformal.py",
    ):
        text = pathlib.Path(rel).read_text(encoding="utf-8")
        # String-literal lines (docstrings, messages) are prose: they may
        # describe network absence, but only code enacts it. AST ranges tell
        # the two apart where quote-counting heuristics cannot.
        tree = ast.parse(text)
        prose_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                prose_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        hits = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if lineno in prose_lines or not line.strip() or line.strip().startswith("#"):
                continue
            if network.search(line):
                hits.append(line.strip())
        if hits:
            offenders.append((rel, hits))
    assert offenders == [], f"network I/O in the decision path: {offenders}"
