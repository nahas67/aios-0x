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


# --------------------------------------------------------------------------- v3
# Security master + corporate actions (vNext goal G020).
#
# Bitemporal instrument identity. Two interval pairs are stored, and both are
# load-bearing: valid_from/valid_to answers "what was true in the world" and
# recorded_from/recorded_to answers "what did we believe". A system that stores
# only the first can run a backtest but cannot answer an audit question, which
# is the question that has to survive a regulator.
#
# Superseded rows are closed (recorded_to set), never deleted. The partial
# unique index enforces that at most one current belief exists per listing and
# valid-time, so a duplicate feed load cannot fork identity in the database even
# if application logic is bypassed.

_V3_SQLITE = """
CREATE TABLE IF NOT EXISTS instrument_identity (
    instrument_id            TEXT NOT NULL,
    listing_id               TEXT NOT NULL,
    ticker                   TEXT NOT NULL,
    mic                      TEXT NOT NULL,
    venue                    TEXT NOT NULL,
    asset_class              TEXT NOT NULL,
    security_type            TEXT NOT NULL DEFAULT 'COMMON',
    currency                 TEXT NOT NULL,
    quote_currency           TEXT,
    account_currency         TEXT,
    tick_size                TEXT,
    lot_size                 TEXT,
    multiplier               TEXT,
    expiry                   TEXT,
    strike                   TEXT,
    underlying_instrument_id TEXT,
    figi                     TEXT,
    isin                     TEXT,
    cik                      TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    valid_from               TEXT NOT NULL,
    valid_to                 TEXT,
    recorded_from            TEXT NOT NULL,
    recorded_to              TEXT,
    source                   TEXT NOT NULL,
    source_priority          INTEGER NOT NULL DEFAULT 100,
    revision                 INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (instrument_id, listing_id, valid_from, recorded_from)
);
CREATE INDEX IF NOT EXISTS idx_identity_current_ticker
    ON instrument_identity(ticker, mic) WHERE recorded_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_identity_isin
    ON instrument_identity(isin) WHERE isin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_identity_valid
    ON instrument_identity(instrument_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS identity_conflicts (
    conflict_id      TEXT PRIMARY KEY,
    instrument_id    TEXT NOT NULL,
    listing_id       TEXT NOT NULL,
    valid_from       TEXT NOT NULL,
    existing_source  TEXT NOT NULL,
    incoming_source  TEXT NOT NULL,
    existing_digest  TEXT NOT NULL,
    incoming_digest  TEXT NOT NULL,
    winner           TEXT NOT NULL,
    reason           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conflicts_instrument
    ON identity_conflicts(instrument_id, valid_from);

CREATE TABLE IF NOT EXISTS corporate_actions (
    action_id                 TEXT NOT NULL,
    instrument_id             TEXT NOT NULL,
    listing_id                TEXT,
    action_type               TEXT NOT NULL,
    announced_at              TEXT NOT NULL,
    effective_at              TEXT NOT NULL,
    record_date               TEXT,
    ex_date                   TEXT,
    ratio_old                 TEXT,
    ratio_new                 TEXT,
    cash_amount               TEXT,
    new_ticker                TEXT,
    successor_instrument_id   TEXT,
    source                    TEXT NOT NULL,
    source_hash               TEXT,
    PRIMARY KEY (action_id, instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_actions_instrument
    ON corporate_actions(instrument_id, effective_at);
"""

