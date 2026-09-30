"""Versioned schema migrations for the deterministic financial state plane.

Master-spec §64 requires *real* migrations, and the V1-A.2 boundary requires that
production startup never creates tables implicitly. This module is the single
authority for the financial schema on both tiers:

- **SQLite** (local/dev): :func:`apply_sqlite_migrations` runs inside the store's
  own connection so a dev database upgrades itself deterministically.
- **PostgreSQL** (production): :func:`apply_postgres_migrations` is driven by the
  operator (``python -m aios db migrate``). The production store refuses to open
  a schema that is behind and never mutates DDL on its own.

Every migration carries the DDL for both dialects. Applied metadata
(``schema_migrations``) records the version, name and a SHA-256 checksum of the
DDL that ran; if the recorded checksum ever disagrees with the code, the store
refuses to start rather than run on a schema it cannot explain.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "MIGRATIONS",
    "Migration",
    "MigrationError",
    "SchemaDrift",
    "SchemaNotMigrated",
    "apply_postgres_migrations",
    "apply_sqlite_migrations",
    "latest_version",
    "schema_status",
]


class MigrationError(RuntimeError):
    """A migration could not be applied."""


class SchemaDrift(MigrationError):
    """An applied migration's DDL no longer matches the code that applied it."""


class SchemaNotMigrated(MigrationError):
    """The database is behind the code and refuses to run until migrated."""


@dataclass(frozen=True)
class Migration:
    """One forward-only schema step, expressed once per dialect."""

    version: int
    name: str
    sqlite: str
    postgres: str

    @property
    def checksum(self) -> str:
        """Digest of both dialects' DDL so drift on either tier is detected."""
        blob = f"{self.version}:{self.name}:{self.sqlite}:{self.postgres}".encode()
        return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------- v1
# Baseline: the V1-A.1 financial kernel (orders, transitions, fills, cash,
# reservations, positions, outbox, inbox, reconciliation records).
# ``IF NOT EXISTS`` is deliberate so that databases provisioned by V1-A.1 (which
# used CREATE TABLE IF NOT EXISTS) adopt this baseline as already-applied.

