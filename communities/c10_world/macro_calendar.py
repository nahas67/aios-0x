"""Community 10: macro calendar - user-supplied scheduled-event feed.

CSV columns:
    event_id,title,event_time,consensus,prior,actual,unit,affected_symbols,is_simulated
- event_time: ISO-8601 with timezone
- affected_symbols: semicolon-separated list
- actual may be empty pre-release; expectation processing skips such rows
"""

import csv
from datetime import datetime
from pathlib import Path

from schemas.contracts import ScheduledEvent

_REQUIRED = {
    "event_id",
    "title",
    "event_time",
    "consensus",
    "prior",
    "actual",
    "unit",
    "affected_symbols",
    "is_simulated",
}
_OPTIONAL_BOOL = {"higher_is_better"}


def _parse_dt(raw: str) -> datetime:
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError(f"calendar timestamps must carry timezone: {raw!r}")
    return ts


def _opt_float(raw: str) -> float | None:
    raw = raw.strip()
    return float(raw) if raw else None


def _parse_bool(raw: str, default: bool) -> bool:
    raw = (raw or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes"}


class FileMacroCalendar:
    """Loads and replays a scheduled-event calendar against a replay clock."""

    def __init__(self, csv_path: str | Path) -> None:
        self._events: dict[str, ScheduledEvent] = {}
        self._returned: set[str] = set()
        self._load(Path(csv_path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"macro calendar missing: {path}")
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = _REQUIRED - columns
            if missing:
                raise ValueError(f"{path}: calendar missing columns {sorted(missing)}")
            for raw in reader:
                event = ScheduledEvent(
                    event_id=raw["event_id"].strip(),
                    title=raw["title"].strip(),
                    event_time=_parse_dt(raw["event_time"]),
                    consensus=_opt_float(raw["consensus"]),
                    prior=_opt_float(raw["prior"]),
                    actual=_opt_float(raw["actual"]),
                    unit=(raw["unit"] or "").strip(),
                    higher_is_better=_parse_bool(raw.get("higher_is_better", ""), default=True),
                    affected_symbols=[
                        s.strip() for s in (raw["affected_symbols"] or "").split(";") if s.strip()
                    ],
                    source_tag=f"file:{path.name}",
                    is_simulated=(raw["is_simulated"] or "").strip().lower()
                    in {"1", "true", "yes"},
                )
                if not event.event_id or not event.title:
                    raise ValueError(f"{path}: event_id and title are required")
                self._events[event.event_id] = event

    def all_events(self) -> list[ScheduledEvent]:
        """All loaded events in chronological order."""
        return sorted(self._events.values(), key=lambda e: e.event_time)

    def due_events(self, as_of_ts: datetime) -> list[ScheduledEvent]:
        """Events with event_time <= as_of_ts not yet returned (each returns once).

        Events lacking an actual value are returned too so the scenario engine
        can publish pre-event cards; expectation processing filters them out.
        """
        due: list[ScheduledEvent] = []
        for event in self.all_events():
            if event.event_id in self._returned:
                continue
            if event.event_time <= as_of_ts:
                due.append(event)
                self._returned.add(event.event_id)
        return due