_V3_POSTGRES = """
CREATE TABLE IF NOT EXISTS instrument_identity (
    instrument_id            TEXT NOT NULL,
    listing_id               TEXT NOT NULL,
    ticker                   TEXT NOT NULL,
    mic                      TEXT NOT NULL,
    venue                    TEXT NOT NULL,
    asset_class              TEXT NOT NULL,
    security_type            TEXT NOT NULL DEFAULT 'COMMON',
    currency                 TEXT NOT NULL,
    quote_currency           TEXT,
    account_currency         TEXT,
    tick_size                NUMERIC(38, 12),
    lot_size                 NUMERIC(38, 12),
    multiplier               NUMERIC(38, 12),
    expiry                   DATE,
    strike                   NUMERIC(38, 12),
    underlying_instrument_id TEXT,
    figi                     TEXT,
    isin                     TEXT,
    cik                      TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    valid_from               TIMESTAMPTZ NOT NULL,
    valid_to                 TIMESTAMPTZ,
    recorded_from            TIMESTAMPTZ NOT NULL,
    recorded_to              TIMESTAMPTZ,
    source                   TEXT NOT NULL,
    source_priority          INTEGER NOT NULL DEFAULT 100,
    revision                 INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (instrument_id, listing_id, valid_from, recorded_from)
);
CREATE INDEX IF NOT EXISTS idx_identity_current_ticker
    ON instrument_identity(ticker, mic) WHERE recorded_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_identity_isin
    ON instrument_identity(isin) WHERE isin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_identity_valid
    ON instrument_identity(instrument_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS identity_conflicts (
    conflict_id      TEXT PRIMARY KEY,
    instrument_id    TEXT NOT NULL,
    listing_id       TEXT NOT NULL,
    valid_from       TIMESTAMPTZ NOT NULL,
    existing_source  TEXT NOT NULL,
    incoming_source  TEXT NOT NULL,
    existing_digest  TEXT NOT NULL,
    incoming_digest  TEXT NOT NULL,
    winner           TEXT NOT NULL,
    reason           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conflicts_instrument
    ON identity_conflicts(instrument_id, valid_from);

CREATE TABLE IF NOT EXISTS corporate_actions (
    action_id                 TEXT NOT NULL,
    instrument_id             TEXT NOT NULL,
    listing_id                TEXT,
    action_type               TEXT NOT NULL,
    announced_at              TIMESTAMPTZ NOT NULL,
    effective_at              TIMESTAMPTZ NOT NULL,
    record_date               DATE,
    ex_date                   DATE,
    ratio_old                 NUMERIC(38, 12),
    ratio_new                 NUMERIC(38, 12),
    cash_amount               NUMERIC(38, 12),
    new_ticker                TEXT,
    successor_instrument_id   TEXT,
    source                    TEXT NOT NULL,
    source_hash               TEXT,
    PRIMARY KEY (action_id, instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_actions_instrument
    ON corporate_actions(instrument_id, effective_at);
"""


# --------------------------------------------------------------------------- v4
# The durable governance ledger (vNext goal G050).
#
# Append-only is enforced by the *database*, not by application discipline. A
# Python guard that promises not to mutate a row is a promise; a trigger that
# aborts the write is a control. The same reasoning that put a partial unique
# index on current identity beliefs in v3 applies here with more force: this
# table is the evidence that a capital decision was governed, and evidence that
# can be edited is not evidence.
#
# Three separate tamper classes are refused, because they need three separate
# mechanisms:
#
#   UPDATE  — a decision edited after the fact.
#   DELETE  — a decision removed, which is how a denial disappears.
#   INSERT  — a decision spliced in out of order, or a gap opened where one
#             should be. A chain hash alone does not catch this: the chain is
#             recomputed over whatever sequence is present, so removing entry N
#             and renumbering N+1.. produces a *valid* shorter chain. The seq
#             and previous_chain_hash checks are what make truncation visible.
#
# The same reasoning put `governance_seals` here: a chain verifies against
# itself, so a truncated log verifies. Only a hash the log cannot influence
# pins the head — an HMAC over the head at a moment in time. That is the
# difference between "the log is internally consistent" and "the log is the
# log we had."

