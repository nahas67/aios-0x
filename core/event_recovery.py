"""Event recovery (original architecture §26): durable replay from the log.

"Event Failure → durable recovery/replay." The hash-chained event log IS the
durable transport; this module is its read side:

- checkpoint(store)          -> latest seq (a consumer's bookmark)
- EventReplay(store, cursor) -> ordered batches of everything after the mark

A crashed or restarted consumer resumes with ``after_seq=checkpoint`` and
receives exactly what it missed: nothing twice, nothing skipped. This is also
the seam where a future multi-process deployment attaches — a service in
another process consumes the same log through the same calls.
"""

from dataclasses import dataclass
from typing import Any

from core.persistence import BaseMemoryStore


def checkpoint(store: BaseMemoryStore) -> int:
    """Latest sequence number in the log (0 when empty)."""
    events = store.read_events(after_seq=0, limit=1_000_000)
    return events[-1]["seq"] if events else 0


@dataclass
class EventReplay:
    """Cursor-based reader over the durable log."""

    store: BaseMemoryStore
    after_seq: int = 0

    def next(self, limit: int = 500) -> list[dict[str, Any]]:
        """Next ascending batch strictly after the cursor; advances it."""
        batch = self.store.read_events(after_seq=self.after_seq, limit=limit)
        if batch:
            self.after_seq = batch[-1]["seq"]
        return batch

    def drain(self, kind_prefix: str | None = None) -> list[dict[str, Any]]:
        """Everything remaining (optionally filtered by kind prefix), in order."""
        out: list[dict[str, Any]] = []
        while True:
            batch = self.next()
            if not batch:
                break
            if kind_prefix is None:
                out.extend(batch)
            else:
                out.extend(e for e in batch if e["kind"].startswith(kind_prefix))
        return out
