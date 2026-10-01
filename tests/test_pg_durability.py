"""Every PostgreSQL write path must commit. Checked structurally so it holds
without a database, and behaviourally where one exists.

The four durable sinks each wrap their INSERT in conn.transaction(). That
brackets the statement; it does not commit it. With autocommit off the row
stayed inside the connection's open transaction -- visible to that store's own
reads, invisible to every other connection, and discarded on close. Each sink's
tests passed anyway, because every one of them read through the same connection.

So the structural half asserts a commit follows each PostgreSQL INSERT within the
same method, and the behavioural half counts rows from a *separate* connection.
"""

from __future__ import annotations

import ast
import os

import pytest

ROOT_PARENT = "core"
DSN = os.environ.get("AIOS_TEST_PG_DSN", "")
NEEDS_PG = pytest.mark.skipif(
    not DSN, reason="set AIOS_TEST_PG_DSN to run the PostgreSQL durability legs"
)
SECRET = b"k" * 32
STAMP = "2026-01-01T00:00:00+00:00"

#: (dotted module, class) pairs whose Postgres methods are audited.
SINKS = [
    ("core.decision_sink", "PostgresDecisionSink"),
    ("core.experiment_sink", "PostgresExperimentSink"),
    ("core.dataset_version_sink", "PostgresDatasetVersionSink"),
    ("core.playbook_store", "PostgresPlaybookStore"),
]


def _class_ast(module: str, class_name: str) -> ast.ClassDef:
    """Parse the Postgres class's own source.

    Parsed rather than imported-and-introspected so the check sees the code as
    written, and so a rename that breaks the import fails here instead of
    surfacing as a confusing ModuleNotFoundError from a helper.
    """
    import importlib
    import inspect

    klass = getattr(importlib.import_module(module), class_name)
    parsed = ast.parse(inspect.getsource(klass))
    for node in parsed.body:
        if isinstance(node, ast.ClassDef):
            return node
    raise AssertionError(f"{module}.{class_name} is not a class")


def _method_with_insert(node: ast.ClassDef) -> list[str]:
    """Names of Postgres methods that contain an INSERT but no commit."""
    offenders: list[str] = []
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        source = ast.unparse(item)
        if "INSERT INTO" not in source:
            continue
        if ".commit()" not in source:
            offenders.append(item.name)
    return offenders


@pytest.mark.parametrize(("module", "class_name"), SINKS)
def test_every_postgres_write_path_commits(module: str, class_name: str) -> None:
    """`transaction()` brackets a statement; only commit() makes it durable.

    This is the property that was violated in all four sinks. Asserted
    structurally so it is checked on a machine with no PostgreSQL at all -- the
    original defect survived years of CI for exactly the opposite reason.
    """
    node = _class_ast(module, class_name)
    offenders = _method_with_insert(node)
    assert offenders == [], (
        f"{class_name} writes without committing in: {offenders}. Without a "
        "commit the row stays inside the connection's open transaction: visible "
        "to this store's own reads and to nothing else, and lost on close."
    )


@pytest.mark.parametrize(("module", "class_name"), SINKS)
def test_no_postgres_write_path_rolls_back_the_connection_itself(
    module: str, class_name: str
) -> None:
    """A connection-level rollback after a failed INSERT is wider than the
    failure.

    psycopg's transaction() has already undone the failed statement by the time
    the handler runs. Calling rollback() again discards the enclosing
    transaction too, including inserts that had already succeeded -- which is how
    the claim ledger's idempotent re-record deleted the claim it was absorbing.
    """
    node = _class_ast(module, class_name)
    offenders: list[str] = []
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(item):
            if not isinstance(sub, ast.ExceptHandler):
                continue
            body = ast.unparse(sub)
            if ".rollback()" in body:
                offenders.append(item.name)
    assert offenders == [], (
        f"{class_name} calls rollback() inside an exception handler: {offenders}. "
        "The transaction block has already undone the failed statement; a second "
        "rollback discards prior successful work on the same connection."
    )