_V4_SQLITE = """
CREATE TABLE IF NOT EXISTS governance_decisions (
    seq                  INTEGER PRIMARY KEY,
    chain_hash           TEXT NOT NULL UNIQUE,
    previous_chain_hash  TEXT NOT NULL,
    disposition          TEXT NOT NULL,
    call_digest          TEXT NOT NULL,
    reasoning            TEXT NOT NULL,
    evaluator            TEXT NOT NULL,
    model_id             TEXT,
    decided_at           TEXT NOT NULL,
    payload              TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS governance_seals (
    seal_id      INTEGER PRIMARY KEY,
    seq          INTEGER NOT NULL,
    chain_hash   TEXT NOT NULL,
    sealed_at    TEXT NOT NULL,
    signature    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_governance_no_update
BEFORE UPDATE ON governance_decisions
BEGIN
    SELECT RAISE(ABORT, 'governance_decisions is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_no_delete
BEFORE DELETE ON governance_decisions
BEGIN
    SELECT RAISE(ABORT, 'governance_decisions is append-only: DELETE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_seq_is_next
BEFORE INSERT ON governance_decisions
WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM governance_decisions)
BEGIN
    SELECT RAISE(ABORT, 'sequence break: seq must be the next integer');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_chains_to_head
BEFORE INSERT ON governance_decisions
WHEN (SELECT COUNT(*) FROM governance_decisions) > 0
 AND NEW.previous_chain_hash <> (
     SELECT chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1
 )
BEGIN
    SELECT RAISE(ABORT, 'chain break: previous_chain_hash does not match the current head');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_seals_no_update
BEFORE UPDATE ON governance_seals
BEGIN
    SELECT RAISE(ABORT, 'governance_seals is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_seals_no_delete
BEFORE DELETE ON governance_seals
BEGIN
    SELECT RAISE(ABORT, 'governance_seals is append-only: DELETE refused');
END;
"""

_V4_POSTGRES = """
CREATE TABLE IF NOT EXISTS governance_decisions (
    seq                  BIGINT PRIMARY KEY,
    chain_hash           TEXT NOT NULL UNIQUE,
    previous_chain_hash  TEXT NOT NULL,
    disposition          TEXT NOT NULL,
    call_digest          TEXT NOT NULL,
    reasoning            TEXT NOT NULL,
    evaluator            TEXT NOT NULL,
    model_id             TEXT,
    decided_at           TIMESTAMPTZ NOT NULL,
    payload              TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS governance_seals (
    seal_id      BIGINT PRIMARY KEY,
    seq          BIGINT NOT NULL,
    chain_hash   TEXT NOT NULL,
    sealed_at    TIMESTAMPTZ NOT NULL,
    signature    TEXT NOT NULL
);

-- Append-only and chain continuity, enforced by the database rather than by
-- application discipline. Each trigger raises a distinct message so a refusal
-- names the tamper class it caught; a single "write refused" would send an
-- operator looking in the wrong place.
CREATE OR REPLACE FUNCTION aios_governance_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'governance_% is append-only: % refused',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_governance_no_update ON governance_decisions;
CREATE TRIGGER trg_governance_no_update
    BEFORE UPDATE ON governance_decisions
    FOR EACH ROW EXECUTE FUNCTION aios_governance_append_only();

DROP TRIGGER IF EXISTS trg_governance_no_delete ON governance_decisions;
CREATE TRIGGER trg_governance_no_delete
    BEFORE DELETE ON governance_decisions
    FOR EACH ROW EXECUTE FUNCTION aios_governance_append_only();

DROP TRIGGER IF EXISTS trg_governance_seq_is_next ON governance_decisions;
CREATE TRIGGER trg_governance_seq_is_next
    BEFORE INSERT ON governance_decisions
    FOR EACH ROW
    WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM governance_decisions)
    EXECUTE FUNCTION aios_governance_append_only();

DROP TRIGGER IF EXISTS trg_governance_chains_to_head ON governance_decisions;
CREATE TRIGGER trg_governance_chains_to_head
    BEFORE INSERT ON governance_decisions
    FOR EACH ROW
    WHEN EXISTS (SELECT 1 FROM governance_decisions)
     AND NEW.previous_chain_hash <> (
         SELECT chain_hash FROM governance_decisions ORDER BY seq DESC LIMIT 1
     )
    EXECUTE FUNCTION aios_governance_append_only();

DROP TRIGGER IF EXISTS trg_governance_seals_no_update ON governance_seals;
CREATE TRIGGER trg_governance_seals_no_update
    BEFORE UPDATE ON governance_seals
    FOR EACH ROW EXECUTE FUNCTION aios_governance_append_only();

DROP TRIGGER IF EXISTS trg_governance_seals_no_delete ON governance_seals;
CREATE TRIGGER trg_governance_seals_no_delete
    BEFORE DELETE ON governance_seals
    FOR EACH ROW EXECUTE FUNCTION aios_governance_append_only();
"""


