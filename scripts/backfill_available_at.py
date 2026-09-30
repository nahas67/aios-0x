"""Backfill available_at on outbox rows that lack it (goal G030).

Rows without ``available_at`` are ``as_of_unknown`` and excluded from
evidence — which is correct for rows whose knowability is genuinely unknown,
and wrong for rows where it is merely unrecorded. The outbox carries two
witnesses: ``published_at`` (when the system published the event — knowable
then at the latest) and ``occurred_at`` (when the event happened in the
world — knowable no earlier). The backfill policy derives the former from
the latter in that priority order:

* ``published_at`` present → ``available_at = published_at`` (source:
  ``published_at``). Publication is the latest moment the system
  demonstrably held the datum.
* else ``occurred_at`` → ``available_at = occurred_at`` (source:
  ``occurred_at-fallback``, flagged). Occurrence is a lower bound on
  knowability and may predate actual availability by an unmeasured lag —
  the flag keeps that uncertainty visible instead of laundering it.
* else neither → unfillable. The row stays ``as_of_unknown`` forever rather
  than receiving an invented timestamp. An invented timestamp would admit
  the row to evidence on false pretenses, which is worse than exclusion.

Three properties make re-runs safe: present values are never overwritten
(the WHERE clause re-checks at apply time, so rows filled between plan and
apply are skipped and reported); every derived value carries its source
field and the policy id that produced it, in a report artifact rather than
in row metadata the schema has no column for; dry-run is the default and
apply is explicit.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "BACKFILL_POLICY_ID",
    "BackfillPlan",
    "BackfillReport",
    "RowDerivation",
    "apply_backfill",
    "plan_backfill",
]

#: The policy this script implements. Recorded on every derivation so a row
#: filled today can be traced to the rule that filled it, and so a future
#: policy change does not retroactively claim old rows.
BACKFILL_POLICY_ID = "outbox-available-at-v1"


@dataclass(frozen=True)
class RowDerivation:
    """How one row's available_at was derived, or why it was not."""

    event_id: str
    derived_at: str | None
    source_field: str
    policy_id: str = BACKFILL_POLICY_ID
    anomaly: bool = False
    detail: str = ""


@dataclass
class BackfillPlan:
    """Rows to fill, computed without writing anything."""

    derivations: list[RowDerivation] = field(default_factory=list)

    @property
    def fillable(self) -> list[RowDerivation]:
        return [d for d in self.derivations if d.derived_at is not None]

    @property
    def unfillable(self) -> list[RowDerivation]:
        return [d for d in self.derivations if d.derived_at is None]


