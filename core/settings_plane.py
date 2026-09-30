"""Versioned settings plane (plan section 4, item B1).

Stores the 96-field ``SystemSettings`` JSON blob opaquely in SQLite, one row
per version, following the ``core/persistence.py`` convention
(``CREATE TABLE IF NOT EXISTS`` + re-entrant lock + busy timeout). Every write
appends a ``SETTINGS_UPDATED`` event to the hash-chained audit store so a
settings change is tamper-evident like any other operator action.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The plane mirrors the server's bounded-body convention (``MAX_REQUEST_BYTES``
# in ``api/server.py``): the blob must be a JSON object and is capped well
# below runaway-payload territory.
SETTINGS_MAX_BYTES = 256 * 1024


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SettingsPlane:
    """Opaque versioned store for the SystemSettings JSON blob."""

    def __init__(self, db_path: str | Path, store: Any = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout = 10000")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings_versions (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        # Audit sink: any object with ``append_event(kind, ref_id, payload)``
        # (``BaseMemoryStore``). ``None`` disables the audit write; reads still work.
        self._store = store

    def get_settings(self) -> dict[str, Any]:
        """Latest blob, or ``{}`` when nothing has been stored yet."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM settings_versions ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {}
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, dict) else {}

    def latest(self) -> dict[str, Any]:
        """Latest blob with version metadata (``version`` 0 when empty)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT version, payload_json, updated_by, updated_at "
                "FROM settings_versions ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {"version": 0, "settings": {}}
        payload = json.loads(row["payload_json"])
        return {
            "version": int(row["version"]),
            "settings": payload if isinstance(payload, dict) else {},
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def put_settings(self, payload: dict[str, Any], actor: str) -> int:
        """Validate, store as a new version and audit; returns the version."""
        if not isinstance(payload, dict):
            raise ValueError("settings payload must be a JSON object")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(canonical.encode("utf-8")) > SETTINGS_MAX_BYTES:
            raise ValueError(
                f"settings payload exceeds {SETTINGS_MAX_BYTES} bytes"
            )
        updated_by = (actor or "").strip()[:128] or "unknown"
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO settings_versions (payload_json, updated_by, updated_at) "
                "VALUES (?, ?, ?)",
                (canonical, updated_by, _utc_now_iso()),
            )
            self._conn.commit()
            version = int(cur.lastrowid or 0)
        if self._store is not None:
            self._store.append_event(
                "SETTINGS_UPDATED",
                str(version),
                {"version": version, "updated_by": updated_by},
            )
        return version

    def close(self) -> None:
        self._conn.close()