# --------------------------------------------------------------------------- v5
# The durable experiment ledger (vNext goal G070).
#
# Same enforcement shape as v4, adapted to a different write pattern. Governance
# decisions are immutable events with a global chain; experiments are stateful
# rows (CREATED → RUNNING → COMPLETED/FAILED), so the ledger stores one event
# per transition carrying the full run snapshot, and current state is the
# latest event per experiment. Two consequences follow.
#
# First, there is no global chain hash — ordering only matters *within* an
# experiment, so each event carries ``supersedes``, the seq of that
# experiment's previous event (0 at creation), and the trigger refuses an
# insert that does not link to its experiment's head. A forged event rewriting
# a FAILED run as COMPLETED cannot link to the head without becoming the head,
# and as the head it is visible rather than hidden: the rewrite is an event,
# not an edit.
#
# Second, the seal signs (max_seq, event_count) rather than a chain head. The
# truncation argument is identical to v4's: a rolling record over the entries
# present verifies perfectly over a shortened log, so only an external anchor
# — an HMAC with a key the log cannot reach — turns "internally consistent"
# into "this is the log we had". For experiments the specific prize of a cut
# tail is manufacturing a track record: 10,000 failures disappear and the one
# lucky result remains. The seal is what makes the denominator auditable.

_V5_SQLITE = """
CREATE TABLE IF NOT EXISTS experiment_events (
    seq             INTEGER PRIMARY KEY,
    experiment_id   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    supersedes      INTEGER NOT NULL,
    recorded_at     TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_events_id
    ON experiment_events(experiment_id, seq);
CREATE TABLE IF NOT EXISTS experiment_seals (
    seal_id      INTEGER PRIMARY KEY,
    event_count  INTEGER NOT NULL,
    max_seq      INTEGER NOT NULL,
    sealed_at    TEXT NOT NULL,
    signature    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_experiment_no_update
BEFORE UPDATE ON experiment_events
BEGIN
    SELECT RAISE(ABORT, 'experiment_events is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_experiment_no_delete
BEFORE DELETE ON experiment_events
BEGIN
    SELECT RAISE(ABORT, 'experiment_events is append-only: DELETE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_experiment_seq_is_next
BEFORE INSERT ON experiment_events
WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM experiment_events)
BEGIN
    SELECT RAISE(ABORT, 'sequence break: seq must be the next integer');
END;

CREATE TRIGGER IF NOT EXISTS trg_experiment_links_to_predecessor
BEFORE INSERT ON experiment_events
WHEN NEW.supersedes <> (
    SELECT COALESCE(MAX(seq), 0) FROM experiment_events
    WHERE experiment_id = NEW.experiment_id
)
BEGIN
    SELECT RAISE(ABORT, 'chain break: supersedes does not match the experiment head');
END;

CREATE TRIGGER IF NOT EXISTS trg_experiment_seals_no_update
BEFORE UPDATE ON experiment_seals
BEGIN
    SELECT RAISE(ABORT, 'experiment_seals is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_experiment_seals_no_delete
BEFORE DELETE ON experiment_seals
BEGIN
    SELECT RAISE(ABORT, 'experiment_seals is append-only: DELETE refused');
END;
"""