def _rows_elsewhere(table: str) -> int:
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed names
        row = cur.fetchone()
        return 0 if row is None else int(row[0])


def _truncate(*tables: str) -> None:
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(tables))


# ══════════════════════════════════════════════════════════════════════════
# Behavioural: a second connection must see the row
# ══════════════════════════════════════════════════════════════════════════


@NEEDS_PG
@pytest.mark.parametrize(
    ("module", "factory", "table", "tables_to_clear"),
    [
        (
            "core.experiment_sink",
            "build_postgres_experiment_sink",
            "experiment_events",
            ("experiment_events", "experiment_seals"),
        ),
        (
            "core.dataset_version_sink",
            "build_postgres_dataset_version_sink",
            "dataset_version_events",
            ("dataset_version_events", "dataset_version_seals"),
        ),
    ],
)
def test_an_event_sink_write_outlives_its_connection(
    module: str, factory: str, table: str, tables_to_clear: tuple[str, ...]
) -> None:
    """An event log that cannot survive its own connection is a log, not a
    ledger -- and the ledger's whole claim is that history is recoverable
    after the fact."""
    import importlib

    build = getattr(importlib.import_module(module), factory)
    _truncate(*tables_to_clear)
    store = build(DSN, auto_migrate=True)
    try:
        store.append("durability-probe", "CREATED", "{}", STAMP)
        assert _rows_elsewhere(table) == 1, (
            f"{table}: a write must be visible to a different connection; "
            "otherwise it is lost when this one closes"
        )
    finally:
        store.close()
    assert _rows_elsewhere(table) == 1
    _truncate(*tables_to_clear)


@NEEDS_PG
def test_a_seal_outlives_its_connection() -> None:
    """The seal is the anchor that makes truncation detectable afterwards, so it
    is the one row that must persist. An unpersisted seal makes a restarted log
    report itself unanchored -- the anchoring mechanism causing the doubt it
    exists to settle."""
    from core.experiment_sink import build_postgres_experiment_sink

    _truncate("experiment_events", "experiment_seals")
    store = build_postgres_experiment_sink(DSN, auto_migrate=True)
    try:
        store.append("seal-probe", "CREATED", "{}", STAMP)
        assert store.seal(SECRET) is not None
    finally:
        store.close()
    assert _rows_elsewhere("experiment_seals") == 1, (
        "a seal must be committed: it is the external anchor against truncation"
    )
    _truncate("experiment_events", "experiment_seals")


@NEEDS_PG
def test_a_playbook_outlives_its_connection() -> None:
    """The store's own docstring promises "a restart loses the router's memory,
    not its policies". That is a claim about a different process, so it is
    checked from a different connection."""
    from core.playbook_store import build_postgres_playbook_store

    _truncate("playbooks", "playbook_seals")
    store = build_postgres_playbook_store(DSN, auto_migrate=True)
    try:
        assert store.save("pb-durable", "v1", "h1", "{}", STAMP) is True
    finally:
        store.close()
    assert _rows_elsewhere("playbooks") == 1
    _truncate("playbooks", "playbook_seals")


@NEEDS_PG
def test_a_refused_write_leaves_the_connection_usable() -> None:
    """A refused INSERT aborts the transaction; the next write must still work.

    Otherwise one schema refusal poisons the connection and every later call
    fails with InFailedSqlTransaction -- the database reporting its own aborted
    state instead of the store reporting anything.
    """
    import psycopg

    from core.playbook_store import build_postgres_playbook_store

    _truncate("playbooks", "playbook_seals")
    store = build_postgres_playbook_store(DSN, auto_migrate=True)
    try:
        store.save("pb-refusal", "v1", "h1", "{}", STAMP)
        with pytest.raises(psycopg.errors.Error, match="append-only"):
            with store._conn.cursor() as cur:
                cur.execute(
                    "UPDATE playbooks SET payload = 'x' WHERE playbook_id = 'pb-refusal'"
                )
        store._conn.rollback()
        assert store.save("pb-refusal-2", "v1", "h2", "{}", STAMP) is True
    finally:
        store.close()
        _truncate("playbooks", "playbook_seals")