_V1_SQLITE = """
CREATE TABLE IF NOT EXISTS orders (
    internal_order_id TEXT PRIMARY KEY,
    client_order_id   TEXT NOT NULL UNIQUE,
    broker_order_id   TEXT,
    strategy_id       TEXT NOT NULL,
    portfolio_id      TEXT NOT NULL,
    account_id        TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    quantity          REAL NOT NULL,
    limit_price       REAL,
    stop_price        REAL,
    time_in_force     TEXT NOT NULL,
    filled_quantity   REAL NOT NULL DEFAULT 0,
    avg_fill_price    REAL,
    status            TEXT NOT NULL,
    version           INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    reject_reason     TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_open ON orders(status, account_id);

CREATE TABLE IF NOT EXISTS order_transitions (
    transition_id TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    from_status   TEXT,
    to_status     TEXT NOT NULL,
    version       INTEGER NOT NULL,
    reason        TEXT,
    actor         TEXT NOT NULL,
    occurred_at   TEXT NOT NULL,
    UNIQUE(order_id, version)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id              TEXT PRIMARY KEY,
    order_id             TEXT NOT NULL,
    broker_execution_id  TEXT,
    account_id           TEXT NOT NULL,
    strategy_id          TEXT,
    symbol               TEXT NOT NULL,
    side                 TEXT NOT NULL,
    quantity             REAL NOT NULL,
    price                REAL NOT NULL,
    fee                  REAL NOT NULL DEFAULT 0,
    currency             TEXT NOT NULL,
    executed_at          TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fills_broker_exec
    ON fills(account_id, broker_execution_id)
    WHERE broker_execution_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS cash_postings (
    posting_id     TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    currency       TEXT NOT NULL,
    amount_minor   INTEGER NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    source_ref     TEXT,
    occurred_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cash_txn ON cash_postings(transaction_id);

CREATE TABLE IF NOT EXISTS cash_reservations (
    reservation_id TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL,
    currency       TEXT NOT NULL,
    amount_minor   INTEGER NOT NULL,
    reason         TEXT NOT NULL DEFAULT '',
    order_id       TEXT,
    created_at     TEXT NOT NULL,
    released_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_reservations_open
    ON cash_reservations(account_id, currency, released_at);

CREATE TABLE IF NOT EXISTS positions (
    account_id    TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    quantity      REAL NOT NULL,
    avg_cost      REAL NOT NULL,
    currency      TEXT NOT NULL,
    realized_pnl  REAL NOT NULL DEFAULT 0,
    fees_paid     REAL NOT NULL DEFAULT 0,
    last_fill_id  TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (account_id, symbol)
);

CREATE TABLE IF NOT EXISTS event_outbox (
    event_id         TEXT PRIMARY KEY,
    event_type       TEXT NOT NULL,
    schema_version   TEXT NOT NULL,
    occurred_at      TEXT NOT NULL,
    published_at     TEXT,
    producer         TEXT NOT NULL,
    actor            TEXT,
    correlation_id   TEXT,
    causation_id     TEXT,
    trace_id         TEXT,
    idempotency_key  TEXT NOT NULL,
    policy_version   TEXT,
    model_version    TEXT,
    strategy_version TEXT,
    payload_json     TEXT NOT NULL,
    payload_hash     TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL,
    last_error       TEXT,
    available_at     TEXT,
    claimed_by       TEXT,
    UNIQUE(idempotency_key, event_type)
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON event_outbox(status, occurred_at);

CREATE TABLE IF NOT EXISTS consumer_inbox (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    result_hash   TEXT NOT NULL,
    processed_at  TEXT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id            TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    checked_orders    INTEGER NOT NULL DEFAULT 0,
    checked_fills     INTEGER NOT NULL DEFAULT 0,
    checked_positions INTEGER NOT NULL DEFAULT 0,
    finding_count     INTEGER NOT NULL DEFAULT 0,
    ok                INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reconciliation_findings (
    finding_id     TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    severity       TEXT NOT NULL,
    subject        TEXT NOT NULL,
    detail         TEXT NOT NULL DEFAULT '',
    internal_value TEXT,
    broker_value   TEXT,
    status         TEXT NOT NULL,
    resolution_note TEXT,
    resolved_by    TEXT,
    created_at     TEXT NOT NULL,
    resolved_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_status ON reconciliation_findings(status);

CREATE TABLE IF NOT EXISTS financial_transaction_log (
    transaction_id TEXT PRIMARY KEY,
    opened_at      TEXT NOT NULL,
    closed_at      TEXT,
    description    TEXT NOT NULL DEFAULT ''
);
"""