_V5_POSTGRES = """
CREATE TABLE IF NOT EXISTS experiment_events (
    seq             BIGINT PRIMARY KEY,
    experiment_id   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    supersedes      BIGINT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_events_id
    ON experiment_events(experiment_id, seq);
CREATE TABLE IF NOT EXISTS experiment_seals (
    seal_id      BIGINT PRIMARY KEY,
    event_count  BIGINT NOT NULL,
    max_seq      BIGINT NOT NULL,
    sealed_at    TIMESTAMPTZ NOT NULL,
    signature    TEXT NOT NULL
);

-- Same enforcement shape as the governance ledger: the database refuses the
-- tamper classes rather than application code promising not to attempt them.
-- The per-experiment continuity check (supersedes) is enforced by the
-- application-facing sink pre-check and re-checked here.
CREATE OR REPLACE FUNCTION aios_experiment_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'experiment_% is append-only: % refused',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_experiment_no_update ON experiment_events;
CREATE TRIGGER trg_experiment_no_update
    BEFORE UPDATE ON experiment_events
    FOR EACH ROW EXECUTE FUNCTION aios_experiment_append_only();

DROP TRIGGER IF EXISTS trg_experiment_no_delete ON experiment_events;
CREATE TRIGGER trg_experiment_no_delete
    BEFORE DELETE ON experiment_events
    FOR EACH ROW EXECUTE FUNCTION aios_experiment_append_only();

DROP TRIGGER IF EXISTS trg_experiment_seq_is_next ON experiment_events;
CREATE TRIGGER trg_experiment_seq_is_next
    BEFORE INSERT ON experiment_events
    FOR EACH ROW
    WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM experiment_events)
    EXECUTE FUNCTION aios_experiment_append_only();

DROP TRIGGER IF EXISTS trg_experiment_links_to_predecessor ON experiment_events;
CREATE TRIGGER trg_experiment_links_to_predecessor
    BEFORE INSERT ON experiment_events
    FOR EACH ROW
    WHEN NEW.supersedes <> (
        SELECT COALESCE(MAX(seq), 0) FROM experiment_events
        WHERE experiment_id = NEW.experiment_id
    )
    EXECUTE FUNCTION aios_experiment_append_only();

DROP TRIGGER IF EXISTS trg_experiment_seals_no_update ON experiment_seals;
CREATE TRIGGER trg_experiment_seals_no_update
    BEFORE UPDATE ON experiment_seals
    FOR EACH ROW EXECUTE FUNCTION aios_experiment_append_only();

DROP TRIGGER IF EXISTS trg_experiment_seals_no_delete ON experiment_seals;
CREATE TRIGGER trg_experiment_seals_no_delete
    BEFORE DELETE ON experiment_seals
    FOR EACH ROW EXECUTE FUNCTION aios_experiment_append_only();
"""


# --------------------------------------------------------------------------- v6
# The evidence fabric: claim ledger (vNext goal G040).
#
# Content-addressed sources, append-only claims. The SQLite tier predates this
# migration and creates the same tables on open (``core/claim_ledger.py``), so
# this DDL mirrors that schema statement-for-statement: a dev database that
# grew its tables from the ledger and a database migrated here must agree.
# The PostgreSQL tier is created by this migration only, when the operator
# asks (``auto_migrate``), mirroring the security-master contract — production
# PostgreSQL never mutates DDL on open.
#
# Timestamps are TIMESTAMPTZ on the PostgreSQL tier and confidence is DOUBLE
# PRECISION; the claim payloads stay TEXT on both tiers so the same row
# mappers serve either side without a type fork.

_V6_SQLITE = """
CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    source        TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL,
    content       TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id               TEXT PRIMARY KEY,
    subject_id             TEXT NOT NULL,
    predicate              TEXT NOT NULL,
    object_json            TEXT NOT NULL,
    claim_class            TEXT NOT NULL,
    provenance             TEXT NOT NULL,
    evidence_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_artifact_id     TEXT NOT NULL,
    source_hash            TEXT NOT NULL,
    source_time            TEXT,
    available_at           TEXT,
    confidence             REAL NOT NULL,
    verdict                TEXT NOT NULL,
    contraindications_json TEXT NOT NULL DEFAULT '[]',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    supersedes             TEXT,
    contradicted_by_json   TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (source_artifact_id) REFERENCES source_artifacts(artifact_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_artifact ON claims(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_claims_supersedes ON claims(supersedes) WHERE supersedes IS NOT NULL;
"""

_V6_POSTGRES = """
CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    source        TEXT NOT NULL,
    retrieved_at  TIMESTAMPTZ NOT NULL,
    content       TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id               TEXT PRIMARY KEY,
    subject_id             TEXT NOT NULL,
    predicate              TEXT NOT NULL,
    object_json            TEXT NOT NULL,
    claim_class            TEXT NOT NULL,
    provenance             TEXT NOT NULL,
    evidence_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_artifact_id     TEXT NOT NULL,
    source_hash            TEXT NOT NULL,
    source_time            TIMESTAMPTZ,
    available_at           TIMESTAMPTZ,
    confidence             DOUBLE PRECISION NOT NULL,
    verdict                TEXT NOT NULL,
    contraindications_json TEXT NOT NULL DEFAULT '[]',
    created_at             TIMESTAMPTZ NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL,
    supersedes             TEXT,
    contradicted_by_json   TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (source_artifact_id) REFERENCES source_artifacts(artifact_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_artifact ON claims(source_artifact_id);
CREATE INDEX IF NOT EXISTS idx_claims_supersedes ON claims(supersedes) WHERE supersedes IS NOT NULL;
"""


