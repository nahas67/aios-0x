"""The migration splitter has to survive real DDL.

``_statements`` splits a migration's DDL on semicolons. That is correct only
until a migration contains a construct where a semicolon is not a statement
boundary, at which point the split silently produces fragments and the
database reports ``incomplete input`` — pointing at the wrong line entirely.

Two such constructs exist in this schema, and both arrived for the same reason:
a control had to be enforced by the database rather than by application code.
That is the right reason to need them, and it is exactly why the splitter has to
handle them.

This suite is mostly a defence against a plausible future "simplification".
``split(";")`` is shorter, looks obviously equivalent against v1–v3, and passes
every existing test until a trigger is added. The test below is what makes that
regression loud.
"""

from __future__ import annotations

import re

import pytest

from core.migrations import MIGRATIONS, _statements, latest_version

V4 = next(m for m in MIGRATIONS if m.version == 4)

#: ``CREATE TRIGGER IF NOT EXISTS name`` and ``CREATE TRIGGER name`` both occur,
#: so the name is matched rather than indexed.
_TRIGGER_NAME = re.compile(r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE)


def test_a_trigger_body_stays_one_statement() -> None:
    """The case that broke it.

    Every inner statement in a trigger body is semicolon-terminated, and the
    body is itself one statement. Splitting naively yields a fragment beginning
    ``SELECT RAISE(...)`` and a stray ``END`` — neither of which is valid SQL.
    """
    statements = _statements(V4.sqlite)
    triggers = [s for s in statements if "CREATE TRIGGER" in s]
    assert len(triggers) == 6
    for trigger in triggers:
        assert trigger.count("BEGIN") >= 1
        assert trigger.rstrip().endswith("END")
        # The inner terminator is preserved, which is the whole point.
        assert ";" in trigger


def test_no_fragment_starts_with_a_keyword_that_needs_a_head() -> None:
    """The symptom of a broken split, stated so it cannot recur quietly.

    A split that cut a trigger body produces statements beginning ``END`` or
    ``SELECT RAISE``. Asserting that no statement is a bare keyword catches the
    bug in a way that does not require knowing which migration introduced it.
    """
    for migration in MIGRATIONS:
        for statement in _statements(migration.sqlite):
            head = statement.split()[0].upper() if statement.split() else ""
            assert head not in {"END", "SELECT", "RAISE", "RETURN"}, (
                f"v{migration.version} produced a fragment starting with {head!r}: {statement!r}"
            )


def test_a_dollar_quoted_function_body_stays_one_statement() -> None:
    """The PostgreSQL tier carries the same hazard in a different costume.

    A PL/pgSQL function body holds ``RAISE ... ;`` inside ``$$ ... $$``. The
    dollar quoting is what makes it inert, and the splitter has to know that.
    """
    statements = _statements(V4.postgres)
    functions = [s for s in statements if "CREATE OR REPLACE FUNCTION" in s]
    assert len(functions) == 1
    body = functions[0]
    assert body.count("$$") == 2
    assert "RAISE EXCEPTION" in body
    assert body.rstrip().endswith("LANGUAGE plpgsql")


def test_a_semicolon_inside_a_string_literal_does_not_split() -> None:
    """A quoted message is data, not syntax.

    The trigger messages are the only strings in the schema containing no
    semicolon today, which is precisely why this is worth a test: the first
    author to write an error message ending in a semicolon would otherwise
    produce a fragment with no error at all.
    """
    sql = "CREATE TABLE probe (a TEXT DEFAULT 'x;y'); CREATE TABLE probe2 (b TEXT);"
    assert _statements(sql) == [
        "CREATE TABLE probe (a TEXT DEFAULT 'x;y')",
        "CREATE TABLE probe2 (b TEXT)",
    ]


def test_a_doubled_quote_is_an_escape_not_a_terminator() -> None:
    """SQL escapes a quote inside a literal by doubling it."""
    sql = "INSERT INTO probe VALUES ('it''s; fine'); SELECT 1;"
    assert _statements(sql) == ["INSERT INTO probe VALUES ('it''s; fine')", "SELECT 1"]


def test_comments_are_stripped_before_splitting() -> None:
    """A semicolon in a comment must not cut the statement below it.

    This is the original reason comments are removed first, and it is easy to
    regress while adding the new cases — the stripping is a whole-line filter,
    so a trailing comment on a line of code would not be caught here either.
    """
    sql = """
    -- a comment; with a semicolon
    CREATE TABLE probe (a TEXT);
    """
    assert _statements(sql) == ["CREATE TABLE probe (a TEXT)"]


def test_every_migration_round_trips_to_its_statement_count() -> None:
    """Counts are stable per version, so a splitter change shows up as a diff.

    Not a count-only assertion about the schema — a count assertion about the
    *splitter*, where a change in the number genuinely means the splitter's
    behaviour changed.
    """
    expected = {1: 17, 2: 19, 3: 8, 4: 8, 5: 9, 6: 5, 7: 9, 8: 6}
    for migration in MIGRATIONS:
        assert len(_statements(migration.sqlite)) == expected[migration.version], (
            f"v{migration.version} statement count changed; the splitter's behaviour "
            "is different from what the schema was written against"
        )


