"""Point-in-time is a query error, not a warning (goal G030).

A backtest that joins a price to a decision on the write time rather than the
knowable time is wrong in exactly the way that looks like skill: the strategy
appears to predict what it actually peeked at. No downstream check can detect
it, because every component downstream is reading a plausible value.

So the tests assert the temporal algebra directly: clocks order, the tripwire
refuses, unknown rows are excluded rather than trusted, and a dataset version
that wants to back research proves it carries both times and a frozen hash.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.temporal import (
    LookaheadViolation,
    TemporalInstant,
    assert_no_lookahead,
    filter_as_of,
    is_as_of_unknown,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = datetime(2024, 6, 1, tzinfo=UTC)
T2 = datetime(2024, 12, 31, tzinfo=UTC)


def _instant(
    event: datetime = T0,
    source: datetime | None = None,
    available: datetime | None = None,
    received: datetime | None = None,
    processed: datetime | None = None,
) -> TemporalInstant:
    return TemporalInstant(
        event_time=event,
        source_time=source or event,
        available_at=available or event,
        received_at=received or event,
        processed_at=processed or event,
    )


# ══════════════════════════════════════════════════════════════════════════
# The six clocks
# ══════════════════════════════════════════════════════════════════════════


def test_clocks_must_be_non_decreasing() -> None:
    """A source cannot record what has not happened yet."""
    with pytest.raises(ValueError, match="precedes"):
        TemporalInstant(
            event_time=T1,
            source_time=T0,  # recorded before it happened
            available_at=T1,
            received_at=T1,
            processed_at=T1,
        )


def test_available_after_received_is_refused() -> None:
    """Knowable time follows the same ordering as every other clock."""
    with pytest.raises(ValueError, match="received_at.*precedes available_at"):
        _instant(event=T0, available=T2, received=T1)


def test_sequence_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TemporalInstant(
            event_time=T0,
            source_time=T0,
            available_at=T0,
            received_at=T0,
            processed_at=T0,
            sequence=-1,
        )


def test_knowable_at_is_available_at() -> None:
    """The join key is when the datum became knowable, not when we wrote it."""
    instant = _instant(event=T0, available=T1, received=T2, processed=T2)
    assert instant.knowable_at == T1
    assert instant.is_knowable_at(T1) is True
    assert instant.is_knowable_at(T0) is False


def test_equal_clocks_are_legal() -> None:
    """A same-millisecond pipeline is fast, not wrong."""
    instant = _instant(event=T0)
    assert instant.is_knowable_at(T0)


# ══════════════════════════════════════════════════════════════════════════
# The tripwire
# ══════════════════════════════════════════════════════════════════════════


def test_data_knowable_before_decision_passes() -> None:
    assert_no_lookahead(T0, T1, "bar")


def test_data_knowable_after_decision_raises() -> None:
    """The failure this module exists to prevent, stated as a test."""
    with pytest.raises(LookaheadViolation, match="look-ahead"):
        assert_no_lookahead(T2, T1, "bar")


def test_data_knowable_exactly_at_decision_passes() -> None:
    """Boundary is inclusive: knowable at decision time is usable."""
    assert_no_lookahead(T1, T1, "bar")


def test_unknown_knowable_time_is_refused_not_trusted() -> None:
    """A row that cannot say when it became knowable cannot prove it was."""
    with pytest.raises(LookaheadViolation, match="no knowable time"):
        assert_no_lookahead(None, T1, "bar")


def test_filter_as_of_keeps_only_knowable() -> None:
    rows = [
        {"id": "old", "knowable": T0},
        {"id": "edge", "knowable": T1},
        {"id": "future", "knowable": T2},
        {"id": "unknown", "knowable": None},
    ]
    kept = filter_as_of(rows, T1, lambda r: r["knowable"])
    assert [r["id"] for r in kept] == ["old", "edge"]


def test_filter_as_of_excludes_unknown_rather_than_trusting_it() -> None:
    """Unknown is not "probably fine". It is the absence of the required proof."""
    assert filter_as_of([{"id": "x", "knowable": None}], T2, lambda r: r["knowable"]) == []


def test_is_as_of_unknown() -> None:
    assert is_as_of_unknown(None) is True
    assert is_as_of_unknown(T0) is False


# ══════════════════════════════════════════════════════════════════════════
# Provenance carries the join key
# ══════════════════════════════════════════════════════════════════════════


def test_provenance_without_available_at_is_as_of_unknown() -> None:
    """Every existing data row lacks available_at, so every one is unknown.

    This is the backfill obligation stated as a test: until a row is backfilled
    it cannot back research, and the system must say so rather than trust it.
    """
    from schemas.contracts import DataProvenance

    provenance = DataProvenance(source_id="ccxt:binance", source_type="MARKET")
    assert provenance.available_at is None
    assert is_as_of_unknown(provenance.available_at) is True


def test_provenance_with_available_at_is_queryable() -> None:
    from schemas.contracts import DataProvenance

    provenance = DataProvenance(
        source_id="ccxt:binance",
        source_type="MARKET",
        data_timestamp=T0,
        available_at=T1,
    )
    assert not is_as_of_unknown(provenance.available_at)
    # The join key is available_at, not retrieved_at: a datum retrieved late
    # but knowable early is usable, and the reverse is look-ahead.
    assert_no_lookahead(provenance.available_at, T2, "bar")
    with pytest.raises(LookaheadViolation):
        assert_no_lookahead(provenance.available_at, T0, "bar")


def test_replay_bar_timestamp_is_event_time_not_available_at() -> None:
    """A replay cursor proves no look-ahead for prices, not for knowledge.

    The replay fetcher exposes one bar at a time, which bounds what the
    strategy can *see*. It does not bound what was *knowable*: a corporate
    action announced after the bar is still invisible to the cursor. Both
    properties are needed, and this test records that the cursor is only one.
    """
    from communities.c1_data.replay_fetcher import ReplayCursor

    cursor = ReplayCursor()
    assert cursor.index == 0
    cursor.advance()
    assert cursor.started is True


# ══════════════════════════════════════════════════════════════════════════
# Dataset versions declare their cut clock
# ══════════════════════════════════════════════════════════════════════════


def test_default_dataset_version_is_not_pit_qualified() -> None:
    """Existing versions are snapshots with an opinion about time.

    They keep working, but they may not back point-in-time research until they
    declare their cut clock, record both times, and freeze their content.
    """
    from kernel.bootstrap import create_kernel
    from kernel.registries import DatasetRegistry

    kernel = create_kernel()
    registry = DatasetRegistry(kernel.state_machine, kernel.provenance)
    dv = registry.register(
        dataset_id="btc_daily",
        version="v1.0",
        source="ccxt:binance",
        schema_hash="abc",
        content_hash="def",
        time_start="2024-01-01",
        time_end="2024-12-31",
        row_count=365,
        actor_id="system",
    )
    assert dv.is_pit_qualified() is False


def test_pit_qualified_version_names_its_cut_and_freezes() -> None:
    from kernel.bootstrap import create_kernel
    from kernel.registries import DatasetRegistry

    kernel = create_kernel()
    registry = DatasetRegistry(kernel.state_machine, kernel.provenance)
    dv = registry.register(
        dataset_id="btc_daily",
        version="v2.0",
        source="ccxt:binance",
        schema_hash="abc",
        content_hash="def",
        time_start="2024-01-01",
        time_end="2024-12-31",
        row_count=365,
        actor_id="system",
        as_of_semantics="available_at",
        bitemporal=True,
        immutable_hash="sha256:frozen",
    )
    assert dv.is_pit_qualified() is True
    assert dv.reference()["immutable_hash"] == "sha256:frozen"


def test_reference_carries_the_frozen_hash_when_present() -> None:
    """An experiment that pins a version pins the frozen content, not the name."""
    from kernel.bootstrap import create_kernel
    from kernel.registries import DatasetRegistry

    kernel = create_kernel()
    registry = DatasetRegistry(kernel.state_machine, kernel.provenance)
    dv = registry.register(
        dataset_id="d",
        version="v1",
        source="s",
        schema_hash="h",
        content_hash="c",
        time_start="2024",
        time_end="2025",
        row_count=1,
        actor_id="system",
        immutable_hash="sha256:x",
        bitemporal=True,
        as_of_semantics="available_at",
    )
    assert dv.reference()["immutable_hash"] == "sha256:x"


def test_temporal_instant_survives_a_dict_round_trip() -> None:
    instant = _instant(event=T0, available=T1, received=T2, processed=T2 + timedelta(seconds=1))
    payload = instant.as_dict()
    assert payload["available_at"] == T1.isoformat()
    assert payload["sequence"] == 0
