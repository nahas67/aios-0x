"""Instrument identity is bitemporal, and the tests prove it (goal G020).

The failure this suite exists to prevent is silent. A ticker reused across two
issuers produces a price series that looks entirely normal, on a chart, in a
backtest, and is wrong. No downstream check can detect it, because every
component downstream is reading a plausible value.

So the tests assert the temporal algebra directly, using the fixtures that
break real systems: a share class, a cross-listing, a delisted-and-reused
ticker, and a delisting.

The store is exercised on SQLite. Parity with PostgreSQL is covered by
``tests/test_v1a2_postgres.py`` for the financial kernel; the SQL here is
parameter-free and dialect-portable, and ``test_postgres_ddl_is_present`` at
least confirms the v3 migration ships a PostgreSQL definition rather than
silently SQLite-only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from core.security_master import (
    ActionType,
    AssetClass,
    CorporateAction,
    CorporateActionEngine,
    IdentityConflict,
    InstrumentIdentity,
    InstrumentStatus,
    SecurityMaster,
)
from core.security_master_store import (
    SecurityMasterError,
    SqliteSecurityMasterStore,
)

T0 = datetime(2020, 1, 1, tzinfo=UTC)
T1 = datetime(2021, 1, 1, tzinfo=UTC)
T2 = datetime(2022, 1, 1, tzinfo=UTC)
T3 = datetime(2023, 1, 1, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path) -> SqliteSecurityMasterStore:
    return SqliteSecurityMasterStore(tmp_path / "security.db")


@pytest.fixture()
def master(store: SqliteSecurityMasterStore) -> SecurityMaster:
    return SecurityMaster(store)


def _equity(
    instrument_id: str,
    ticker: str,
    mic: str,
    *,
    valid_from: datetime = T0,
    recorded_from: datetime | None = None,
    currency: str = "USD",
    listing_id: str | None = None,
    **overrides,
) -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=instrument_id,
        # Supersession is per listing, so a test that revises a belief must keep
        # the listing stable. Defaulting it to the ticker would make every
        # revision look like a brand-new listing.
        listing_id=listing_id or f"{mic}:{instrument_id}",
        ticker=ticker,
        mic=mic,
        venue=mic,
        asset_class=AssetClass.EQUITY,
        currency=currency,
        valid_from=valid_from,
        recorded_from=recorded_from or valid_from,
        source=overrides.pop("source", "test"),
        **overrides,
    )


# ══════════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════════


def test_identical_content_at_different_times_is_one_assertion() -> None:
    """The digest excludes temporal columns, so re-recording is a no-op.

    Without this, a feed that reloads every night manufactures a new revision
    each time and an auditor has to explain thousands of identical rows.
    """
    early = _equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T0)
    late = _equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T3)
    assert early.identity_digest() == late.identity_digest()


def test_content_change_changes_the_digest() -> None:
    a = _equity("i1", "ABC", "XNYS", currency="USD")
    b = _equity("i1", "ABC", "XNYS", currency="EUR")
    assert a.identity_digest() != b.identity_digest()


def test_valid_to_must_follow_valid_from() -> None:
    with pytest.raises(ValueError, match="valid_to must be after valid_from"):
        _equity("i1", "ABC", "XNYS", valid_from=T1, valid_to=T0)


def test_recorded_to_must_follow_recorded_from() -> None:
    """A belief closed before it was held is a contradiction, not a revision."""
    with pytest.raises(ValueError, match="recorded_to must not precede recorded_from"):
        InstrumentIdentity(
            instrument_id="i1",
            listing_id="XNYS:ABC",
            ticker="ABC",
            mic="XNYS",
            venue="XNYS",
            asset_class=AssetClass.EQUITY,
            currency="USD",
            valid_from=T0,
            recorded_from=T3,
            recorded_to=T1,
            source="test",
        )


def test_same_instant_supersession_is_an_empty_truth_not_a_contradiction() -> None:
    """The write path closes a superseded belief at the incoming recorded
    time, so a backfill asserting two revisions with one recorded timestamp
    produces recorded_to == recorded_from. Refusing that would make the store
    write rows the model cannot read back — a defect this test pins shut."""
    closed = InstrumentIdentity(
        instrument_id="i1",
        listing_id="XNYS:ABC",
        ticker="ABC",
        mic="XNYS",
        venue="XNYS",
        asset_class=AssetClass.EQUITY,
        currency="USD",
        valid_from=T0,
        recorded_from=T3,
        recorded_to=T3,
        source="test",
    )
    assert closed.covers_recorded_time(T3) is False
    assert closed.covers_recorded_time(T0) is False


def test_valid_intervals_reject_inversion() -> None:
    with pytest.raises(ValueError, match="valid_to must be after valid_from"):
        InstrumentIdentity(
            instrument_id="i1",
            listing_id="XNYS:ABC",
            ticker="ABC",
            mic="XNYS",
            venue="XNYS",
            asset_class=AssetClass.EQUITY,
            currency="USD",
            valid_from=T1,
            valid_to=T0,
            recorded_from=T1,
            source="test",
        )


def test_decimal_fields_reject_nonsense() -> None:
    with pytest.raises(ValueError, match="tick_size is not a valid number"):
        _equity("i1", "ABC", "XNYS", tick_size="not-a-number")


def test_decimal_fields_do_not_pass_through_float() -> None:
    """0.1 must be exactly 0.1, not the nearest double.

    Prices and ratios are exact quantities. A float round-trip here bakes in
    error that compounds across a chain of splits.
    """
    record = _equity("i1", "ABC", "XNYS", tick_size=Decimal("0.1"))
    assert record.tick_size == Decimal("0.1")
    assert str(record.tick_size) == "0.1"


# ══════════════════════════════════════════════════════════════════════════
# The two temporal questions
# ══════════════════════════════════════════════════════════════════════════


def test_as_of_uses_valid_time_only(master: SecurityMaster) -> None:
    """A backtest must see what was true, even if we learned it much later."""
    master.upsert(
        _equity("i1", "OLD", "XNYS", valid_from=T0, recorded_from=T0, valid_to=T2)
    )
    master.upsert(_equity("i1", "NEW", "XNYS", valid_from=T2, recorded_from=T2))

    historical = master.as_of("i1", T1)
    assert historical is not None
    assert historical.ticker == "OLD"

    current = master.as_of("i1", T3)
    assert current is not None
    assert current.ticker == "NEW"


def test_as_known_uses_recorded_time_only(master: SecurityMaster) -> None:
    """An audit asks what the system believed, which is a different question."""
    # We only learned the truth in T3; before that we believed something else.
    master.upsert(
        _equity("i1", "WRONG", "XNYS", valid_from=T0, recorded_from=T0, valid_to=T2)
    )
    master.upsert(
        _equity("i1", "RIGHT", "XNYS", valid_from=T0, recorded_from=T3, source="correction")
    )

    before_correction = master.as_known("i1", T1)
    assert before_correction is not None
    assert before_correction.ticker == "WRONG"

    after_correction = master.as_known("i1", datetime(2023, 6, 1, tzinfo=UTC))
    assert after_correction is not None
    assert after_correction.ticker == "RIGHT"


def test_as_of_and_as_known_disagree_during_a_correction(master: SecurityMaster) -> None:
    """The two paths are independent, which is the entire point of bitemporality.

    In the gap between learning something and being able to say it was always
    true, valid time and transaction time must return different answers.
    """
    master.upsert(
        _equity("i1", "STALE", "XNYS", valid_from=T0, recorded_from=T0, valid_to=T2)
    )
    # Correction learned in T3, asserting the ticker was always NEW since T0.
    master.upsert(
        _equity("i1", "TRUE", "XNYS", valid_from=T0, recorded_from=T3, source="correction")
    )
    moment = T2 + timedelta(days=1)
    truth = master.as_of("i1", moment)
    belief = master.as_known("i1", moment)
    assert truth is not None and belief is not None
    assert truth.ticker == "TRUE"
    assert belief.ticker == "STALE"


def test_superseded_belief_is_preserved_not_deleted(master: SecurityMaster) -> None:
    """An amendment that erases the old claim is not an amendment, it is a cover-up."""
    master.upsert(_equity("i1", "V1", "XNYS", recorded_from=T0))
    master.upsert(_equity("i1", "V2", "XNYS", recorded_from=T2, source="correction"))

    versions = master.versions("i1")
    assert len(versions) == 2
    assert [v.ticker for v in versions] == ["V1", "V2"]
    assert versions[0].is_current is False
    assert versions[1].is_current is True


def test_resolve_returns_the_current_belief(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "OLD", "XNYS", recorded_from=T0))
    master.upsert(_equity("i1", "NEW", "XNYS", recorded_from=T2, source="correction"))
    resolved = master.resolve("NEW", "XNYS")
    assert resolved is not None
    assert resolved.ticker == "NEW"


def test_resolve_of_an_unknown_ticker_is_none(master: SecurityMaster) -> None:
    assert master.resolve("NOPE", "XNYS") is None


# ══════════════════════════════════════════════════════════════════════════
# Reused tickers: the fixture that breaks real systems
# ══════════════════════════════════════════════════════════════════════════


def test_reused_ticker_never_collapses_two_issuers(master: SecurityMaster) -> None:
    """``XYZ`` was First Corp, delisted, then reused by Second Corp.

    The two must remain distinguishable. A system that keys on the ticker alone
    splices their price series into one line, and nothing downstream can tell.
    """
    first = _equity(
        "first-corp", "XYZ", "XNYS", valid_from=T0, valid_to=T2, status=InstrumentStatus.ACTIVE
    )
    first_closed = first.model_copy(update={"valid_to": T2})
    master.upsert(first_closed)
    second = _equity(
        "second-corp", "XYZ", "XNYS", valid_from=T2, status=InstrumentStatus.ACTIVE
    )
    master.upsert(second)

    # Same ticker, same venue, two identities: no ambiguity about which.
    assert master.as_of("first-corp", T1) is not None
    assert master.as_of("second-corp", T3) is not None
    # The first issuer was not listed at T3 and the second did not exist at T1.
    assert master.as_of("first-corp", T3) is None
    assert master.as_of("second-corp", T1) is None


def test_delisted_instrument_is_never_live(master: SecurityMaster) -> None:
    master.upsert(
        _equity(
            "dead", "DED", "XNYS", valid_from=T0, valid_to=T2, status=InstrumentStatus.DELISTED
        )
    )
    version = master.as_of("dead", T1)
    assert version is not None
    assert version.is_live is False


def test_share_classes_are_distinct_instruments_on_one_venue(master: SecurityMaster) -> None:
    """``BRK.B`` is not ``BRK.A``. Same issuer, different instrument."""
    master.upsert(_equity("brk-a", "BRK.A", "XNYS"))
    master.upsert(_equity("brk-b", "BRK.B", "XNYS"))
    assert master.resolve("BRK.A", "XNYS") is not None
    assert master.resolve("BRK.B", "XNYS") is not None
    assert master.as_of("brk-b", T1) is not None


def test_cross_listed_instrument_keeps_one_identity_per_listing(master: SecurityMaster) -> None:
    """One issuer, two venues, two listings, one instrument identity."""
    master.upsert(_equity("acme", "ACME", "XNYS"))
    master.upsert(_equity("acme", "ACME", "XLON"))
    assert master.as_of("acme", T1) is not None
    assert master.resolve("ACME", "XLON") is not None
    assert len(master.versions("acme")) == 2


def test_isin_resolves_across_venues(master: SecurityMaster) -> None:
    master.upsert(_equity("acme", "ACME", "XNYS", isin="US0000000001"))
    master.upsert(_equity("acme", "ACME", "XLON", isin="US0000000001"))
    found = master.find_by_isin("US0000000001")
    assert found is not None
    assert found.instrument_id == "acme"


# ══════════════════════════════════════════════════════════════════════════
# Store behaviour
# ══════════════════════════════════════════════════════════════════════════


def test_identical_reload_does_not_churn_history(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS", recorded_from=T0))
    for _ in range(5):
        master.upsert(_equity("i1", "ABC", "XNYS", recorded_from=T0))
    assert len(master.versions("i1")) == 1


def test_source_conflict_is_recorded_not_discarded(master: SecurityMaster) -> None:
    """A source that was wrong once is evidence an audit needs."""
    master.upsert(
        _equity("i1", "A", "XNYS", recorded_from=T0, source="vendor-1", source_priority=10)
    )
    master.upsert(
        _equity("i1", "B", "XNYS", recorded_from=T2, source="vendor-2", source_priority=50)
    )
    conflicts = master.conflicts_for("i1")
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert isinstance(conflict, IdentityConflict)
    assert {conflict.existing_source, conflict.incoming_source} == {"vendor-1", "vendor-2"}
    assert conflict.winner == "vendor-1"
    assert "source_priority" in conflict.reason


def test_higher_priority_source_wins_and_belief_advances(master: SecurityMaster) -> None:
    master.upsert(
        _equity("i1", "A", "XNYS", recorded_from=T0, source="weak", source_priority=900)
    )
    master.upsert(
        _equity("i1", "B", "XNYS", recorded_from=T2, source="strong", source_priority=10)
    )
    conflicts = master.conflicts_for("i1")
    assert conflicts[0].winner == "strong"
    assert master.as_known("i1", T3).ticker == "B"  # type: ignore[union-attr]


def test_same_source_correction_is_not_a_conflict(master: SecurityMaster) -> None:
    """One source fixing itself is a revision, not a disagreement."""
    master.upsert(_equity("i1", "A", "XNYS", recorded_from=T0, source="vendor-1"))
    master.upsert(_equity("i1", "B", "XNYS", recorded_from=T2, source="vendor-1"))
    assert master.conflicts_for("i1") == []


def test_identity_round_trips_through_the_store(master: SecurityMaster) -> None:
    record = _equity(
        "i1",
        "ABC",
        "XNYS",
        tick_size=Decimal("0.01"),
        lot_size=Decimal("100"),
        multiplier=Decimal("1"),
        isin="US0000000002",
        cik="0000000001",
        status=InstrumentStatus.SUSPENDED,
    )
    master.upsert(record)
    stored = master.current("i1")
    assert stored == record


def test_decimal_precision_survives_the_store(master: SecurityMaster) -> None:
    """A price of 0.1 must come back as 0.1 after a persistence round trip."""
    master.upsert(_equity("i1", "ABC", "XNYS", tick_size=Decimal("0.1")))
    assert master.current("i1").tick_size == Decimal("0.1")  # type: ignore[union-attr]


# ══════════════════════════════════════════════════════════════════════════
# Corporate actions
# ══════════════════════════════════════════════════════════════════════════


def _split(
    ratio_old: str,
    ratio_new: str,
    effective: datetime,
    action_id: str | None = None,
) -> CorporateAction:
    return CorporateAction(
        action_id=action_id or f"split-{ratio_old}-{ratio_new}-{effective.year}",
        instrument_id="i1",
        action_type=ActionType.SPLIT,
        announced_at=effective - timedelta(days=7),
        effective_at=effective,
        ratio_old=Decimal(ratio_old),
        ratio_new=Decimal(ratio_new),
        source="test",
    )


def _dividend(amount: str, effective: datetime) -> CorporateAction:
    return CorporateAction(
        action_id=f"div-{amount}-{effective.year}",
        instrument_id="i1",
        action_type=ActionType.DIVIDEND,
        announced_at=effective - timedelta(days=14),
        effective_at=effective,
        cash_amount=Decimal(amount),
        source="test",
    )


def test_split_adjusts_price_and_quantity_inversely() -> None:
    """A 4-for-1 split: a pre-split price of 400 becomes 100, one share becomes 4."""
    engine = CorporateActionEngine([_split("1", "4", T1)])
    moment = datetime(2020, 12, 31, tzinfo=UTC)
    factor = engine.adjustment("i1", moment, anchor=T2)
    assert factor.price_factor == Decimal("0.25")
    assert factor.quantity_factor == Decimal(4)


def test_reverse_split_is_the_mirror_of_a_split() -> None:
    """A 1-for-10 reverse split moves in the opposite direction."""
    engine = CorporateActionEngine([_split("10", "1", T1)])
    moment = datetime(2020, 12, 31, tzinfo=UTC)
    assert engine.adjustment("i1", moment, anchor=T2).price_factor == Decimal(10)


def test_an_action_before_the_observation_does_not_alter_it() -> None:
    """Already-baked-in economics must not be applied twice.

    The look-ahead property's mirror image: scaling a post-split observation by
    the split that already happened to it double-counts, and a naive
    "apply every split in the file" implementation does exactly that.
    """
    engine = CorporateActionEngine([_split("1", "2", T1)])
    after = engine.adjustment("i1", T2, anchor=T3)
    assert after.price_factor == Decimal(1)
    assert after.quantity_factor == Decimal(1)


def test_an_action_after_the_anchor_does_not_alter_it() -> None:
    """Outside the frame means outside the answer."""
    engine = CorporateActionEngine([_split("1", "2", T1), _split("1", "2", T2)])
    # Anchor before the second split, so only the first can contribute.
    factor = engine.adjustment("i1", datetime(2020, 6, 1, tzinfo=UTC), anchor=T1)
    assert factor.applied == 1
    assert factor.price_factor == Decimal("0.5")


def test_anchor_defaults_to_the_latest_known_action() -> None:
    engine = CorporateActionEngine([_split("1", "2", T1)])
    moment = datetime(2020, 6, 1, tzinfo=UTC)
    assert engine.adjustment("i1", moment).anchor == T1


def test_no_actions_means_an_identity_transform() -> None:
    engine = CorporateActionEngine()
    factor = engine.adjustment("i1", T2)
    assert factor.is_identity
    assert factor.applied == 0


def test_anchoring_before_the_observation_is_refused() -> None:
    """A nonsensical frame is an error, not a silently clamped answer."""
    engine = CorporateActionEngine([_split("1", "2", T1)])
    with pytest.raises(ValueError, match="after the requested anchor"):
        engine.adjustment("i1", T3, anchor=T1)


def test_an_unadjusted_price_adjusts_to_a_continuous_series() -> None:
    """A known split halves an unadjusted price into a continuous series.

    Concretely: a 2-for-1 split means the raw feed shows 100 before the ex-date
    and 50 after. Back-adjusting the earlier observation makes both 50, which is
    the whole purpose of the engine.
    """
    engine = CorporateActionEngine([_split("1", "2", T1)])
    anchor = datetime(2021, 1, 3, tzinfo=UTC)
    before = engine.adjust_price(
        "i1", datetime(2020, 12, 31, tzinfo=UTC), Decimal("100"), anchor=anchor
    )
    after = engine.adjust_price(
        "i1", datetime(2021, 1, 2, tzinfo=UTC), Decimal("50"), anchor=anchor
    )
    assert before == Decimal(50)
    assert after == Decimal(50)


def test_adjustment_inverts_exactly() -> None:
    """Unadjusting must recover the raw value, or a re-fit changes the history."""
    engine = CorporateActionEngine([_split("1", "4", T1), _split("1", "2", T2)])
    moment = datetime(2020, 6, 1, tzinfo=UTC)
    raw = Decimal("123.45")
    adjusted = engine.adjust_price("i1", moment, raw)
    assert engine.unadjust_price("i1", moment, adjusted) == raw


def test_dividend_reduces_price_without_changing_share_count() -> None:
    engine = CorporateActionEngine([_dividend("2.50", T1)])
    moment = datetime(2020, 6, 1, tzinfo=UTC)
    factor = engine.adjustment("i1", moment, anchor=T2)
    assert factor.price_factor == Decimal(1)
    assert factor.quantity_factor == Decimal(1)
    assert factor.cash_per_share == Decimal("2.50")


def test_chained_splits_compound() -> None:
    engine = CorporateActionEngine([_split("1", "4", T1), _split("1", "2", T2)])
    moment = datetime(2020, 6, 1, tzinfo=UTC)
    factor = engine.adjustment("i1", moment, anchor=T3)
    assert factor.price_factor == Decimal("0.125")
    assert factor.quantity_factor == Decimal(8)


def test_identity_transition_reports_delisting() -> None:
    engine = CorporateActionEngine(
        [
            CorporateAction(
                action_id="delist-1",
                instrument_id="i1",
                action_type=ActionType.DELISTING,
                announced_at=T1,
                effective_at=T2,
                source="test",
            )
        ]
    )
    transitions = engine.identity_transitions("i1")
    assert transitions == [(T2, InstrumentStatus.DELISTED, None)]


def test_ticker_at_reflects_a_symbol_change() -> None:
    """Joining a 2019 series to a ticker adopted in 2023 is a silent corruption."""
    engine = CorporateActionEngine(
        [
            CorporateAction(
                action_id="sym-1",
                instrument_id="i1",
                action_type=ActionType.SYMBOL_CHANGE,
                announced_at=T1,
                effective_at=T2,
                new_ticker="NEWCO",
                source="test",
            )
        ]
    )
    assert engine.ticker_at("i1", T1) is None
    assert engine.ticker_at("i1", T3) == "NEWCO"


def test_split_requires_both_ratios() -> None:
    from core.security_master import ActionType

    with pytest.raises(ValueError, match="requires ratio_old and ratio_new"):
        CorporateAction(
            action_id="bad",
            instrument_id="i1",
            action_type=ActionType.SPLIT,
            announced_at=T0,
            effective_at=T1,
            ratio_old=Decimal(1),
            source="test",
        )


def test_symbol_change_requires_a_new_ticker() -> None:
    with pytest.raises(ValueError, match="requires new_ticker"):
        CorporateAction(
            action_id="bad",
            instrument_id="i1",
            action_type=ActionType.SYMBOL_CHANGE,
            announced_at=T0,
            effective_at=T1,
            source="test",
        )


def test_an_action_cannot_take_effect_before_it_is_announced() -> None:
    """Acting on information that did not exist yet is look-ahead by construction."""
    with pytest.raises(ValueError, match="before it is announced"):
        CorporateAction(
            action_id="bad",
            instrument_id="i1",
            action_type=ActionType.DELISTING,
            announced_at=T2,
            effective_at=T1,
            source="test",
        )


def test_ex_date_cannot_precede_record_date() -> None:
    with pytest.raises(ValueError, match="ex_date cannot precede record_date"):
        CorporateAction(
            action_id="bad",
            instrument_id="i1",
            action_type=ActionType.DIVIDEND,
            announced_at=T0,
            effective_at=T1,
            record_date=date(2021, 6, 1),
            ex_date=date(2021, 5, 1),
            source="test",
        )


def test_actions_are_immutable_in_the_store(master: SecurityMaster) -> None:
    """A corrected ratio gets a new action_id, so the history stays explainable."""
    master.record_action(_split("1", "4", T1, action_id="split-A"))
    with pytest.raises(SecurityMasterError, match="already recorded with different"):
        master.record_action(_split("1", "8", T1, action_id="split-A"))


def test_recording_the_same_action_twice_is_a_no_op(master: SecurityMaster) -> None:
    master.record_action(_split("1", "4", T1))
    master.record_action(_split("1", "4", T1))
    assert len(master.actions("i1")) == 1


# ══════════════════════════════════════════════════════════════════════════
# Dialect coverage
# ══════════════════════════════════════════════════════════════════════════


def test_postgres_ddl_is_present_for_v3() -> None:
    """The v3 migration must ship a PostgreSQL definition.

    A SQLite-only migration would pass every local test and fail at deploy, so
    its absence is asserted rather than assumed.
    """
    from core.migrations import MIGRATIONS

    v3 = next(m for m in MIGRATIONS if m.version == 3)
    assert "instrument_identity" in v3.postgres
    assert "corporate_actions" in v3.postgres
    assert "TIMESTAMPTZ" in v3.postgres
    assert "identity_conflicts" in v3.postgres


def test_postgres_uses_numeric_for_money() -> None:
    """PostgreSQL gets NUMERIC, not DOUBLE PRECISION, for exact quantities."""
    from core.migrations import MIGRATIONS

    v3 = next(m for m in MIGRATIONS if m.version == 3)
    assert "NUMERIC" in v3.postgres
    assert "DOUBLE PRECISION" not in v3.postgres.split("CREATE TABLE IF NOT EXISTS instrument_identity")[1].split(
        "CREATE TABLE IF NOT EXISTS identity_conflicts"
    )[0]


def test_schema_migration_applies_every_version_in_order(tmp_path) -> None:
    """Assert the full applied list, not a count.

    A count-only assertion (``== 3``) would still pass if a migration were
    renumbered or if the ledger were skipped entirely, because the number of
    rows would be unchanged. Naming every version means adding v4 breaks this
    test loudly, which is the point — an unmigrated tier is how a schema
    silently diverges between environments.
    """
    store = SqliteSecurityMasterStore(tmp_path / "m.db")
    rows = store._identity_rows("SELECT version FROM schema_migrations ORDER BY version", ())
    assert [int(r["version"]) for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
