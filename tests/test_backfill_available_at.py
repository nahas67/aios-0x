"""Backfill assigns knowability; it never invents it (goal G030).

Outbox rows without ``available_at`` are ``as_of_unknown`` and excluded from
evidence. Some of those rows have witnesses — ``published_at`` (knowable then
at the latest) or ``occurred_at`` (knowable no earlier) — and for those, the
timestamp is unrecorded rather than unknown. This suite pins the policy that
separates the two cases, and the disciplines that keep a backfill honest:
dry-run by default, present values never overwritten (re-checked at apply
time, not just at plan time), every derivation carrying its source field and
policy id, and rows with no witness left alone rather than guessed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backfill_available_at import (
    BACKFILL_POLICY_ID,
    apply_backfill,
    main,
    plan_backfill,
)


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "fin.db")
    conn.execute(
        "CREATE TABLE event_outbox ("
        " event_id TEXT PRIMARY KEY, occurred_at TEXT, published_at TEXT,"
        " available_at TEXT, status TEXT)"
    )
    conn.executemany(
        "INSERT INTO event_outbox (event_id, occurred_at, published_at, available_at, status)"
        " VALUES (?, ?, ?, ?, 'PENDING')",
        [
            # Published: the system demonstrably held it then.
            ("e-pub", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:05+00:00", None),
            # Occurred only: lower bound on knowability, flagged as fallback.
            ("e-occ", "2024-01-02T00:00:00+00:00", None, None),
            # Neither: unfillable, stays unknown.
            ("e-bare", None, None, None),
            # Already present: must never be touched.
            ("e-kept", "2024-01-03T00:00:00+00:00", "2024-01-03T00:00:05+00:00",
             "2024-01-03T00:00:05+00:00"),
            # Clock skew: published before occurred. Anomalous but bounded.
            ("e-skew", "2024-01-04T00:00:10+00:00", "2024-01-04T00:00:00+00:00", None),
        ],
    )
    conn.commit()
    return conn


def _value(conn: sqlite3.Connection, event_id: str) -> str | None:
    row = conn.execute(
        "SELECT available_at FROM event_outbox WHERE event_id = ?", (event_id,)
    ).fetchone()
    return None if row is None else row[0]


# ══════════════════════════════════════════════════════════════════════════
# Planning: reads only, names everything
# ══════════════════════════════════════════════════════════════════════════


def test_plan_derives_from_the_right_witness(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        plan = plan_backfill(conn)
        by_id = {d.event_id: d for d in plan.derivations}
        assert set(by_id) == {"e-pub", "e-occ", "e-bare", "e-skew"}
        assert by_id["e-pub"].source_field == "published_at"
        assert by_id["e-pub"].derived_at == "2024-01-01T00:00:05+00:00"
        assert by_id["e-occ"].source_field == "occurred_at-fallback"
        assert by_id["e-occ"].derived_at == "2024-01-02T00:00:00+00:00"
        assert by_id["e-bare"].derived_at is None
        assert by_id["e-skew"].anomaly is True
        assert all(d.policy_id == BACKFILL_POLICY_ID for d in by_id.values())
        assert _value(conn, "e-pub") is None
    finally:
        conn.close()


def test_plan_ignores_rows_already_present(tmp_path: Path) -> None:
    """Planning reads only rows lacking available_at: the present are not
    even candidates, so a plan can never propose overwriting them."""
    conn = _db(tmp_path)
    try:
        plan = plan_backfill(conn)
        assert "e-kept" not in {d.event_id for d in plan.derivations}
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# Applying: dry-run by default, never clobbers
# ══════════════════════════════════════════════════════════════════════════


def test_dry_run_changes_nothing_but_reports(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        report = apply_backfill(conn, plan_backfill(conn), dry_run=True)
        assert report.dry_run is True
        assert report.filled == 3
        assert report.unfillable == 1
        assert "would fill" in report.summary()
        assert _value(conn, "e-pub") is None
    finally:
        conn.close()


def test_apply_fills_and_leaves_the_present_alone(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        report = apply_backfill(conn, plan_backfill(conn), dry_run=False)
        assert report.dry_run is False
        assert report.filled == 3
        assert report.unfillable == 1
        assert "3 filled" in report.summary()
        assert _value(conn, "e-pub") == "2024-01-01T00:00:05+00:00"
        assert _value(conn, "e-occ") == "2024-01-02T00:00:00+00:00"
        assert _value(conn, "e-bare") is None
        assert _value(conn, "e-kept") == "2024-01-03T00:00:05+00:00"
    finally:
        conn.close()


def test_apply_rechecks_presence_at_write_time(tmp_path: Path) -> None:
    """A row filled between plan and apply is skipped, not clobbered: the
    UPDATE carries its own IS NULL guard, so the plan going stale cannot
    overwrite a value recorded after it was made."""
    conn = _db(tmp_path)
    try:
        plan = plan_backfill(conn)
        conn.execute(
            "UPDATE event_outbox SET available_at = ? WHERE event_id = ?",
            ("2024-01-01T00:00:07+00:00", "e-pub"),
        )
        conn.commit()
        report = apply_backfill(conn, plan, dry_run=False)
        assert report.filled == 2
        assert report.skipped_already_present == 1
        assert _value(conn, "e-pub") == "2024-01-01T00:00:07+00:00"
    finally:
        conn.close()


def test_rerun_is_a_no_op(tmp_path: Path) -> None:
    """Idempotent: a second apply finds nothing to do and says so."""
    conn = _db(tmp_path)
    try:
        apply_backfill(conn, plan_backfill(conn), dry_run=False)
        second = apply_backfill(conn, plan_backfill(conn), dry_run=False)
        assert second.filled == 0
        assert second.unfillable == 1
    finally:
        conn.close()


def test_unknown_dialect_is_refused(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        with pytest.raises(ValueError, match="unknown dialect"):
            apply_backfill(conn, plan_backfill(conn), dialect="oracle", dry_run=True)
    finally:
        conn.close()


def test_report_artifact_is_complete_json(tmp_path: Path) -> None:
    """The report is the per-row record the schema has no column for: every
    derivation with its source field, policy, and anomaly flag."""
    conn = _db(tmp_path)
    try:
        report = apply_backfill(conn, plan_backfill(conn), dry_run=True)
        payload = json.loads(report.to_json())
        assert payload["policy_id"] == BACKFILL_POLICY_ID
        assert payload["dry_run"] is True
        assert payload["filled"] == 3
        by_id = {d["event_id"]: d for d in payload["derivations"]}
        assert by_id["e-skew"]["anomaly"] is True
        assert by_id["e-bare"]["derived_at"] is None
    finally:
        conn.close()


def test_cli_dry_run_by_default(tmp_path: Path, capsys) -> None:
    """The command-line entry point dry-runs unless --apply is passed: the
    safe behaviour must be the default, not a flag the operator remembers."""
    conn = _db(tmp_path)
    conn.close()
    assert main(["--db", str(tmp_path / "fin.db")]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "would fill" in out
    check = sqlite3.connect(tmp_path / "fin.db")
    try:
        assert _value(check, "e-pub") is None
    finally:
        check.close()