def test_a_drop_trigger_is_still_split_normally() -> None:
    """``DROP TRIGGER`` is not a ``CREATE TRIGGER`` body and must not be held open.

    The trigger-body tracking keys on the ``CREATE TRIGGER`` prefix specifically.
    Matching on ``TRIGGER`` alone would swallow every following statement on the
    PostgreSQL tier, where the migrations ``DROP`` then ``CREATE`` each one.
    """
    statements = _statements(V4.postgres)
    drops = [s for s in statements if s.strip().upper().startswith("DROP TRIGGER")]
    assert len(drops) == 6
    for drop in drops:
        assert "governance_" in drop
        assert " ON " in drop


def test_the_governance_triggers_cover_every_tamper_class() -> None:
    """The splitter preserving the bodies is only useful if the bodies are right.

    Four classes need four triggers on the decisions table — edit, delete,
    reorder, re-chain — and two more keeping the seals themselves immutable. A
    migration that dropped one would still apply cleanly, so the names are
    asserted rather than a count.
    """
    names = set()
    for statement in _statements(V4.sqlite):
        match = _TRIGGER_NAME.search(statement)
        if match:
            names.add(match.group(1))
    assert names == {
        "trg_governance_no_update",
        "trg_governance_no_delete",
        "trg_governance_seq_is_next",
        "trg_governance_chains_to_head",
        "trg_governance_seals_no_update",
        "trg_governance_seals_no_delete",
    }


def test_the_experiment_triggers_cover_every_tamper_class() -> None:
    """The v5 ledger stores one event per transition rather than one row per
    decision, so the continuity trigger links each event to its experiment's
    head (``supersedes``) instead of a global chain. Same guarantee, adapted
    shape: edit, delete, reorder, and re-link are each refused by name."""
    v5 = next(m for m in MIGRATIONS if m.version == 5)
    names = set()
    for statement in _statements(v5.sqlite):
        match = _TRIGGER_NAME.search(statement)
        if match:
            names.add(match.group(1))
    assert names == {
        "trg_experiment_no_update",
        "trg_experiment_no_delete",
        "trg_experiment_seq_is_next",
        "trg_experiment_links_to_predecessor",
        "trg_experiment_seals_no_update",
        "trg_experiment_seals_no_delete",
    }


def test_the_dataset_version_triggers_cover_every_tamper_class() -> None:
    """Same event-log shape as v5 under dataset names: edit, delete,
    reorder, and re-link each refused by name, seals immutable."""
    v7 = next(m for m in MIGRATIONS if m.version == 7)
    names = set()
    for statement in _statements(v7.sqlite):
        match = _TRIGGER_NAME.search(statement)
        if match:
            names.add(match.group(1))
    assert names == {
        "trg_dataset_version_no_update",
        "trg_dataset_version_no_delete",
        "trg_dataset_version_seq_is_next",
        "trg_dataset_version_links_to_predecessor",
        "trg_dataset_version_seals_no_update",
        "trg_dataset_version_seals_no_delete",
    }


def test_the_playbook_store_triggers_cover_every_tamper_class() -> None:
    """Snapshot table rather than event log: no sequence or linkage to guard,
    so edit and delete refusal on both tables is the whole guarantee. A
    migration that dropped one would still apply cleanly, so the names are
    asserted rather than a count."""
    v8 = next(m for m in MIGRATIONS if m.version == 8)
    names = set()
    for statement in _statements(v8.sqlite):
        match = _TRIGGER_NAME.search(statement)
        if match:
            names.add(match.group(1))
    assert names == {
        "trg_playbooks_no_update",
        "trg_playbooks_no_delete",
        "trg_playbook_seals_no_update",
        "trg_playbook_seals_no_delete",
    }


def test_the_latest_version_matches_the_registered_migrations() -> None:
    """``latest_version`` is derived, so this guards the derivation itself."""
    assert latest_version() == max(m.version for m in MIGRATIONS)
    assert latest_version() == 8


def test_migration_checksums_are_distinct() -> None:
    """Two migrations with the same checksum means one will not be re-applied.

    Drift detection compares checksums, so a collision would make a genuinely
    new migration look already-applied — the database would report a schema
    version that the code does not believe it wrote.
    """
    checksums = [m.checksum for m in MIGRATIONS]
    assert len(set(checksums)) == len(checksums)


def test_an_empty_migration_yields_no_statements() -> None:
    """Callers iterate the result, so an empty list must be safe to walk."""
    assert _statements("") == []
    assert _statements("   \n\n  ") == []
    assert _statements("-- only a comment") == []


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: f"v{m.version}")
def test_no_statement_ends_mid_identifier(migration: object) -> None:
    """A fragment is almost always cut at the wrong place.

    Cheap structural check across every migration on both dialects: nothing
    should end on a character that cannot legally end a statement.
    """
    for dialect in ("sqlite", "postgres"):
        for statement in _statements(getattr(migration, dialect)):
            assert statement.rstrip()[-1] not in ",+-*/=<>", (
                f"v{migration.version} {dialect} produced a fragment ending mid-token: "
                f"{statement[-40:]!r}"
            )