# --------------------------------------------------------------------------- v7
# The durable dataset-version store (vNext goal G030).
#
# Same event-log shape as v5: one event per lifecycle transition carrying the
# full version snapshot, current state as the latest event per dataset key,
# per-key ``supersedes`` linkage, and a seal over (count, head). Dataset
# versions change rarely and certify slowly, which is exactly why their loss
# would go unnoticed the longest: nobody re-registers a dataset daily, so a
# vanished version surfaces months later as an unreproducible backtest.

_V7_SQLITE = """
CREATE TABLE IF NOT EXISTS dataset_version_events (
    seq             INTEGER PRIMARY KEY,
    dataset_key     TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    supersedes      INTEGER NOT NULL,
    recorded_at     TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_version_events_key
    ON dataset_version_events(dataset_key, seq);
CREATE TABLE IF NOT EXISTS dataset_version_seals (
    seal_id      INTEGER PRIMARY KEY,
    event_count  INTEGER NOT NULL,
    max_seq      INTEGER NOT NULL,
    sealed_at    TEXT NOT NULL,
    signature    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_no_update
BEFORE UPDATE ON dataset_version_events
BEGIN
    SELECT RAISE(ABORT, 'dataset_version_events is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_no_delete
BEFORE DELETE ON dataset_version_events
BEGIN
    SELECT RAISE(ABORT, 'dataset_version_events is append-only: DELETE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_seq_is_next
BEFORE INSERT ON dataset_version_events
WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM dataset_version_events)
BEGIN
    SELECT RAISE(ABORT, 'sequence break: seq must be the next integer');
END;

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_links_to_predecessor
BEFORE INSERT ON dataset_version_events
WHEN NEW.supersedes <> (
    SELECT COALESCE(MAX(seq), 0) FROM dataset_version_events
    WHERE dataset_key = NEW.dataset_key
)
BEGIN
    SELECT RAISE(ABORT, 'chain break: supersedes does not match the dataset head');
END;

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_seals_no_update
BEFORE UPDATE ON dataset_version_seals
BEGIN
    SELECT RAISE(ABORT, 'dataset_version_seals is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_dataset_version_seals_no_delete
BEFORE DELETE ON dataset_version_seals
BEGIN
    SELECT RAISE(ABORT, 'dataset_version_seals is append-only: DELETE refused');
END;
"""

_V7_POSTGRES = """
CREATE TABLE IF NOT EXISTS dataset_version_events (
    seq             BIGINT PRIMARY KEY,
    dataset_key     TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    supersedes      BIGINT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_version_events_key
    ON dataset_version_events(dataset_key, seq);
CREATE TABLE IF NOT EXISTS dataset_version_seals (
    seal_id      BIGINT PRIMARY KEY,
    event_count  BIGINT NOT NULL,
    max_seq      BIGINT NOT NULL,
    sealed_at    TIMESTAMPTZ NOT NULL,
    signature    TEXT NOT NULL
);

CREATE OR REPLACE FUNCTION aios_dataset_version_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'dataset_version_% is append-only: % refused',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_dataset_version_no_update ON dataset_version_events;
CREATE TRIGGER trg_dataset_version_no_update
    BEFORE UPDATE ON dataset_version_events
    FOR EACH ROW EXECUTE FUNCTION aios_dataset_version_append_only();

DROP TRIGGER IF EXISTS trg_dataset_version_no_delete ON dataset_version_events;
CREATE TRIGGER trg_dataset_version_no_delete
    BEFORE DELETE ON dataset_version_events
    FOR EACH ROW EXECUTE FUNCTION aios_dataset_version_append_only();

DROP TRIGGER IF EXISTS trg_dataset_version_seq_is_next ON dataset_version_events;
CREATE TRIGGER trg_dataset_version_seq_is_next
    BEFORE INSERT ON dataset_version_events
    FOR EACH ROW
    WHEN NEW.seq <> (SELECT COALESCE(MAX(seq), 0) + 1 FROM dataset_version_events)
    EXECUTE FUNCTION aios_dataset_version_append_only();

DROP TRIGGER IF EXISTS trg_dataset_version_links_to_predecessor ON dataset_version_events;
CREATE TRIGGER trg_dataset_version_links_to_predecessor
    BEFORE INSERT ON dataset_version_events
    FOR EACH ROW
    WHEN NEW.supersedes <> (
        SELECT COALESCE(MAX(seq), 0) FROM dataset_version_events
        WHERE dataset_key = NEW.dataset_key
    )
    EXECUTE FUNCTION aios_dataset_version_append_only();

DROP TRIGGER IF EXISTS trg_dataset_version_seals_no_update ON dataset_version_seals;
CREATE TRIGGER trg_dataset_version_seals_no_update
    BEFORE UPDATE ON dataset_version_seals
    FOR EACH ROW EXECUTE FUNCTION aios_dataset_version_append_only();

DROP TRIGGER IF EXISTS trg_dataset_version_seals_no_delete ON dataset_version_seals;
CREATE TRIGGER trg_dataset_version_seals_no_delete
    BEFORE DELETE ON dataset_version_seals
    FOR EACH ROW EXECUTE FUNCTION aios_dataset_version_append_only();
"""


