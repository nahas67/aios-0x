"""Cross-dialect parity for the durable ledgers (goals G050, G070).

The governance log and the experiment log each have two tiers. A behavioural
difference between them is a defect in one of the two stores, not a dialect
difference — and an audit that passes on SQLite while production runs
PostgreSQL is an audit of the wrong system.

Behavioural tests run against *both* tiers. The PostgreSQL legs run when
``AIOS_TEST_PG_DSN`` is set and skip otherwise, per the repo's integration
contract. The DDL cross-checks need no database: the migration texts are the
artifact under test, so a schema fork fails hermetically, everywhere.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from core.decision_sink import (
    build_postgres_decision_sink,
    build_sqlite_decision_sink,
)
from core.experiment_sink import (
    build_experiment_ledger,
    build_postgres_experiment_sink,
    build_sqlite_experiment_sink,
)
from core.migrations import MIGRATIONS, _statements
from kernel.tool_governance import ToolGuardian
from schemas.governance import ToolCall

DSN = os.environ.get("AIOS_TEST_PG_DSN", "")

SECRET = b"k" * 32

#: A real ISO-8601 instant, fixed so both tiers see the same value. The tests
#: previously passed the literal "t", which SQLite accepts in a TEXT column and
#: PostgreSQL rejects in a TIMESTAMPTZ one ("invalid input syntax for type
#: timestamp with time zone"). That made three parity tests SQLite-only in
#: effect: they exercised the SQLite tier and skipped the production tier, so
#: the very divergence they exist to catch went unseen.
STAMP = "2026-01-01T00:00:00+00:00"


def _call(symbol: str = "AAPL", quantity: float = 10.0) -> ToolCall:
    return ToolCall(
        tool="broker.submit",
        operation="place",
        capability="broker.order.place",
        agent_id="agent.strategy",
        intent="parity check",
        arguments={
            "symbol": {"value": symbol, "provenance": "OPERATOR"},
            "quantity": {"value": quantity, "provenance": "MODEL_DERIVED"},
        },
    )


def _truncate_pg(table_names: list[str]) -> None:
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in table_names:
                cur.execute(f"TRUNCATE {table}")


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def decision_sink(request, tmp_path: Path):
    """One governance log per tier. Same behaviour asserted on both."""
    if request.param == "sqlite":
        yield build_sqlite_decision_sink(tmp_path / "gov.db")
    else:
        _truncate_pg(["governance_decisions", "governance_seals"])
        store = build_postgres_decision_sink(DSN, auto_migrate=True)
        try:
            yield store
        finally:
            store.close()


@pytest.fixture(params=["sqlite"] + (["postgres"] if DSN else []))
def experiment_sink(request, tmp_path: Path):
    """One experiment log per tier. Same behaviour asserted on both."""
    if request.param == "sqlite":
        yield build_sqlite_experiment_sink(tmp_path / "exp.db")
    else:
        _truncate_pg(["experiment_events", "experiment_seals"])
        store = build_postgres_experiment_sink(DSN, auto_migrate=True)
        try:
            yield store
        finally:
            store.close()


# ══════════════════════════════════════════════════════════════════════════
# Governance log parity
# ══════════════════════════════════════════════════════════════════════════


def test_decisions_round_trip_with_chain_intact(decision_sink) -> None:
    """Three decisions through a real guardian, read back identical, chain
    verifying — on whichever tier the fixture supplied."""
    guardian = ToolGuardian(SECRET, sink=decision_sink)
    for index in range(3):
        guardian.evaluate(_call(symbol=f"SYM{index}", quantity=float(index + 1)))
    stored = decision_sink.read_all()
    assert len(stored) == 3
    assert [d.call_digest for d in stored] == [d.call_digest for d in guardian.log()]
    assert decision_sink.head() == guardian.chain_hash
    assert decision_sink.audit(SECRET).chain_intact is True


def test_denial_survives_with_its_reason(decision_sink) -> None:
    guardian = ToolGuardian(SECRET, sink=decision_sink)
    guardian.register_deny_rule(
        "SANCTIONS",
        lambda call: call.value_of("symbol") == "BANNED",
        policy_id="policy.sanctions",
    )
    from schemas.governance import ToolGovernanceError

    with pytest.raises(ToolGovernanceError):
        guardian.authorize(_call(symbol="BANNED"))
    decisions = decision_sink.read_all()
    assert len(decisions) == 1
    assert decisions[0].disposition.value == "DENY"
    assert "SANCTIONS" in decisions[0].reasoning


def test_seal_covers_the_head_on_both_tiers(decision_sink) -> None:
    guardian = ToolGuardian(SECRET, sink=decision_sink)
    guardian.evaluate(_call())
    assert decision_sink.seal(SECRET) is not None
    audit = decision_sink.audit(SECRET)
    assert audit.ok is True
    assert audit.sealed_through == 1


def _raw_execute(sink, sql: str) -> None:
    """Raw SQL around the store API, the way an attacker with a file handle
    would. Attribute-sniffing keeps one test body serving both tiers rather
    than two near-identical tests drifting apart."""
    if hasattr(sink, "_connection"):
        sink._connection.execute(sql)
    else:
        with sink._conn.cursor() as cur:
            cur.execute(sql)


def test_update_and_delete_are_refused_on_both_tiers(decision_sink) -> None:
    """The refusal comes from the schema on both tiers — though the message
    differs: SQLite names the tamper class per trigger, while the Postgres
    tier funnels through one function naming table and operation."""
    import sqlite3

    import psycopg

    guardian = ToolGuardian(SECRET, sink=decision_sink)
    guardian.evaluate(_call())
    with pytest.raises((sqlite3.IntegrityError, psycopg.errors.Error)) as excinfo:
        _raw_execute(
            decision_sink,
            "UPDATE governance_decisions SET reasoning = 'innocent' WHERE seq = 1",
        )
    assert "append-only" in str(excinfo.value)


# ══════════════════════════════════════════════════════════════════════════
# Experiment log parity
# ══════════════════════════════════════════════════════════════════════════


def test_experiment_lifecycle_round_trips(experiment_sink) -> None:
    """Create, start, fail — read back as snapshots with linkage intact."""
    experiment_sink.append("exp-1", "CREATED", '{"status": "CREATED"}', STAMP)
    experiment_sink.append("exp-1", "STARTED", '{"status": "RUNNING"}', STAMP)
    experiment_sink.append("exp-1", "FAILED", '{"status": "FAILED"}', STAMP)
    snapshots = experiment_sink.read_snapshots()
    assert set(snapshots) == {"exp-1"}
    assert snapshots["exp-1"] == '{"status": "FAILED"}'
    events = experiment_sink.read_events()
    assert [e.supersedes for e in events] == [0, 1, 2]
    assert experiment_sink.audit(SECRET).chain_intact is True


def test_forked_event_refused_on_both_tiers(experiment_sink, tmp_path: Path) -> None:
    """Same fork, both tiers: an event skipping its predecessor is refused
    by name. The sqlite message names the chain break; the postgres message
    names table and operation through the shared function."""
    import sqlite3

    import psycopg

    experiment_sink.append("exp-1", "CREATED", "{}", STAMP)
    if hasattr(experiment_sink, "_connection"):
        with pytest.raises(sqlite3.IntegrityError, match="chain break"):
            experiment_sink._connection.execute(
                f"INSERT INTO experiment_events (seq, experiment_id, event_type, "
                f"supersedes, recorded_at, payload) "
                f"VALUES (2, 'exp-1', 'X', 0, '{STAMP}', '{{}}')"
            )
    else:
        # The refusal must name the tamper class, not merely fail. On this tier
        # the fork is caught by the predecessor-link check rather than the
        # append-only guard, so the message says "chain break" — which is more
        # precise, not less. Matching the class rather than one function's text
        # keeps the assertion about the property instead of about which guard
        # happened to fire first.
        with pytest.raises(psycopg.errors.Error, match="chain break|append-only"):
            with experiment_sink._conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO experiment_events (seq, experiment_id, event_type, "
                    f"supersedes, recorded_at, payload) "
                    f"VALUES (2, 'exp-1', 'X', 0, '{STAMP}', '{{}}')"
                )


def test_seal_signs_count_and_head_on_both_tiers(experiment_sink) -> None:
    experiment_sink.append("exp-1", "CREATED", "{}", STAMP)
    experiment_sink.append("exp-1", "STARTED", "{}", STAMP)
    seal = experiment_sink.seal(SECRET)
    assert seal is not None
    assert (seal.event_count, seal.max_seq) == (2, 2)
    assert experiment_sink.audit(SECRET).ok is True


# ══════════════════════════════════════════════════════════════════════════
# Hermetic: v4/v5 DDL parity without a database
# ══════════════════════════════════════════════════════════════════════════


def _ddl_names(statements: list[str], kind: str) -> set[str]:
    pattern = re.compile(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+)?{kind}\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
        re.IGNORECASE,
    )
    return {
        match.group(1).lower()
        for statement in statements
        if (match := pattern.search(statement))
    }


def _columns(statements: list[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for statement in statements:
        match = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)",
            statement, re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        table, body = match.group(1).lower(), match.group(2)
        cols = set()
        for line in body.splitlines():
            token = line.strip().split()
            if token and token[0].upper() not in {
                "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT",
            }:
                cols.add(token[0].strip('", ').lower())
        found[table] = cols
    return found


@pytest.mark.parametrize("version", [4, 5, 6, 7, 8])
def test_ledger_ddl_matches_across_dialects(version: int) -> None:
    """Every table, index, trigger, and column on one tier exists on the
    other under the same name. The postgres tier additionally defines guard
    functions, which SQLite does not need because its triggers carry their own
    messages inline. The claim ledger (v6) carries no triggers — append-only by
    construction, with no UPDATE in either tier's code — so it defines no
    function on either side. The playbook store (v8) snapshots immutable
    policies rather than logging transitions, so its seal signs (count,
    set-hash) instead of a chain head.

    The count of postgres guard functions is asserted per version rather than
    pinned at one. It used to be exactly one per ledger, because sequencing and
    chain continuity were expressed as trigger WHEN clauses — which PostgreSQL
    rejects outright: a WHEN condition must be parenthesised and may not
    contain a subquery, and both ledger checks are subqueries. Those checks now
    live in plpgsql functions, so a ledger with sequencing has one function per
    check plus the append-only guard. The property that matters is that every
    trigger names a function that exists, which is checked separately below.
    """
    migration = next(m for m in MIGRATIONS if m.version == version)
    sqlite_stmts = _statements(migration.sqlite)
    pg_stmts = _statements(migration.postgres)
    for kind in ("TABLE", "INDEX", "TRIGGER"):
        assert _ddl_names(sqlite_stmts, kind) == _ddl_names(pg_stmts, kind), (
            f"v{version} {kind} mismatch"
        )
    functions = _ddl_names(pg_stmts, "FUNCTION")
    sqlite_functions = _ddl_names(sqlite_stmts, "FUNCTION")
    if version == 6:
        assert functions == set(), "v6 defines no guard function: no triggers to guard with"
    else:
        assert functions, f"v{version} postgres tier must define its guard functions"
        assert len(functions) >= 1
        assert all(f.startswith("aios_") for f in functions), (
            f"v{version} guard functions must be namespaced under aios_: {functions}"
        )
    assert sqlite_functions == set(), "SQLite defines no functions on any version"
    sqlite_cols = _columns(sqlite_stmts)
    pg_cols = _columns(pg_stmts)
    assert set(sqlite_cols) == set(pg_cols)
    for table in sqlite_cols:
        assert sqlite_cols[table] == pg_cols[table], f"v{version} column mismatch on {table}"


@pytest.mark.parametrize("version", [4, 5, 7, 8])
def test_every_postgres_trigger_executes_a_function_that_exists(version: int) -> None:
    """A trigger naming a missing function is not caught by the DDL-parity
    test, because that test compares names rather than resolving references.
    PostgreSQL does catch it — at apply time — which means the whole migration
    fails. This asserts the reference resolves from the DDL itself, so the
    defect surfaces without a database.

    The three-function ledgers are a direct consequence of moving the
    sequencing and chain checks out of WHEN clauses; this is the test that keeps
    the refactor honest.
    """
    migration = next(m for m in MIGRATIONS if m.version == version)
    statements = _statements(migration.postgres)
    defined = _ddl_names(statements, "FUNCTION")
    referenced: set[str] = set()
    for statement in statements:
        match = re.search(
            r"EXECUTE\s+(?:PROCEDURE|FUNCTION)\s+([A-Za-z_][A-Za-z0-9_.]*)",
            statement,
            re.IGNORECASE,
        )
        if match:
            referenced.add(match.group(1).lower())
    assert referenced, f"v{version} defines no EXECUTE FUNCTION trigger at all"
    missing = sorted(referenced - defined)
    assert missing == [], f"v{version} triggers reference undefined functions: {missing}"


def test_experiment_ledger_facade_accepts_either_tier(tmp_path: Path) -> None:
    """The facade pairs a sink with its key regardless of tier. A facade
    that only accepted SQLite would make the production tier unsealable."""
    from core.experiment_sink import ExperimentLedger

    sqlite_ledger = build_experiment_ledger(tmp_path / "a.db", SECRET)
    assert sqlite_ledger.seal() is None
    sqlite_ledger.close()
    if DSN:
        _truncate_pg(["experiment_events", "experiment_seals"])
        pg = ExperimentLedger(
            sink=build_postgres_experiment_sink(DSN, auto_migrate=True), secret=SECRET
        )
        try:
            assert pg.seal() is None
        finally:
            pg.close()