_V1_POSTGRES = """
CREATE TABLE IF NOT EXISTS orders (
    internal_order_id TEXT PRIMARY KEY,
    client_order_id   TEXT NOT NULL UNIQUE,
    broker_order_id   TEXT,
    strategy_id       TEXT NOT NULL,
    portfolio_id      TEXT NOT NULL,
    account_id        TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    quantity          DOUBLE PRECISION NOT NULL,
    limit_price       DOUBLE PRECISION,
    stop_price        DOUBLE PRECISION,
    time_in_force     TEXT NOT NULL,
    filled_quantity   DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_fill_price    DOUBLE PRECISION,
    status            TEXT NOT NULL,
    version           INTEGER NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL,
    reject_reason     TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_open ON orders(status, account_id);

CREATE TABLE IF NOT EXISTS order_transitions (
    transition_id TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    from_status   TEXT,
    to_status     TEXT NOT NULL,
    version       INTEGER NOT NULL,
    reason        TEXT,
    actor         TEXT NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL,
    UNIQUE(order_id, version)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id              TEXT PRIMARY KEY,
    order_id             TEXT NOT NULL,
    broker_execution_id  TEXT,
    account_id           TEXT NOT NULL,
    strategy_id          TEXT,
    symbol               TEXT NOT NULL,
    side                 TEXT NOT NULL,
    quantity             DOUBLE PRECISION NOT NULL,
    price                DOUBLE PRECISION NOT NULL,
    fee                  DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency             TEXT NOT NULL,
    executed_at          TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fills_broker_exec
    ON fills(account_id, broker_execution_id)
    WHERE broker_execution_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS cash_postings (
    posting_id     TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    account_id     TEXT NOT NULL,
    currency       TEXT NOT NULL,
    amount_minor   BIGINT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    source_ref     TEXT,
    occurred_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cash_txn ON cash_postings(transaction_id);

CREATE TABLE IF NOT EXISTS cash_reservations (
    reservation_id TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL,
    currency       TEXT NOT NULL,
    amount_minor   BIGINT NOT NULL,
    reason         TEXT NOT NULL DEFAULT '',
    order_id       TEXT,
    created_at     TIMESTAMPTZ NOT NULL,
    released_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_reservations_open
    ON cash_reservations(account_id, currency, released_at);

CREATE TABLE IF NOT EXISTS positions (
    account_id    TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    quantity      DOUBLE PRECISION NOT NULL,
    avg_cost      DOUBLE PRECISION NOT NULL,
    currency      TEXT NOT NULL,
    realized_pnl  DOUBLE PRECISION NOT NULL DEFAULT 0,
    fees_paid     DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_fill_id  TEXT,
    updated_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, symbol)
);

CREATE TABLE IF NOT EXISTS event_outbox (
    event_id         TEXT PRIMARY KEY,
    event_type       TEXT NOT NULL,
    schema_version   TEXT NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL,
    published_at     TIMESTAMPTZ,
    producer         TEXT NOT NULL,
    actor            TEXT,
    correlation_id   TEXT,
    causation_id     TEXT,
    trace_id         TEXT,
    idempotency_key  TEXT NOT NULL,
    policy_version   TEXT,
    model_version    TEXT,
    strategy_version TEXT,
    payload_json     TEXT NOT NULL,
    payload_hash     TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL,
    last_error       TEXT,
    available_at     TIMESTAMPTZ,
    claimed_by       TEXT,
    UNIQUE(idempotency_key, event_type)
);
-- Competing outbox workers claim disjoint rows via FOR UPDATE SKIP LOCKED; this
-- partial index keeps that claim cheap while the backlog is PENDING-only.
CREATE INDEX IF NOT EXISTS idx_outbox_claimable
    ON event_outbox(status, available_at, occurred_at);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON event_outbox(status, occurred_at);

CREATE TABLE IF NOT EXISTS consumer_inbox (
    consumer_name TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    result_hash   TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id            TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    checked_orders    INTEGER NOT NULL DEFAULT 0,
    checked_fills     INTEGER NOT NULL DEFAULT 0,
    checked_positions INTEGER NOT NULL DEFAULT 0,
    finding_count     INTEGER NOT NULL DEFAULT 0,
    ok                BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_recon_runs_account
    ON reconciliation_runs(account_id, started_at DESC);

CREATE TABLE IF NOT EXISTS reconciliation_findings (
    finding_id     TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL,
    kind           TEXT NOT NULL,
    severity       TEXT NOT NULL,
    subject        TEXT NOT NULL,
    detail         TEXT NOT NULL DEFAULT '',
    internal_value TEXT,
    broker_value   TEXT,
    status         TEXT NOT NULL,
    resolution_note TEXT,
    resolved_by    TEXT,
    created_at     TIMESTAMPTZ NOT NULL,
    resolved_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_findings_status ON reconciliation_findings(status);

CREATE TABLE IF NOT EXISTS financial_transaction_log (
    transaction_id TEXT PRIMARY KEY,
    opened_at      TIMESTAMPTZ NOT NULL,
    closed_at      TIMESTAMPTZ,
    description    TEXT NOT NULL DEFAULT ''
);
"""

# --------------------------------------------------------------------------- v2
# Broker-reconciliation identity + provenance, and the safety-plane lockout
# ledger. Identity matching (not counting) needs the broker's own identifiers and
# the reconciliation window contract persisted alongside each run.