@dataclass
class BackfillReport:
    """What one run did — or, on dry-run, what it would do."""

    policy_id: str = BACKFILL_POLICY_ID
    filled: int = 0
    skipped_already_present: int = 0
    unfillable: int = 0
    derivations: list[RowDerivation] = field(default_factory=list)
    dry_run: bool = True

    def summary(self) -> str:
        verb = "would fill" if self.dry_run else "filled"
        return (
            f"policy {self.policy_id} ({'dry-run' if self.dry_run else 'applied'}): "
            f"{self.filled} {verb}, "
            f"{self.skipped_already_present} already present, "
            f"{self.unfillable} unfillable"
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "policy_id": self.policy_id,
                "dry_run": self.dry_run,
                "filled": self.filled,
                "skipped_already_present": self.skipped_already_present,
                "unfillable": self.unfillable,
                "derivations": [
                    {
                        "event_id": d.event_id,
                        "derived_at": d.derived_at,
                        "source_field": d.source_field,
                        "policy_id": d.policy_id,
                        "anomaly": d.anomaly,
                        "detail": d.detail,
                    }
                    for d in self.derivations
                ],
            },
            indent=2,
            sort_keys=True,
        )


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def plan_backfill(connection: Any) -> BackfillPlan:
    """Compute derivations for every row lacking available_at. Reads only."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT event_id, occurred_at, published_at FROM event_outbox "
            "WHERE available_at IS NULL ORDER BY occurred_at"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    plan = BackfillPlan()
    for row in rows:
        event_id, occurred_raw, published_raw = row[0], row[1], row[2]
        occurred = _parse(occurred_raw)
        published = _parse(published_raw)
        if published is not None:
            anomaly = occurred is not None and published < occurred
            plan.derivations.append(
                RowDerivation(
                    event_id=str(event_id),
                    derived_at=published.isoformat(),
                    source_field="published_at",
                    anomaly=anomaly,
                    detail=(
                        "published before occurrence: clock skew between producer "
                        "and publisher; used publication as the knowability bound"
                        if anomaly
                        else "publication is the latest demonstrably-held moment"
                    ),
                )
            )
        elif occurred is not None:
            plan.derivations.append(
                RowDerivation(
                    event_id=str(event_id),
                    derived_at=occurred.isoformat(),
                    source_field="occurred_at-fallback",
                    detail="no publication record: occurrence is a lower bound on "
                    "knowability and may predate availability by an unmeasured lag",
                )
            )
        else:
            plan.derivations.append(
                RowDerivation(
                    event_id=str(event_id),
                    derived_at=None,
                    source_field="none",
                    detail="no occurred_at and no published_at: unfillable, "
                    "stays as_of_unknown rather than receiving an invented time",
                )
            )
    return plan


def apply_backfill(
    connection: Any, plan: BackfillPlan, *, dialect: str = "sqlite", dry_run: bool = True
) -> BackfillReport:
    """Write the plan's derivations. Present values are never overwritten:
    the UPDATE re-checks ``available_at IS NULL``, so rows filled between
    plan and apply are skipped and counted rather than clobbered."""
    if dialect not in {"sqlite", "postgres"}:
        raise ValueError(f"unknown dialect {dialect!r}: expected 'sqlite' or 'postgres'")
    mark = "?" if dialect == "sqlite" else "%s"
    report = BackfillReport()
    cursor = connection.cursor()
    try:
        for derivation in plan.fillable:
            if dry_run:
                continue
            cursor.execute(
                f"UPDATE event_outbox SET available_at = {mark} "
                f"WHERE event_id = {mark} AND available_at IS NULL",
                (derivation.derived_at, derivation.event_id),
            )
            if cursor.rowcount and cursor.rowcount > 0:
                report.filled += 1
            else:
                report.skipped_already_present += 1
        if not dry_run:
            _commit(connection)
    finally:
        cursor.close()
    report.unfillable = len(plan.unfillable)
    report.derivations = list(plan.derivations)
    report.dry_run = dry_run
    if dry_run:
        # Nothing written: report what would happen rather than zeros that
        # read as "nothing to do".
        report.filled = len(plan.fillable)
        report.skipped_already_present = 0
    return report


def _commit(connection: Any) -> None:
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill available_at on outbox rows that lack it. Dry-run by default."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--db", help="SQLite file path")
    target.add_argument("--dsn", help="PostgreSQL DSN")
    parser.add_argument("--apply", action="store_true", help="write; without it, dry-run only")
    parser.add_argument("--report-out", default="", help="write the JSON report artifact here")
    args = parser.parse_args(argv)

    if args.db:
        import sqlite3

        connection = sqlite3.connect(args.db)
        dialect = "sqlite"
    else:
        import psycopg

        connection = psycopg.connect(args.dsn)
        dialect = "postgres"
    try:
        plan = plan_backfill(connection)
        report = apply_backfill(connection, plan, dialect=dialect, dry_run=not args.apply)
    finally:
        connection.close()
    print(report.summary())
    print(f"fillable: {len(plan.fillable)}, unfillable: {len(plan.unfillable)}")
    if args.report_out:
        Path(args.report_out).write_text(report.to_json(), encoding="utf-8")
        print(f"report written to {args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
