"""Seed ingest populates an empty master (goal G020).

The security master is empty in production until something populates it, and
an empty master makes every backtest provisional: no identity to join on, no
delistings for the survivorship detector to find, no splits for the adjustment
engine to replay. This suite covers the importer that fixes that, and the
three properties that make re-runs safe — because ingest runs at bootstrap,
at deploy, and whenever the corpus grows:

*Validation precedes writing.* A bundle with one bad row records nothing,
and the report names the row. A half-populated master is worse than an empty
one, because its gaps look like absences.

*Identities upsert.* Re-ingest of an unchanged bundle changes nothing; the
report says "skipped", not "recorded again". A second run that claims to
have recorded the whole book is lying about what it did.

*Actions are immutable.* Re-recording is a no-op; the same action_id with
different content is refused. A corporate action that changed after the fact
is a correction with a new name, not an edit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.security_master import SecurityMaster
from core.security_master_store import build_sqlite_security_master_store
from core.seed_ingest import SeedIngestError, ingest_seed_bundle, load_seed_bundle

BUNDLE_PATH = Path(__file__).resolve().parent.parent / "data" / "seed" / "bootstrap_v1.json"


@pytest.fixture()
def master(tmp_path: Path) -> SecurityMaster:
    return SecurityMaster(build_sqlite_security_master_store(tmp_path / "sec.db"))


# ══════════════════════════════════════════════════════════════════════════
# The bootstrap corpus
# ══════════════════════════════════════════════════════════════════════════


def test_the_bootstrap_bundle_loads(master: SecurityMaster) -> None:
    """The corpus the repo ships must itself be ingestible, or it is
    documentation rather than seed."""
    bundle = load_seed_bundle(BUNDLE_PATH)
    assert bundle["bundle_id"] == "aios-bootstrap-v1"
    report = ingest_seed_bundle(master, bundle)
    assert report.ok, report.errors
    assert report.identities_recorded == 9
    assert report.actions_recorded == 9
    assert "clean" in report.summary()


def test_ingest_is_idempotent(master: SecurityMaster) -> None:
    """The second run changes nothing and says so.

    Ingest runs at every deploy. A re-run that manufactured revisions would
    fork identity history on a schedule, and an auditor would then have to
    explain thousands of identical rows.
    """
    bundle = load_seed_bundle(BUNDLE_PATH)
    first = ingest_seed_bundle(master, bundle)
    assert first.ok
    second = ingest_seed_bundle(master, bundle)
    assert second.ok
    assert second.identities_recorded == 0
    assert second.identities_skipped == 9
    assert second.actions_recorded == 0
    assert second.actions_skipped == 9
    assert master._store.all_instrument_ids() == first_identities(master)


def first_identities(master: SecurityMaster) -> list[str]:
    return master._store.all_instrument_ids()


def test_the_seed_contains_a_delisting_for_the_survivorship_detector(
    master: SecurityMaster,
) -> None:
    """The corpus is not arbitrary: TWTR exists so the survivorship detector
    has a real disappearance to find, and the detector's absence test
    (no delisted instruments in the universe) is exercised against a book
    that actually contains one."""
    ingest_seed_bundle(master, load_seed_bundle(BUNDLE_PATH))
    assert "US90184L1026" in master._store.all_instrument_ids()
    listed = master.as_of("US90184L1026", datetime(2022, 6, 1, tzinfo=UTC))
    assert listed is not None
    assert listed.ticker == "TWTR"
    assert listed.status.value == "ACTIVE"
    delisted = master.as_of("US90184L1026", datetime(2022, 12, 1, tzinfo=UTC))
    assert delisted is not None
    assert delisted.status.value == "DELISTED"
    # Two versions: the transition superseded the listing rather than
    # deleting it, so the history shows what was true when.
    assert len(master.versions("US90184L1026")) == 2


def test_the_seed_contains_a_symbol_change_with_stable_identity(
    master: SecurityMaster,
) -> None:
    """FB became META; the instrument did not. A backtest joining on the new
    ticker without the old history is the truncation the contamination
    detector's symbol-change case exists to catch."""
    ingest_seed_bundle(master, load_seed_bundle(BUNDLE_PATH))
    before = master.as_of("US30303M1027", datetime(2022, 1, 1, tzinfo=UTC))
    after = master.as_of("US30303M1027", datetime(2023, 1, 1, tzinfo=UTC))
    assert before is not None and after is not None
    assert before.ticker == "FB"
    assert after.ticker == "META"
    assert before.instrument_id == after.instrument_id