# --------------------------------------------------------------------------- v8
# The durable playbook store (vNext goal G120).
#
# Playbooks are immutable once registered — no transitions, so no event log.
# One row per playbook version with its content hash; append-only triggers
# refuse UPDATE and DELETE. A restart loses the router's memory, not its
# policies: resume reloads every row and re-registers, and certification is
# re-asked live, so a playbook whose verdict was revoked while the process
# was down loads but never selects. The seal signs (count, head) for the
# same truncation argument as every sibling ledger.

_V8_SQLITE = """
CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id   TEXT NOT NULL,
    version       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    payload       TEXT NOT NULL,
    PRIMARY KEY (playbook_id, version)
);
CREATE TABLE IF NOT EXISTS playbook_seals (
    seal_id      INTEGER PRIMARY KEY,
    event_count  INTEGER NOT NULL,
    set_hash     TEXT NOT NULL,
    sealed_at    TEXT NOT NULL,
    signature    TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_playbooks_no_update
BEFORE UPDATE ON playbooks
BEGIN
    SELECT RAISE(ABORT, 'playbooks is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_playbooks_no_delete
BEFORE DELETE ON playbooks
BEGIN
    SELECT RAISE(ABORT, 'playbooks is append-only: DELETE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_playbook_seals_no_update
BEFORE UPDATE ON playbook_seals
BEGIN
    SELECT RAISE(ABORT, 'playbook_seals is append-only: UPDATE refused');
END;

CREATE TRIGGER IF NOT EXISTS trg_playbook_seals_no_delete
BEFORE DELETE ON playbook_seals
BEGIN
    SELECT RAISE(ABORT, 'playbook_seals is append-only: DELETE refused');
END;
"""

