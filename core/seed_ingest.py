"""Seed ingest for the security master (vNext goal G020).

The master is empty in production until something populates it, and an empty
master makes every backtest provisional: no identity to join on, no
delistings for the survivorship detector to find, no splits for the
adjustment engine to replay. This module is the something.

A seed bundle is versioned JSON: instruments plus corporate actions, each
record carrying its own source. The repo ships a curated bootstrap corpus at
``data/seed/bootstrap_v1.json`` — eight listings, nine actions, every record
with a provenance note — and the same importer takes an external file, e.g.
an export shaped like the FinanceDatabase corpus, so scale is a matter of
pointing at a bigger file rather than a second importer.

Three properties make re-runs safe, because ingest runs at bootstrap, at
deploy, and whenever the corpus grows:

*Validation is free.* Records are parsed through the domain models, so a bad
row is refused with the model's message naming the field, not with a
constraint error from three layers down. A bundle that fails validation
records nothing — validation completes before the first write.

*Identities upsert.* ``SecurityMaster.upsert`` already treats identical
content at the same valid time as a no-op, so re-ingest of an unchanged
bundle changes nothing and ingest of a grown bundle adds only what is new.

*Actions are immutable.* ``record_action`` re-recording the same action is a
no-op; the same action_id with different content is refused rather than
repaired, because a corporate action that changed after the fact is either a
correction (which gets a new action_id) or a different event wearing an old
name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.security_master import CorporateAction, InstrumentIdentity, SecurityMaster

__all__ = [
    "SeedIngestError",
    "SeedReport",
    "ingest_seed_bundle",
    "load_seed_bundle",
]

#: Bundle keys the importer understands. Anything else is refused rather than
#: ignored: an unknown top-level key is usually a renamed section whose
#: records would otherwise be silently dropped.
_BUNDLE_KEYS = frozenset({"bundle_id", "description", "instruments", "corporate_actions"})


class SeedIngestError(RuntimeError):
    """A seed bundle was refused before anything was written."""


@dataclass
class SeedReport:
    """What one ingest run did, per record class."""

    bundle_id: str
    identities_recorded: int = 0
    identities_skipped: int = 0
    actions_recorded: int = 0
    actions_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def total_recorded(self) -> int:
        return self.identities_recorded + self.actions_recorded

    def summary(self) -> str:
        base = (
            f"bundle {self.bundle_id}: {self.identities_recorded} identities "
            f"({self.identities_skipped} already current), {self.actions_recorded} "
            f"actions ({self.actions_skipped} already recorded)"
        )
        if self.errors:
            return base + f"; {len(self.errors)} error(s): " + "; ".join(self.errors[:3])
        return base + "; clean"


def load_seed_bundle(path: str | Path) -> dict[str, Any]:
    """Parse and shape-check a bundle. Records are validated later, by the
    models, at ingest time — this checks the envelope only."""
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SeedIngestError(f"seed bundle not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise SeedIngestError(f"seed bundle {target} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SeedIngestError(f"seed bundle {target} must be a JSON object")
    unknown = set(raw) - _BUNDLE_KEYS
    if unknown:
        raise SeedIngestError(
            f"seed bundle {target} has unknown top-level keys {sorted(unknown)}; "
            "refused rather than partially ingested"
        )
    if not raw.get("bundle_id"):
        raise SeedIngestError(f"seed bundle {target} carries no bundle_id")
    for key in ("instruments", "corporate_actions"):
        records = raw.get(key, [])
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise SeedIngestError(f"seed bundle {target}: {key!r} must be a list of objects")
    return raw


def ingest_seed_bundle(
    master: SecurityMaster, bundle: dict[str, Any] | str | Path
) -> SeedReport:
    """Validate, then record, a seed bundle. Nothing is written until every
    record parses.

    Two phases, because a bundle that fails halfway leaves a half-populated
    master whose gaps look like absences: phase one parses every record
    through its model and collects failures; phase two writes only when phase
    one is clean. A bundle with one bad row records nothing, and the report
    names the row.
    """
    raw = load_seed_bundle(bundle) if isinstance(bundle, (str, Path)) else bundle
    if not isinstance(raw, dict) or not raw.get("bundle_id"):
        raise SeedIngestError("a seed bundle must be a dict carrying bundle_id")
    report = SeedReport(bundle_id=str(raw["bundle_id"]))

    identities: list[InstrumentIdentity] = []
    for index, record in enumerate(raw.get("instruments", [])):
        try:
            identities.append(InstrumentIdentity.model_validate(record))
        except Exception as exc:
            report.errors.append(f"instruments[{index}]: {exc}")
    actions: list[CorporateAction] = []
    for index, record in enumerate(raw.get("corporate_actions", [])):
        try:
            actions.append(CorporateAction.model_validate(record))
        except Exception as exc:
            report.errors.append(f"corporate_actions[{index}]: {exc}")
    if report.errors:
        return report

    for identity in identities:
        try:
            # upsert returns the pre-existing version object when content is
            # identical and the passed record itself when it wrote: identity
            # of the return value is the signal, because comparing digests
            # would trivially match in the write case (the store returns what
            # it was given). A re-run must report skips, not re-record the
            # whole book.
            stored = master.upsert(identity)
            if stored is identity:
                report.identities_recorded += 1
            else:
                report.identities_skipped += 1
        except Exception as exc:
            report.errors.append(f"identity {identity.instrument_id}: {exc}")
    for action in actions:
        try:
            before = len(master.actions(action.instrument_id))
            master.record_action(action)
            after = len(master.actions(action.instrument_id))
            if after == before:
                report.actions_skipped += 1
            else:
                report.actions_recorded += 1
        except Exception as exc:
            report.errors.append(f"action {action.action_id}: {exc}")
    return report