def test_the_seed_splits_replay_through_the_adjustment_engine(
    master: SecurityMaster,
) -> None:
    """The corpus must justify the adjustment engine, not just the identity
    table: a known split must reproduce its factor exactly."""
    from decimal import Decimal

    from core.security_master import CorporateActionEngine

    ingest_seed_bundle(master, load_seed_bundle(BUNDLE_PATH))
    engine = CorporateActionEngine(master.actions("US0378331005"))
    factor = engine.adjustment(
        "US0378331005",
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert factor is not None
    assert factor.price_factor == Decimal("0.25")
    assert factor.applied == 1


def test_every_seed_record_carries_a_source(master: SecurityMaster) -> None:
    """Unsourced rows are rumours. The bundle requires a source per record so
    the master never holds an assertion nobody made."""
    bundle = load_seed_bundle(BUNDLE_PATH)
    assert all("source" in r for r in bundle["instruments"])
    assert all("source" in r for r in bundle["corporate_actions"])
    report = ingest_seed_bundle(master, bundle)
    assert report.ok
    assert master.current("US0378331005").source == "aios-bootstrap-v1"


# ══════════════════════════════════════════════════════════════════════════
# Validation precedes writing
# ══════════════════════════════════════════════════════════════════════════


def test_a_bundle_with_one_bad_row_records_nothing(master: SecurityMaster) -> None:
    """A half-populated master is worse than an empty one: its gaps look like
    absences. All-or-nothing per bundle, with the bad row named."""
    bundle = load_seed_bundle(BUNDLE_PATH)
    bundle["instruments"] = list(bundle["instruments"]) + [
        {"instrument_id": "BROKEN", "ticker": "???"}
    ]
    report = ingest_seed_bundle(master, bundle)
    assert not report.ok
    assert any("instruments[9]" in e for e in report.errors)
    assert master._store.all_instrument_ids() == []
    assert master.actions("US0378331005") == []


def test_a_split_without_ratios_is_refused_with_the_field_named(
    master: SecurityMaster,
) -> None:
    bundle = load_seed_bundle(BUNDLE_PATH)
    bundle["corporate_actions"] = [
        {
            "action_id": "BAD-SPLIT",
            "instrument_id": "US0378331005",
            "action_type": "SPLIT",
            "announced_at": "2020-07-30T20:30:00+00:00",
            "effective_at": "2020-08-31T13:30:00+00:00",
            "source": "test",
        }
    ]
    report = ingest_seed_bundle(master, bundle)
    assert not report.ok
    assert any("ratio" in e for e in report.errors)
    assert master._store.all_instrument_ids() == []


def test_an_action_effective_before_announcement_is_refused(
    master: SecurityMaster,
) -> None:
    """Time travel in the corpus is a data bug, and ingesting it would bake
    the bug into every backtest that replays the action."""
    bundle = {
        "bundle_id": "bad-time",
        "instruments": [],
        "corporate_actions": [
            {
                "action_id": "BACKWARDS",
                "instrument_id": "X",
                "action_type": "DIVIDEND",
                "announced_at": "2024-06-01T00:00:00+00:00",
                "effective_at": "2024-05-01T00:00:00+00:00",
                "cash_amount": "0.10",
                "source": "test",
            }
        ],
    }
    report = ingest_seed_bundle(master, bundle)
    assert not report.ok
    assert any("announced" in e for e in report.errors)


def test_unknown_top_level_keys_are_refused_not_ignored(tmp_path: Path) -> None:
    """An unknown section is usually a renamed section whose records would
    otherwise be silently dropped. Refuse the envelope."""
    path = tmp_path / "weird.json"
    path.write_text(
        json.dumps({"bundle_id": "x", "equities": []}), encoding="utf-8"
    )
    with pytest.raises(SeedIngestError, match="unknown top-level keys"):
        load_seed_bundle(path)


def test_a_missing_file_is_refused_with_its_path(tmp_path: Path) -> None:
    with pytest.raises(SeedIngestError, match="not found"):
        load_seed_bundle(tmp_path / "absent.json")


def test_malformed_json_is_refused_with_its_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SeedIngestError, match="not valid JSON"):
        load_seed_bundle(path)


def test_a_bundle_without_an_id_is_refused(master: SecurityMaster) -> None:
    with pytest.raises(SeedIngestError, match="bundle_id"):
        ingest_seed_bundle(master, {"instruments": []})


# ══════════════════════════════════════════════════════════════════════════
# Immutability at ingest time
# ══════════════════════════════════════════════════════════════════════════


def test_rewriting_an_action_under_its_id_is_refused(master: SecurityMaster) -> None:
    """A corporate action that changed after the fact is a correction with a
    new action_id, not an edit. The report carries the refusal; the stored
    action is untouched."""
    ingest_seed_bundle(master, load_seed_bundle(BUNDLE_PATH))
    forged = {
        "bundle_id": "forgery",
        "instruments": [],
        "corporate_actions": [
            {
                "action_id": "AAPL-SPLIT-20200831",
                "instrument_id": "US0378331005",
                "action_type": "SPLIT",
                "announced_at": "2020-07-30T20:30:00+00:00",
                "effective_at": "2020-08-31T13:30:00+00:00",
                "ratio_old": "1",
                "ratio_new": "2",
                "source": "forgery",
            }
        ],
    }
    report = ingest_seed_bundle(master, forged)
    assert not report.ok
    assert any("AAPL-SPLIT-20200831" in e for e in report.errors)
    stored = [a for a in master.actions("US0378331005") if a.action_id == "AAPL-SPLIT-20200831"]
    assert len(stored) == 1
    assert str(stored[0].ratio_new) == "4"


def test_ingest_accepts_a_path_or_a_dict(master: SecurityMaster) -> None:
    """Both call shapes work: operators pass paths, tests pass dicts."""
    by_path = ingest_seed_bundle(master, BUNDLE_PATH)
    assert by_path.ok
    by_dict = ingest_seed_bundle(master, load_seed_bundle(BUNDLE_PATH))
    assert by_dict.ok
    assert by_dict.identities_skipped == 9
    assert by_dict.identities_skipped == by_path.identities_recorded