_V2_SQLITE = """
ALTER TABLE reconciliation_runs ADD COLUMN mode TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN broker TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN adapter_version TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN window_start TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN window_end TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN cursor_token TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN queried_at TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN lockout_scope TEXT NOT NULL DEFAULT 'NONE';
ALTER TABLE reconciliation_runs ADD COLUMN matched_executions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reconciliation_runs ADD COLUMN broker_only_executions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reconciliation_runs ADD COLUMN internal_only_executions INTEGER NOT NULL DEFAULT 0;

ALTER TABLE reconciliation_findings ADD COLUMN broker TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN account_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN strategy_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN execution_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN scope TEXT NOT NULL DEFAULT 'NONE';

CREATE INDEX IF NOT EXISTS idx_findings_subject
    ON reconciliation_findings(kind, subject, status);

CREATE TABLE IF NOT EXISTS safety_lockouts (
    lockout_id   TEXT PRIMARY KEY,
    scope        TEXT NOT NULL,
    subject      TEXT NOT NULL,
    reason       TEXT NOT NULL,
    finding_id   TEXT,
    run_id       TEXT,
    engaged_by   TEXT NOT NULL,
    engaged_at   TEXT NOT NULL,
    released_by  TEXT,
    released_at  TEXT,
    release_note TEXT,
    active       INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lockouts_active
    ON safety_lockouts(scope, subject) WHERE active = 1;
"""

_V2_POSTGRES = """
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS broker TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS adapter_version TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS window_start TIMESTAMPTZ;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS window_end TIMESTAMPTZ;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS cursor_token TEXT;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS queried_at TIMESTAMPTZ;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS lockout_scope TEXT NOT NULL DEFAULT 'NONE';
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS matched_executions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS broker_only_executions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reconciliation_runs ADD COLUMN IF NOT EXISTS internal_only_executions INTEGER NOT NULL DEFAULT 0;

ALTER TABLE reconciliation_findings ADD COLUMN IF NOT EXISTS broker TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN IF NOT EXISTS account_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN IF NOT EXISTS strategy_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN IF NOT EXISTS execution_id TEXT;
ALTER TABLE reconciliation_findings ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'NONE';

CREATE INDEX IF NOT EXISTS idx_findings_subject
    ON reconciliation_findings(kind, subject, status);

CREATE TABLE IF NOT EXISTS safety_lockouts (
    lockout_id   TEXT PRIMARY KEY,
    scope        TEXT NOT NULL,
    subject      TEXT NOT NULL,
    reason       TEXT NOT NULL,
    finding_id   TEXT,
    run_id       TEXT,
    engaged_by   TEXT NOT NULL,
    engaged_at   TIMESTAMPTZ NOT NULL,
    released_by  TEXT,
    released_at  TIMESTAMPTZ,
    release_note TEXT,
    active       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lockouts_active
    ON safety_lockouts(scope, subject) WHERE active = TRUE;
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="financial_kernel_baseline", sqlite=_V1_SQLITE, postgres=_V1_POSTGRES),
    Migration(version=2, name="reconciliation_identity_and_safety_lockouts", sqlite=_V2_SQLITE, postgres=_V2_POSTGRES),
)


def latest_version() -> int:
    """Highest schema version this code knows how to produce."""
    return max(m.version for m in MIGRATIONS)


_META_SQLITE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""

_META_POSTGRES = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);
"""


def _applied_versions(rows: list[tuple[Any, ...]]) -> dict[int, tuple[str, str]]:
    return {int(r[0]): (str(r[1]), str(r[2])) for r in rows}


def _check_drift(applied: dict[int, tuple[str, str]]) -> None:
    for migration in MIGRATIONS:
        recorded = applied.get(migration.version)
        if recorded is None:
            continue
        name, checksum = recorded
        if checksum != migration.checksum:
            raise SchemaDrift(
                f"migration {migration.version} ({migration.name}) was applied with a "
                f"different definition (recorded {checksum[:12]}, code "
                f"{migration.checksum[:12]}); refusing to run on an unexplained schema"
            )
        if name != migration.name:
            raise SchemaDrift(
                f"migration {migration.version} is named {name!r} in the database and "
                f"{migration.name!r} in the code"
            )


