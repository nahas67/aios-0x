"""Regressions for three Postgres-only defects, as hermetic tests where possible.

Each defect was found by running the parity suite against a real PostgreSQL
tier after years of it skipping. All three are dialect divergences that no
SQLite-only suite can see, and all three were silent: a log that failed its own
audit, a no-op that deleted the record it was absorbing, and a digest that made
the same belief hash differently per tier.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from core.claim_ledger import Claim, SourceArtifact, _same_assertion
from core.decision_sink import ts_str
from core.security_master import InstrumentIdentity

# ══════════════════════════════════════════════════════════════════════════
# Seal timestamps: str(datetime) != isoformat(datetime)
# ══════════════════════════════════════════════════════════════════════════


def test_ts_str_renders_a_datetime_the_way_it_was_signed() -> None:
    """PostgreSQL returns TIMESTAMPTZ as a datetime; SQLite returns TEXT.

    str() of a datetime puts a space where isoformat() puts T, so a seal signed
    over the ISO string verifies against different bytes on the production tier
    and every audit reports tampering where none occurred.
    """
    from datetime import UTC, datetime

    moment = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    iso = moment.isoformat()
    assert ts_str(moment) == iso
    assert str(moment) != iso, (
        "if str() and isoformat() ever agreed this test would stop proving "
        "anything -- which is the point of asserting the difference is real"
    )


def test_ts_str_passes_strings_through_unchanged() -> None:
    """The SQLite tier already holds the canonical string; normalising must not
    second-guess it, or a value would be rewritten on every round trip."""
    canonical = "2026-01-02T03:04:05.678901+00:00"
    assert ts_str(canonical) == canonical


def test_ts_str_is_idempotent() -> None:
    """Normalising an already-normalised value must be a no-op, so repeated
    reads cannot drift the bytes a signature covers."""
    from datetime import UTC, datetime

    moment = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    once = ts_str(moment)
    assert ts_str(once) == once


def test_a_seal_verifies_after_a_timestamptz_round_trip() -> None:
    """The end-to-end property, at the level the audit depends on.

    A seal signed over an ISO string must still verify when that string has been
    through a column that hands it back as a datetime -- which is what every
    Postgres read does.
    """
    import hashlib
    import hmac
    from datetime import UTC, datetime

    moment = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    secret = b"k" * 32
    signed_text = moment.isoformat()
    signature = hmac.new(
        secret, f"1|head|{signed_text}".encode(), hashlib.sha256
    ).hexdigest()

    # Simulate the column round trip: what comes back is a datetime, and the
    # reader renders it.
    read_back = ts_str(moment)
    recomputed = hmac.new(
        secret, f"1|head|{read_back}".encode(), hashlib.sha256
    ).hexdigest()

    assert recomputed == signature, (
        "a seal must survive the TIMESTAMPTZ round trip, or every audit on the "
        "production tier reports tampering that did not happen"
    )


# ══════════════════════════════════════════════════════════════════════════
# identity_digest: Decimal scale differs per dialect
# ══════════════════════════════════════════════════════════════════════════


def _identity(**overrides: Any) -> InstrumentIdentity:
    from datetime import UTC, datetime

    moment = datetime(2024, 1, 1, tzinfo=UTC)
    base: dict[str, Any] = {
        "instrument_id": "i1",
        "listing_id": "XNYS:i1",
        "ticker": "ABC",
        "mic": "XNYS",
        "venue": "XNYS",
        "asset_class": "EQUITY",
        "security_type": "COMMON",
        "currency": "USD",
        "valid_from": moment,
        "recorded_from": moment,
        "source": "test",
        "tick_size": Decimal("0.01"),
        "lot_size": Decimal("1"),
    }
    base.update(overrides)
    return InstrumentIdentity(**base)


def test_digest_ignores_decimal_scale() -> None:
    """NUMERIC declares a scale, so Postgres returns 0.01 as 0.010000000000 while
    SQLite returns 0.01. Same belief, different digest."""
    assert _identity(tick_size=Decimal("0.01")).identity_digest() == _identity(
        tick_size=Decimal("0.010000000000")
    ).identity_digest()
    assert _identity(lot_size=Decimal("1")).identity_digest() == _identity(
        lot_size=Decimal("1.000000000000")
    ).identity_digest()


def test_digest_still_distinguishes_different_decimals() -> None:
    """Normalising scale must not collapse genuinely different values."""
    assert _identity(tick_size=Decimal("0.01")).identity_digest() != _identity(
        tick_size=Decimal("0.1")
    ).identity_digest()
    assert _identity(lot_size=Decimal("1")).identity_digest() != _identity(
        lot_size=Decimal("2")
    ).identity_digest()


def test_digest_still_reflects_a_content_change() -> None:
    """A real revision must produce a different digest, or the no-op would
    swallow the very changes the ledger exists to record."""
    assert _identity(ticker="ABC").identity_digest() != _identity(
        ticker="XYZ"
    ).identity_digest()
    assert _identity(security_type="COMMON").identity_digest() != _identity(
        security_type="ETF"
    ).identity_digest()


def test_decimal_normalisation_handles_a_positive_exponent() -> None:
    """Decimal("1E+2").normalize() is 1E+2; str() of it must not raise.

    gt=Decimal(0) on the model means this cannot arise from ordinary input, but
    the digest is a security-relevant hash and should not be one bad field away
    from an exception.
    """
    from core.security_master import InstrumentIdentity as IM

    assert IM._digest_value(Decimal("1E+2")) == "1E+2"
    assert IM._digest_value(Decimal("0.0100")) == "0.01"
    assert IM._digest_value(None) == "None"
    assert IM._digest_value("TEXT") == "TEXT"


# ══════════════════════════════════════════════════════════════════════════
# Idempotent claim re-record must not delete the claim it absorbs
# ══════════════════════════════════════════════════════════════════════════


def _claim(artifact: SourceArtifact, claim_object: float = 67234.12) -> Claim:
    from core.claim_ledger import ClaimClass, ClaimVerdict, ProvenanceTag

    return Claim(
        claim_id="claim-1",
        subject_id="BTC/USD",
        predicate="close_price",
        claim_object=claim_object,
        claim_class=ClaimClass.OBSERVED,
        provenance=ProvenanceTag.EXTRACTED,
        evidence_refs=["feed-bar-1", "feed-bar-2"],
        source_artifact_id=artifact.artifact_id,
        source_hash=artifact.source_hash,
        confidence=0.8,
        verdict=ClaimVerdict.SUFFICIENT,
    )


def _artifact() -> SourceArtifact:
    return SourceArtifact.create(
        "close 67234.12 at 2024-05-01T00:00:00Z",
        kind="feed-bar",
        source="test-feed",
    )


def test_an_identical_reassertion_is_recognised_as_identical() -> None:
    """_same_assertion is what the Postgres idempotency path consults after a
    unique violation. If it disagrees with itself the path can never absorb a
    replay."""
    claim = _claim(_artifact())
    assert _same_assertion(claim, _claim(_artifact())) is True
    assert _same_assertion(claim, _claim(_artifact(), claim_object=0.9)) is False


def test_rollback_of_a_failed_insert_must_not_reach_prior_work() -> None:
    """The defect, stated without a database.

    psycopg's `transaction()` block already rolls back the statement that
    failed. An extra connection-level rollback() on top of that discards the
    enclosing transaction too -- including an insert that had already succeeded.
    The original code did exactly this, so a re-record returned the right claim
    and simultaneously deleted it.

    Asserted as a shape rather than as behaviour because reproducing it needs a
    driver and a live server; the behavioural half lives in
    tests/test_claim_ledger_parity.py, which runs when AIOS_TEST_PG_DSN is set.
    """
    import inspect

    from core.claim_ledger import PostgresClaimLedger

    source = inspect.getsource(PostgresClaimLedger.record_claim)
    handler = source.split("except self._psycopg.errors.UniqueViolation", 1)[1]
    # Everything after the handler's own `raise` is unreachable, so only the
    # live portion before it is relevant. Comments are stripped too: the fix's
    # own explanation names the call it removed, and matching inside prose
    # would report the fix as the defect.
    live = handler.split("\n        raise ClaimLedgerError", 1)[0]
    code_only = "\n".join(
        line for line in live.splitlines() if not line.lstrip().startswith("#")
    )

    assert "self._conn.rollback()" not in code_only, (
        "the unique-violation handler must not roll the connection back again: "
        "the transaction() block has already undone the failed insert, and a "
        "second rollback discards prior successful work too"
    )


def test_unique_violation_handler_reads_with_a_dict_row_factory() -> None:
    """_row_to_claim takes a mapping. A plain psycopg cursor yields a positional
    tuple, and dict(tuple_of_7_columns) raises ValueError -- which is how the
    idempotent path failed before it could even compare."""
    import inspect

    from core.claim_ledger import PostgresClaimLedger

    source = inspect.getsource(PostgresClaimLedger.record_claim)
    handler = source.split("except self._psycopg.errors.UniqueViolation", 1)[1]
    live = handler.split("\n        raise ClaimLedgerError", 1)[0]
    code_only = "\n".join(
        line for line in live.splitlines() if not line.lstrip().startswith("#")
    )
    assert "dict_row" in code_only, (
        "the unique-violation handler must read with a dict row factory"
    )


# ══════════════════════════════════════════════════════════════════════════
# Migration DDL: PostgreSQL trigger WHEN clauses
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("version", [4, 5, 6, 7, 8])
def test_no_postgres_trigger_uses_a_when_clause_with_a_subquery(version: int) -> None:
    """PostgreSQL forbids a subquery inside a trigger WHEN condition, and
    requires the condition to be parenthesised.

    Every sequencing and chain-continuity check in these ledgers is a subquery,
    so expressing them as WHEN clauses produced DDL that no machine could apply.
    Migration v4 therefore never applied on PostgreSQL: the append-only and
    sequencing guarantees the ledger documents have never actually run on the
    production tier. The checks now live in plpgsql functions.
    """
    import re

    from core.migrations import MIGRATIONS, _statements

    migration = next(m for m in MIGRATIONS if m.version == version)
    offenders: list[str] = []
    for statement in _statements(migration.postgres):
        upper = " ".join(statement.split()).upper()
        if "CREATE TRIGGER" not in upper:
            continue
        match = re.search(r"\bWHEN\b(.*?)(?:EXECUTE\s+(?:FUNCTION|PROCEDURE))", upper)
        if not match:
            continue
        condition = match.group(1)
        if "NEW." in condition or "SELECT" in condition:
            offenders.append(" ".join(statement.split())[:150])

    assert offenders == [], (
        f"v{version} defines a WHEN clause PostgreSQL will reject: {offenders}"
    )


@pytest.mark.parametrize("version", [4, 5, 7, 8])
def test_every_postgres_trigger_function_reference_resolves(version: int) -> None:
    """A trigger naming an undefined function fails at apply time, which is how
    the whole migration fails. Asserted from the DDL so it surfaces without a
    database."""
    import re

    from core.migrations import MIGRATIONS, _statements

    migration = next(m for m in MIGRATIONS if m.version == version)
    statements = _statements(migration.postgres)
    defined = {
        m.group(1).lower()
        for s in statements
        for m in [
            re.search(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)", s, re.IGNORECASE
            )
        ]
        if m
    }
    referenced = {
        m.group(1).lower()
        for s in statements
        for m in [
            re.search(
                r"EXECUTE\s+(?:PROCEDURE|FUNCTION)\s+(\w+)", s, re.IGNORECASE
            )
        ]
        if m
    }
    assert referenced, f"v{version} defines no EXECUTE FUNCTION trigger at all"
    assert sorted(referenced - defined) == [], (
        f"v{version} triggers reference functions the migration never defines: "
        f"{sorted(referenced - defined)}"
    )


def test_ledger_guards_live_in_function_bodies_not_when_clauses() -> None:
    """The sequencing and chain checks must be reachable at all.

    This is the positive statement of the same property: the guard exists, it is
    a function, and a trigger invokes it. Without this the previous test could
    pass simply by having deleted the guarantees.
    """
    from core.migrations import MIGRATIONS, _statements

    migration = next(m for m in MIGRATIONS if m.version == 4)
    statements = _statements(migration.postgres)
    joined = " ".join(statements)
    assert "aios_governance_seq_is_next" in joined, (
        "the governance ledger's sequence guard must exist as a function"
    )
    assert "aios_governance_chains_to_head" in joined, (
        "the governance ledger's chain guard must exist as a function"
    )
    assert "EXECUTE FUNCTION aios_governance_seq_is_next()" in joined
    assert "EXECUTE FUNCTION aios_governance_chains_to_head()" in joined
