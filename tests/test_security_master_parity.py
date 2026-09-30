"""Cross-dialect parity for the security master (goal G020).

The SQLite tier is the dev default; PostgreSQL is production. A behavioural
difference between them is a defect in one of the two stores, not a dialect
difference — and the failure it produces is the worst kind, because every test
passes on the tier it runs on while production reads different answers.

So every behavioural test here runs against *both* tiers. The PostgreSQL leg
runs when ``AIOS_TEST_PG_DSN`` is set and skips otherwise, which is the same
contract the existing integration suites use: CI and hermetic local runs stay
green everywhere, and wherever a database exists the parity is actually
exercised rather than asserted.

The hermetic half of this file needs no database at all: the v3 DDL on both
dialects must define the same tables, indexes, and triggers. A table present
on one tier and missing on the other is a schema fork, and a fork discovered
at migration time in production is the most expensive place to find it.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.migrations import MIGRATIONS, _statements
from core.security_master import (
    ActionType,
    AssetClass,
    CorporateAction,
    InstrumentIdentity,
    InstrumentStatus,
    SecurityMaster,
)
from core.security_master_store import (
    PostgresSecurityMasterStore,
    SecurityMasterError,
    build_sqlite_security_master_store,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = T0 + timedelta(days=30)
T2 = T0 + timedelta(days=60)

DSN = os.environ.get("AIOS_TEST_PG_DSN", "")
NEEDS_PG = pytest.mark.skipif(not DSN, reason="set AIOS_TEST_PG_DSN to run the PostgreSQL leg")


def _equity(
    instrument_id: str,
    ticker: str,
    mic: str,
    *,
    valid_from: datetime = T0,
    recorded_from: datetime | None = None,
    source: str = "test",
    source_priority: int = 100,
    **overrides,
) -> InstrumentIdentity:
    overrides.setdefault("tick_size", Decimal("0.01"))
    overrides.setdefault("lot_size", Decimal("1"))
    return InstrumentIdentity(
        instrument_id=instrument_id,
        listing_id=overrides.pop("listing_id", f"{mic}:{instrument_id}"),
        ticker=ticker,
        mic=mic,
        venue=mic,
        asset_class=AssetClass.EQUITY,
        currency="USD",
        valid_from=valid_from,
        recorded_from=recorded_from or valid_from,
        source=source,
        source_priority=source_priority,
        **overrides,
    )


def _split(
    instrument_id: str, effective_at: datetime, action_id: str = "split-1"
) -> CorporateAction:
    return CorporateAction(
        action_id=action_id,
        instrument_id=instrument_id,
        action_type=ActionType.SPLIT,
        announced_at=effective_at - timedelta(days=30),
        effective_at=effective_at,
        ratio_old=Decimal("1"),
        ratio_new=Decimal("4"),
        source="test",
    )


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def master(request, tmp_path: Path) -> SecurityMaster:
    """One SecurityMaster per tier. Same behaviour asserted on both."""
    if request.param == "sqlite":
        yield SecurityMaster(build_sqlite_security_master_store(tmp_path / "sec.db"))
    else:
        store = PostgresSecurityMasterStore(DSN, auto_migrate=True)
        store._conn.autocommit = True
        with store._conn.cursor() as cur:
            cur.execute(
                "TRUNCATE instrument_identity, corporate_actions, identity_conflicts"
            )
        store._conn.autocommit = False
        try:
            yield SecurityMaster(store)
        finally:
            store.close()


# ══════════════════════════════════════════════════════════════════════════
# Behavioural parity: identical answers on both tiers
# ══════════════════════════════════════════════════════════════════════════


def test_identity_round_trip_preserves_exact_decimals(master: SecurityMaster) -> None:
    """Tick sizes are exact quantities. A tier that floats them corrupts every
    price grid derived downstream, silently and differently per tier."""
    master.upsert(_equity("i1", "ABC", "XNYS"))
    current = master.current("i1")
    assert current is not None
    assert current.tick_size == Decimal("0.01")
    assert current.lot_size == Decimal("1")
    assert current.ticker == "ABC"


def test_supersession_closes_the_prior_belief(master: SecurityMaster) -> None:
    """A revised belief closes the old row; it does not delete or duplicate it."""
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T0))
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T1, recorded_from=T1))
    versions = master.versions("i1")
    assert len(versions) == 2
    assert versions[0].recorded_to is not None
    assert versions[1].recorded_to is None
    assert master.current("i1") is not None
    assert master.current("i1").valid_from == T1


def test_reasserting_history_is_a_no_op_on_both_tiers(master: SecurityMaster) -> None:
    """A feed reload re-asserts superseded versions. The second assertion of
    an identical row must not reach the store's insert path — where the
    primary key would refuse it — on either tier. Tier-specific PK errors
    surfacing here would mean the no-op lives in one dialect but not the other."""
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T0))
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T1, recorded_from=T1))
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T0))
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T1, recorded_from=T1))
    assert len(master.versions("i1")) == 2


def test_same_instant_supersession_round_trips(master: SecurityMaster) -> None:
    """Backfill pattern: two revisions asserted with one recorded timestamp.

    The store closes the first at the second's recorded time, producing
    recorded_to == recorded_from. The row must read back — a store that
    writes rows its own model refuses to read is corrupt by construction,
    identically on both tiers.
    """
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T1))
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T2, recorded_from=T1))
    versions = master.versions("i1")
    assert len(versions) == 2
    assert versions[0].recorded_to == versions[0].recorded_from
    assert master.current("i1").valid_from == T2


def test_reused_ticker_never_collapses_two_issuers(master: SecurityMaster) -> None:
    """The gate the goal names: two issuers, one ticker, distinct identities."""
    master.upsert(
        _equity(
            "old-corp", "ZZZ", "XNYS", valid_from=T0, valid_to=T1,
            status=InstrumentStatus.DELISTED,
        )
    )
    master.upsert(_equity("new-corp", "ZZZ", "XNYS", valid_from=T1))
    assert master.as_of("old-corp", T0 + timedelta(days=1)).ticker == "ZZZ"
    assert master.as_of("new-corp", T1 + timedelta(days=1)).ticker == "ZZZ"
    # resolve() orders by revision only, so with two current rows for one
    # ticker the tie-break is unspecified — asserting either outcome would
    # make this a parity hazard, passing per tier or per run. The time-aware
    # lookup disambiguates; the ticker lookup deliberately does not promise
    # to. (Whether resolve should prefer live listings is a G140 question,
    # recorded there — not a parity question.)
    assert master.resolve("ZZZ", "XNYS") is not None
    assert master.resolve("ZZZ", "XNYS").instrument_id in {"old-corp", "new-corp"}


def test_source_conflict_is_recorded_and_lower_priority_wins(
    master: SecurityMaster,
) -> None:
    """A disagreement is evidence, and the loser is retained as such."""
    master.upsert(
        _equity("i1", "ABC", "XNYS", recorded_from=T0, source="vendor-a", source_priority=10)
    )
    master.upsert(
        _equity("i1", "ABC", "XNYS", recorded_from=T1, source="vendor-b", source_priority=90,
                tick_size=Decimal("0.05"))
    )
    conflicts = master.conflicts_for("i1")
    assert len(conflicts) == 1
    assert conflicts[0].winner == "vendor-a"
    # Storage always advances to the latest insert; the conflict row is the
    # audit trail saying vendor-a would have won by priority. Current belief
    # is vendor-b's assertion, disagreed-with and recorded as such.
    assert master.current("i1").tick_size == Decimal("0.05")
    assert len(master.versions("i1")) == 2


def test_same_source_restatement_is_a_correction_not_a_conflict(
    master: SecurityMaster,
) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS", source="vendor-a"))
    master.upsert(
        _equity("i1", "ABC", "XNYS", source="vendor-a", valid_from=T1,
                tick_size=Decimal("0.05"))
    )
    assert master.conflicts_for("i1") == []
    assert master.current("i1").tick_size == Decimal("0.05")


def test_action_round_trip_preserves_exact_ratios(master: SecurityMaster) -> None:
    """Split ratios are exact. A 4-for-1 recorded as 3.9999999 on one tier
    would adjust every historical price on that tier differently."""
    master.upsert(_equity("i1", "ABC", "XNYS"))
    master.record_action(_split("i1", T1))
    actions = master.actions("i1")
    assert len(actions) == 1
    assert actions[0].ratio_old == Decimal("1")
    assert actions[0].ratio_new == Decimal("4")
    assert actions[0].split_factor == Decimal("0.25")


def test_rerecording_an_action_is_a_no_op(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS"))
    first = master.record_action(_split("i1", T1))
    second = master.record_action(_split("i1", T1))
    assert second == first
    assert len(master.actions("i1")) == 1


def test_rerecording_an_action_with_different_content_is_refused(
    master: SecurityMaster,
) -> None:
    """Immutability is per-tier. A tier that silently overwrote would let a
    corrected split rewrite history without a trace."""
    master.upsert(_equity("i1", "ABC", "XNYS"))
    master.record_action(_split("i1", T1))
    altered = CorporateAction(
        action_id="split-1",
        instrument_id="i1",
        action_type=ActionType.SPLIT,
        announced_at=T1 - timedelta(days=30),
        effective_at=T1,
        ratio_old=Decimal("1"),
        ratio_new=Decimal("2"),
        source="test",
    )
    with pytest.raises(SecurityMasterError, match="immutable"):
        master.record_action(altered)


def test_all_actions_window_bounds_hold_on_both_tiers(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS"))
    master.record_action(_split("i1", T1, action_id="s1"))
    master.record_action(_split("i1", T2, action_id="s2"))
    assert [a.action_id for a in master._store.all_actions()] == ["s1", "s2"]
    windowed = master._store.all_actions(
        window_start=T1.isoformat(), window_end=T1.isoformat()
    )
    assert [a.action_id for a in windowed] == ["s1"]
    assert master._store.all_actions(window_start=T2.isoformat()) == [
        a for a in master._store.all_actions() if a.action_id == "s2"
    ]


def test_delisted_identities_are_visible_to_enumeration(master: SecurityMaster) -> None:
    """Survivorship bias is the absence of instruments: a tier whose
    enumeration only reaches current beliefs is blind to exactly the rows
    that matter."""
    master.upsert(_equity("alive", "AAA", "XNYS"))
    master.upsert(
        _equity("dead", "DDD", "XNYS", valid_from=T0, valid_to=T1,
                status=InstrumentStatus.DELISTED)
    )
    assert master._store.all_instrument_ids() == ["alive", "dead"]
    # "Current belief" is not "live": the delisted row is still the latest
    # belief about that instrument, and current() reports it with its status
    # rather than pretending the instrument never existed.
    assert master.current("dead") is not None
    assert master.current("dead").status is InstrumentStatus.DELISTED
    assert master.current("dead").is_live is False
    assert master.as_of("dead", T0).status is InstrumentStatus.DELISTED


def test_as_known_sees_what_was_believed_when(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS", valid_from=T0, recorded_from=T1))
    assert master.as_known("i1", T0) is None
    assert master.as_known("i1", T1) is not None
    assert master.as_known("i1", T1).ticker == "ABC"


def test_find_by_isin_reaches_the_current_listing(master: SecurityMaster) -> None:
    master.upsert(_equity("i1", "ABC", "XNYS", isin="US0000000001"))
    found = master.find_by_isin("US0000000001")
    assert found is not None
    assert found.instrument_id == "i1"
    assert master.find_by_isin("US9999999999") is None


# ══════════════════════════════════════════════════════════════════════════
# Hermetic: the two DDLs define the same schema
# ══════════════════════════════════════════════════════════════════════════


def _ddl_names(statements: list[str], kind: str) -> set[str]:
    pattern = re.compile(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+)?{kind}\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
        re.IGNORECASE,
    )
    names = set()
    for statement in statements:
        match = pattern.search(statement)
        if match:
            names.add(match.group(1).lower())
    return names


def test_v3_tables_indexes_and_triggers_match_across_dialects() -> None:
    """A table present on one tier and missing on the other is a schema fork,
    and a fork discovered at migration time in production is the most
    expensive place to find it. No database needed: the DDL texts are the
    artifact under test."""
    v3 = next(m for m in MIGRATIONS if m.version == 3)
    sqlite_stmts = _statements(v3.sqlite)
    pg_stmts = _statements(v3.postgres)
    for kind in ("TABLE", "INDEX", "TRIGGER", "FUNCTION"):
        sqlite_names = _ddl_names(sqlite_stmts, kind)
        pg_names = _ddl_names(pg_stmts, kind)
        assert sqlite_names == pg_names, (
            f"{kind} mismatch: sqlite={sorted(sqlite_names)} postgres={sorted(pg_names)}"
        )


def test_v3_columns_match_across_dialects() -> None:
    """Same tables is necessary but not sufficient: a column missing on one
    tier fails reads that the other tier passes, which is a parity failure
    wearing a schema's clothes."""
    v3 = next(m for m in MIGRATIONS if m.version == 3)

    def columns(statements: list[str]) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for statement in statements:
            match = re.search(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)",
                statement, re.IGNORECASE | re.DOTALL,
            )
            if not match:
                continue
            table, body = match.group(1).lower(), match.group(2)
            cols = set()
            for line in body.splitlines():
                token = line.strip().split()
                if token and token[0].upper() not in {
                    "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT",
                }:
                    cols.add(token[0].strip('", ').lower())
            found[table] = cols
        return found

    sqlite_cols = columns(_statements(v3.sqlite))
    pg_cols = columns(_statements(v3.postgres))
    assert set(sqlite_cols) == set(pg_cols)
    for table in sqlite_cols:
        assert sqlite_cols[table] == pg_cols[table], (
            f"column mismatch on {table}: "
            f"sqlite-only={sorted(sqlite_cols[table] - pg_cols[table])} "
            f"postgres-only={sorted(pg_cols[table] - sqlite_cols[table])}"
        )