def _statements(sql: str) -> list[str]:
    """Split a migration's DDL into statements, dropping ``--`` comments first.

    Comments must be removed *before* splitting: a semicolon inside a comment
    would otherwise cut a statement in half.
    """
    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    return [s.strip() for s in without_comments.split(";") if s.strip()]


def apply_sqlite_migrations(connection: Any, *, target: int | None = None) -> list[int]:
    """Bring a SQLite connection to ``target`` (default: latest).

    Returns the versions applied by *this* call. Idempotent: a database already
    at the target applies nothing.
    """
    stop = latest_version() if target is None else target
    connection.execute(_META_SQLITE)
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations"
    ).fetchall()
    applied = _applied_versions([tuple(r) for r in rows])
    _check_drift(applied)

    done: list[int] = []
    for migration in MIGRATIONS:
        if migration.version > stop or migration.version in applied:
            continue
        for statement in _statements(migration.sqlite):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
            " VALUES (?, ?, ?, ?)",
            (
                migration.version,
                migration.name,
                migration.checksum,
                datetime.now(UTC).isoformat(),
            ),
        )
        done.append(migration.version)
        logger.info("applied sqlite migration %s (%s)", migration.version, migration.name)
    connection.commit()
    return done


def apply_postgres_migrations(connection: Any, *, target: int | None = None) -> list[int]:
    """Bring a PostgreSQL connection to ``target`` (default: latest).

    Runs the whole forward migration plan inside ONE transaction: PostgreSQL has
    transactional DDL, so a mid-plan failure leaves the schema untouched rather
    than half-migrated.

    The transaction is opened here when the connection is in autocommit mode
    (the financial store keeps its connection that way so that bare reads cannot
    leave a dangling implicit transaction); a connection that already manages
    its own transaction is used as-is, as the CLI does.
    """
    stop = latest_version() if target is None else target
    done: list[int] = []
    outer = (
        connection.transaction()
        if getattr(connection, "autocommit", False)
        else nullcontext()
    )
    with outer, connection.cursor() as cur:
        cur.execute(_META_POSTGRES)
        cur.execute("LOCK TABLE schema_migrations IN ACCESS EXCLUSIVE MODE")
        cur.execute("SELECT version, name, checksum FROM schema_migrations")
        applied = _applied_versions(list(cur.fetchall()))
        _check_drift(applied)

        for migration in MIGRATIONS:
            if migration.version > stop or migration.version in applied:
                continue
            for statement in _statements(migration.postgres):
                cur.execute(statement)
            cur.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
                " VALUES (%s, %s, %s, %s)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(UTC),
                ),
            )
            done.append(migration.version)
            logger.info("applied postgres migration %s (%s)", migration.version, migration.name)
    return done


def _fetch_all(
    connection: Any, dialect: str, sql: str
) -> list[tuple[Any, ...]]:
    """Run one read query on either tier (sqlite3 cursors are not context managers)."""
    if dialect == "sqlite":
        return [tuple(row) for row in connection.execute(sql).fetchall()]
    with connection.cursor() as cur:
        cur.execute(sql)
        return [tuple(row) for row in cur.fetchall()]


def schema_status(connection: Any, *, dialect: str) -> dict[str, Any]:
    """Report applied vs required versions for health endpoints and the CLI."""
    meta = _META_SQLITE if dialect == "sqlite" else _META_POSTGRES
    try:
        if dialect == "sqlite":
            connection.execute(meta)
        else:
            with connection.cursor() as cur:
                cur.execute(meta)
        rows = _fetch_all(
            connection,
            dialect,
            "SELECT version, name, checksum, applied_at FROM schema_migrations"
            " ORDER BY version",
        )
    except Exception as exc:  # noqa: BLE001 - status must never raise
        return {
            "dialect": dialect,
            "current": 0,
            "required": latest_version(),
            "up_to_date": False,
            "error": str(exc),
        }
    applied = _applied_versions([(r[0], r[1], r[2]) for r in rows])
    current = max(applied, default=0)
    return {
        "dialect": dialect,
        "current": current,
        "required": latest_version(),
        "up_to_date": current >= latest_version(),
        "applied": [
            {"version": int(r[0]), "name": str(r[1]), "applied_at": str(r[3])} for r in rows
        ],
    }
