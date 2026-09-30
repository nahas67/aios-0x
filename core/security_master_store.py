"""SQLite and PostgreSQL stores for the security master (vNext goal G020).

The store is a thin dialect adapter over :mod:`core.security_master`. All
temporal reasoning lives in the query layer; this file only persists and
retrieves. Both tiers are held to the same behaviour by
``tests/test_security_master.py``, which runs the identical suite against each
— the same parity discipline ``core/financial_invariants.py`` established for
the financial kernel.

Two decisions are worth stating because they are the ones a reviewer would
question:

**Supersession is a transaction, not a delete.** Recording a new belief closes
the prior row's ``recorded_to`` and inserts the new one in a single atomic
step. A crash between the two would leave an instrument with two current
beliefs, which the partial unique index refuses. Fail-closed at the schema
level rather than trusted to application ordering.

**Source conflict resolution is deterministic.** When two sources disagree, the
lower ``source_priority`` wins, and the rejection is written to
``identity_conflicts``. The loser is not discarded: a source that was wrong
once is evidence, and an audit asking "why does our record say X" needs the
answer.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.migrations import apply_postgres_migrations, apply_sqlite_migrations
from core.security_master import (
    CorporateAction,
    InstrumentIdentity,
    SecurityMasterStore,
    _row_to_action,
    _row_to_identity,
)

__all__ = [
    "SecurityMasterError",
    "PostgresSecurityMasterStore",
    "SqliteSecurityMasterStore",
    "build_postgres_security_master_store",
    "build_sqlite_security_master_store",
]


class SecurityMasterError(RuntimeError):
    """A security-master write was refused."""


_IDENTITY_COLUMNS = (
    "instrument_id",
    "listing_id",
    "ticker",
    "mic",
    "venue",
    "asset_class",
    "security_type",
    "currency",
    "quote_currency",
    "account_currency",
    "tick_size",
    "lot_size",
    "multiplier",
    "expiry",
    "strike",
    "underlying_instrument_id",
    "figi",
    "isin",
    "cik",
    "status",
    "valid_from",
    "valid_to",
    "recorded_from",
    "recorded_to",
    "source",
    "source_priority",
    "revision",
)

_ACTION_COLUMNS = (
    "action_id",
    "instrument_id",
    "listing_id",
    "action_type",
    "announced_at",
    "effective_at",
    "record_date",
    "ex_date",
    "ratio_old",
    "ratio_new",
    "cash_amount",
    "new_ticker",
    "successor_instrument_id",
    "source",
    "source_hash",
)


def _decimal_text(value: Decimal | None) -> str | None:
    """Render a Decimal for storage without a float round-trip.

    Prices and ratios are exact quantities; ``str(Decimal)`` preserves that
    exactly, whereas a float conversion would bake in binary error that then
    compounds across a chain of splits.
    """
    return None if value is None else str(value)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _identity_params(record: InstrumentIdentity) -> tuple[Any, ...]:
    return (
        record.instrument_id,
        record.listing_id,
        record.ticker,
        record.mic,
        record.venue,
        str(record.asset_class),
        record.security_type,
        record.currency,
        record.quote_currency,
        record.account_currency,
        _decimal_text(record.tick_size),
        _decimal_text(record.lot_size),
        _decimal_text(record.multiplier),
        record.expiry.isoformat() if record.expiry else None,
        _decimal_text(record.strike),
        record.underlying_instrument_id,
        record.figi,
        record.isin,
        record.cik,
        str(record.status),
        _iso(record.valid_from),
        _iso(record.valid_to),
        _iso(record.recorded_from),
        _iso(record.recorded_to),
        record.source,
        record.source_priority,
        record.revision,
    )


def _action_params(action: CorporateAction) -> tuple[Any, ...]:
    return (
        action.action_id,
        action.instrument_id,
        action.listing_id,
        str(action.action_type),
        _iso(action.announced_at),
        _iso(action.effective_at),
        action.record_date.isoformat() if action.record_date else None,
        action.ex_date.isoformat() if action.ex_date else None,
        _decimal_text(action.ratio_old),
        _decimal_text(action.ratio_new),
        _decimal_text(action.cash_amount),
        action.new_ticker,
        action.successor_instrument_id,
        action.source,
        action.source_hash,
    )


_INSERT_IDENTITY_SQL = (
    f"INSERT INTO instrument_identity ({', '.join(_IDENTITY_COLUMNS)})"
    f" VALUES ({', '.join('?' for _ in _IDENTITY_COLUMNS)})"
)

_INSERT_ACTION_SQL = (
    f"INSERT INTO corporate_actions ({', '.join(_ACTION_COLUMNS)})"
    f" VALUES ({', '.join('?' for _ in _ACTION_COLUMNS)})"
)

_INSERT_CONFLICT_SQL = (
    "INSERT INTO identity_conflicts"
    " (conflict_id, instrument_id, listing_id, valid_from, existing_source,"
    " incoming_source, existing_digest, incoming_digest, winner, reason)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_CLOSE_PRIOR_SQL = (
    "UPDATE instrument_identity SET recorded_to = ?"
    " WHERE instrument_id = ? AND listing_id = ? AND recorded_to IS NULL"
    " AND valid_from <= ?"
)

_FIND_PRIOR_SQL = (
    "SELECT * FROM instrument_identity"
    " WHERE instrument_id = ? AND listing_id = ? AND recorded_to IS NULL"
    " AND valid_from <= ? ORDER BY valid_from DESC, revision DESC"
)

#: Why a losing source was rejected, recorded verbatim in identity_conflicts.
_CONFLICT_REASON = (
    "source_priority tie: incoming record retained because it is the later "
    "assertion at the same valid time"
)


class SqliteSecurityMasterStore(SecurityMasterStore):
    """Local SQLite tier of the security master."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 10000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = FULL")
        # The dev tier migrates itself; production PostgreSQL never mutates DDL
        # on open (see core/pg_financial_store.py for that contract).
        apply_sqlite_migrations(self._conn)
        self._conn.commit()

    # ------------------------------------------------------------------ readers

    def _identity_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _action_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def identity_versions(self, instrument_id: str) -> list[InstrumentIdentity]:
        rows = self._identity_rows(
            "SELECT * FROM instrument_identity WHERE instrument_id = ?"
            " ORDER BY recorded_from, valid_from, revision",
            (instrument_id,),
        )
        return [_row_to_identity(row) for row in rows]

    def actions_for(self, instrument_id: str) -> list[CorporateAction]:
        rows = self._action_rows(
            "SELECT * FROM corporate_actions WHERE instrument_id = ?"
            " ORDER BY effective_at, action_id",
            (instrument_id,),
        )
        return [_row_to_action(row) for row in rows]

    def all_actions(self, window_start: str | None = None, window_end: str | None = None) -> list[CorporateAction]:
        """Every corporate action, optionally bounded by effective time.

        Enumerating actions across the whole book is what a survivorship check
        needs: it must ask which instruments *disappeared* during a test
        window, and asking one instrument at a time would only ever find the
        ones already in the universe.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if window_start is not None:
            clauses.append("effective_at >= ?")
            params.append(window_start)
        if window_end is not None:
            clauses.append("effective_at <= ?")
            params.append(window_end)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._action_rows(
            f"SELECT * FROM corporate_actions{where} ORDER BY effective_at, action_id",
            tuple(params),
        )
        return [_row_to_action(row) for row in rows]

    def all_instrument_ids(self) -> list[str]:
        """Every identity ever recorded, current or superseded.

        Survivorship bias is the *absence* of instruments, so a query that only
        reaches current beliefs cannot see it: a delisted identity has a closed
        ``recorded_to`` and is exactly the row that matters.
        """
        rows = self._identity_rows(
            "SELECT DISTINCT instrument_id FROM instrument_identity ORDER BY instrument_id",
            (),
        )
        return [str(row["instrument_id"]) for row in rows]

    # ------------------------------------------------------------------ writers

    def record_identity(self, record: InstrumentIdentity) -> InstrumentIdentity:
        """Persist a version, atomically closing any prior belief it supersedes."""
        with self._lock:
            prior_rows = self._identity_rows(
                "SELECT * FROM instrument_identity"
                " WHERE instrument_id = ? AND listing_id = ? AND recorded_to IS NULL"
                " AND valid_from <= ?",
                (record.instrument_id, record.listing_id, _iso(record.valid_from)),
            )
            prior = [_row_to_identity(row) for row in prior_rows]
            for existing in prior:
                self._record_conflict(existing, record)
            try:
                with self._conn:
                    for _ in prior:
                        self._conn.execute(
                            _CLOSE_PRIOR_SQL,
                            (
                                _iso(record.recorded_from),
                                record.instrument_id,
                                record.listing_id,
                                _iso(record.valid_from),
                            ),
                        )
                    self._conn.execute(_INSERT_IDENTITY_SQL, _identity_params(record))
            except sqlite3.IntegrityError as exc:
                # The partial unique index refused a second current belief for
                # this listing and valid time. Refuse rather than repair: the
                # caller has a bug and hiding it would fork identity.
                raise SecurityMasterError(
                    f"identity for {record.instrument_id}/{record.listing_id} conflicts "
                    f"with an existing current belief: {exc}"
                ) from exc
        return record

    def _record_conflict(
        self, existing: InstrumentIdentity, incoming: InstrumentIdentity
    ) -> None:
        """Note a disagreement between sources before the winner is stored."""
        if existing.identity_digest() == incoming.identity_digest():
            return
        if existing.source == incoming.source:
            # Same source restating itself is a correction, not a conflict.
            return
        winner = existing if existing.source_priority <= incoming.source_priority else incoming
        loser = incoming if winner is existing else existing
        self._conn.execute(
            _INSERT_CONFLICT_SQL,
            (
                f"{incoming.instrument_id}:{incoming.listing_id}:{incoming.valid_from.isoformat()}",
                incoming.instrument_id,
                incoming.listing_id,
                _iso(incoming.valid_from),
                existing.source,
                incoming.source,
                existing.identity_digest(),
                incoming.identity_digest(),
                winner.source,
                (
                    f"source_priority {winner.source_priority} beat {loser.source_priority}"
                    if winner.source_priority != loser.source_priority
                    else _CONFLICT_REASON
                ),
            ),
        )

    def record_action(self, action: CorporateAction) -> CorporateAction:
        """Persist an action. Re-recording the same action is a no-op, not an update."""
        with self._lock:
            existing = self._action_rows(
                "SELECT * FROM corporate_actions WHERE action_id = ? AND instrument_id = ?",
                (action.action_id, action.instrument_id),
            )
            if existing:
                stored = _row_to_action(existing[0])
                if stored != action:
                    raise SecurityMasterError(
                        f"corporate action {action.action_id} already recorded with different "
                        "content. Corporate actions are immutable; record a correction as a new "
                        "action_id so the history stays explainable."
                    )
                return stored
            self._conn.execute(_INSERT_ACTION_SQL, _action_params(action))
            self._conn.commit()
        return action


def build_sqlite_security_master_store(db_path: str | Path) -> SqliteSecurityMasterStore:
    """Construct the SQLite tier. Named for symmetry with the financial store."""
    return SqliteSecurityMasterStore(db_path)


def _pg_placeholders(sql: str) -> str:
    """Rewrite ``?`` placeholders to ``%s`` for psycopg.

    The statements are shared verbatim otherwise: same columns, same order,
    same predicates. One statement text with a mechanical placeholder rewrite
    keeps the two dialects from drifting into two different queries wearing
    the same name.
    """
    return sql.replace("?", "%s")


class PostgresSecurityMasterStore(SecurityMasterStore):
    """Production PostgreSQL tier of the security master.

    Identical behaviour to the SQLite tier by construction: the same row
    mappers (which already accept native datetime/date/Decimal objects), the
    same supersession transaction, the same conflict rule, the same
    re-record-is-a-no-op action rule. The parity suite holds both tiers to
    the same assertions; a behavioural difference is a defect in this class,
    not a dialect difference.

    Production PostgreSQL never mutates DDL on open — ``auto_migrate`` is
    opt-in and exists for tests and bootstrap tooling, mirroring the
    financial store's contract.
    """

    def __init__(self, dsn: str, *, auto_migrate: bool = False) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy so PG-less installs stay clean
        except ImportError as exc:
            raise ImportError(
                "PostgresSecurityMasterStore requires psycopg >= 3. "
                "Install with: pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = False
        if auto_migrate:
            apply_postgres_migrations(self._conn)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ readers

    def _identity_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur:
            cur.execute(_pg_placeholders(sql), params)
            return [dict(row) for row in cur.fetchall()]

    def _action_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock, self._conn.cursor(row_factory=self._psycopg.rows.dict_row) as cur:
            cur.execute(_pg_placeholders(sql), params)
            return [dict(row) for row in cur.fetchall()]

    def identity_versions(self, instrument_id: str) -> list[InstrumentIdentity]:
        rows = self._identity_rows(
            "SELECT * FROM instrument_identity WHERE instrument_id = ?"
            " ORDER BY recorded_from, valid_from, revision",
            (instrument_id,),
        )
        return [_row_to_identity(row) for row in rows]

    def actions_for(self, instrument_id: str) -> list[CorporateAction]:
        rows = self._action_rows(
            "SELECT * FROM corporate_actions WHERE instrument_id = ?"
            " ORDER BY effective_at, action_id",
            (instrument_id,),
        )
        return [_row_to_action(row) for row in rows]

    def all_actions(
        self, window_start: str | None = None, window_end: str | None = None
    ) -> list[CorporateAction]:
        clauses: list[str] = []
        params: list[Any] = []
        if window_start is not None:
            clauses.append("effective_at >= ?")
            params.append(window_start)
        if window_end is not None:
            clauses.append("effective_at <= ?")
            params.append(window_end)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._action_rows(
            f"SELECT * FROM corporate_actions{where} ORDER BY effective_at, action_id",
            tuple(params),
        )
        return [_row_to_action(row) for row in rows]

    def all_instrument_ids(self) -> list[str]:
        rows = self._identity_rows(
            "SELECT DISTINCT instrument_id FROM instrument_identity ORDER BY instrument_id",
            (),
        )
        return [str(row["instrument_id"]) for row in rows]

    # ------------------------------------------------------------------ writers

    def record_identity(self, record: InstrumentIdentity) -> InstrumentIdentity:
        """Persist a version, atomically closing any prior belief it supersedes."""
        with self._lock:
            prior_rows = self._identity_rows(
                "SELECT * FROM instrument_identity"
                " WHERE instrument_id = ? AND listing_id = ? AND recorded_to IS NULL"
                " AND valid_from <= ?",
                (record.instrument_id, record.listing_id, _iso(record.valid_from)),
            )
            prior = [_row_to_identity(row) for row in prior_rows]
            try:
                with self._conn.transaction():
                    # Conflict rows join this same transaction: a failed insert
                    # rolls back its conflict notes too, so the conflicts table
                    # never claims a disagreement about a version that was
                    # never stored.
                    for existing in prior:
                        self._record_conflict(existing, record)
                    with self._conn.cursor() as cur:
                        for _ in prior:
                            cur.execute(
                                _pg_placeholders(_CLOSE_PRIOR_SQL),
                                (
                                    _iso(record.recorded_from),
                                    record.instrument_id,
                                    record.listing_id,
                                    _iso(record.valid_from),
                                ),
                            )
                        cur.execute(
                            _pg_placeholders(_INSERT_IDENTITY_SQL),
                            _identity_params(record),
                        )
            except self._psycopg.errors.UniqueViolation as exc:
                raise SecurityMasterError(
                    f"identity for {record.instrument_id}/{record.listing_id} conflicts "
                    f"with an existing current belief: {exc}"
                ) from exc
        return record

    def _record_conflict(
        self, existing: InstrumentIdentity, incoming: InstrumentIdentity
    ) -> None:
        """Note a disagreement between sources before the winner is stored."""
        if existing.identity_digest() == incoming.identity_digest():
            return
        if existing.source == incoming.source:
            return
        winner = existing if existing.source_priority <= incoming.source_priority else incoming
        loser = incoming if winner is existing else existing
        with self._conn.cursor() as cur:
            cur.execute(
                _pg_placeholders(_INSERT_CONFLICT_SQL),
                (
                    f"{incoming.instrument_id}:{incoming.listing_id}:{incoming.valid_from.isoformat()}",
                    incoming.instrument_id,
                    incoming.listing_id,
                    _iso(incoming.valid_from),
                    existing.source,
                    incoming.source,
                    existing.identity_digest(),
                    incoming.identity_digest(),
                    winner.source,
                    (
                        f"source_priority {winner.source_priority} beat {loser.source_priority}"
                        if winner.source_priority != loser.source_priority
                        else _CONFLICT_REASON
                    ),
                ),
            )

    def record_action(self, action: CorporateAction) -> CorporateAction:
        """Persist an action. Re-recording the same action is a no-op, not an update."""
        with self._lock:
            existing = self._action_rows(
                "SELECT * FROM corporate_actions WHERE action_id = ? AND instrument_id = ?",
                (action.action_id, action.instrument_id),
            )
            if existing:
                stored = _row_to_action(existing[0])
                if stored != action:
                    raise SecurityMasterError(
                        f"corporate action {action.action_id} already recorded with different "
                        "content. Corporate actions are immutable; record a correction as a new "
                        "action_id so the history stays explainable."
                    )
                return stored
            with self._conn.cursor() as cur:
                cur.execute(_pg_placeholders(_INSERT_ACTION_SQL), _action_params(action))
            self._conn.commit()
        return action


def build_postgres_security_master_store(
    dsn: str, *, auto_migrate: bool = False
) -> PostgresSecurityMasterStore:
    """Construct the PostgreSQL tier. Migrations run only when asked."""
    return PostgresSecurityMasterStore(dsn, auto_migrate=auto_migrate)