_V8_POSTGRES = """
CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id   TEXT NOT NULL,
    version       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    payload       TEXT NOT NULL,
    PRIMARY KEY (playbook_id, version)
);
CREATE TABLE IF NOT EXISTS playbook_seals (
    seal_id      BIGINT PRIMARY KEY,
    event_count  BIGINT NOT NULL,
    set_hash     TEXT NOT NULL,
    sealed_at    TIMESTAMPTZ NOT NULL,
    signature    TEXT NOT NULL
);

CREATE OR REPLACE FUNCTION aios_playbook_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'playbook_% is append-only: % refused',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_playbooks_no_update ON playbooks;
CREATE TRIGGER trg_playbooks_no_update
    BEFORE UPDATE ON playbooks
    FOR EACH ROW EXECUTE FUNCTION aios_playbook_append_only();

DROP TRIGGER IF EXISTS trg_playbooks_no_delete ON playbooks;
CREATE TRIGGER trg_playbooks_no_delete
    BEFORE DELETE ON playbooks
    FOR EACH ROW EXECUTE FUNCTION aios_playbook_append_only();

DROP TRIGGER IF EXISTS trg_playbook_seals_no_update ON playbook_seals;
CREATE TRIGGER trg_playbook_seals_no_update
    BEFORE UPDATE ON playbook_seals
    FOR EACH ROW EXECUTE FUNCTION aios_playbook_append_only();

DROP TRIGGER IF EXISTS trg_playbook_seals_no_delete ON playbook_seals;
CREATE TRIGGER trg_playbook_seals_no_delete
    BEFORE DELETE ON playbook_seals
    FOR EACH ROW EXECUTE FUNCTION aios_playbook_append_only();
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="financial_kernel_baseline", sqlite=_V1_SQLITE, postgres=_V1_POSTGRES),
    Migration(version=2, name="reconciliation_identity_and_safety_lockouts", sqlite=_V2_SQLITE, postgres=_V2_POSTGRES),
    Migration(
        version=3,
        name="security_master_and_corporate_actions",
        sqlite=_V3_SQLITE,
        postgres=_V3_POSTGRES,
    ),
    Migration(
        version=4,
        name="durable_governance_ledger",
        sqlite=_V4_SQLITE,
        postgres=_V4_POSTGRES,
    ),
    Migration(
        version=5,
        name="durable_experiment_ledger",
        sqlite=_V5_SQLITE,
        postgres=_V5_POSTGRES,
    ),
    Migration(
        version=6,
        name="claim_ledger",
        sqlite=_V6_SQLITE,
        postgres=_V6_POSTGRES,
    ),
    Migration(
        version=7,
        name="durable_dataset_version_store",
        sqlite=_V7_SQLITE,
        postgres=_V7_POSTGRES,
    ),
    Migration(
        version=8,
        name="durable_playbook_store",
        sqlite=_V8_SQLITE,
        postgres=_V8_POSTGRES,
    ),
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

    Plain ``split(";")`` is not sufficient once a migration contains a
    ``CREATE TRIGGER`` or a PL/pgSQL function, and getting this wrong is silent
    in the worst way — the database reports "incomplete input" far from the
    actual cause. Two constructs carry semicolons that are not statement
    boundaries:

    * ``BEGIN ... END;`` trigger bodies, where every inner statement is
      terminated but the body is one statement.
    * ``$$ ... $$`` dollar-quoted function bodies on the PostgreSQL tier, where
      the same applies to ``RAISE ... ;`` inside a function.

    Both are tracked explicitly rather than with a heuristic, and string
    literals are skipped so a ``;`` inside a quoted message cannot cut a
    statement either. The scan is also dialect-agnostic: a trigger body on one
    tier and a dollar-quoted body on the other are the same problem.

    The terminating semicolon is consumed rather than retained, so every
    returned statement is ready for ``connection.execute``. That is observable
    and asserted in ``tests/test_migration_splitter.py``: a trigger statement
    therefore ends with ``END``, not ``END;``.
    """
    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    statements: list[str] = []
    current: list[str] = []
    is_trigger = False
    block_depth = 0
    in_dollars = False
    in_string = False
    index = 0
    length = len(without_comments)
    while index < length:
        char = without_comments[index]
        pair = without_comments[index : index + 2]
        if in_string:
            current.append(char)
            if char == "'":
                # A doubled quote is an escaped quote, not a terminator.
                if pair == "''":
                    current.append("'")
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if in_dollars:
            current.append(char)
            if pair == "$$":
                current.append("$")
                index += 2
                in_dollars = False
                continue
            index += 1
            continue
        if char == "'":
            in_string = True
            current.append(char)
            index += 1
            continue
        if pair == "$$":
            in_dollars = True
            current.append(pair)
            index += 2
            continue
        if char == ";" and not (is_trigger and block_depth > 0):
            statements.append("".join(current).strip())
            current = []
            is_trigger = False
            block_depth = 0
            index += 1
            continue
        if char.isalpha() or char == "_":
            start = index
            while index + 1 < length and (
                without_comments[index + 1].isalnum()
                or without_comments[index + 1] == "_"
            ):
                index += 1
            word = without_comments[start : index + 1]
            current.append(word)
            upper = word.upper()
            head = "".join(current).upper()
            if upper == "TRIGGER" and "CREATE" in head and not is_trigger:
                is_trigger = True
            elif is_trigger and upper == "BEGIN":
                block_depth += 1
            elif is_trigger and upper == "END" and block_depth > 0:
                block_depth -= 1
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


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
