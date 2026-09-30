"""The governance log has to outlive the process (goal G050).

``ToolGuardian`` recorded every decision it made and kept them in a list. On
restart, six hours of capital decisions — every allow, clamp, escalation, and
denial — were simply gone. A system that cannot say what it authorised last
Tuesday cannot answer the only question that matters after an incident.

This suite is built around one uncomfortable fact that is easy to get wrong:

**A hash chain does not detect truncation.**

The chain is a rolling digest over the entries present. Remove the last three
decisions and every remaining link still recomputes correctly — the log is
*shorter*, not *broken*, and any verification that stops at "the links hold"
passes. So a test suite that only checks tampering-within-the-log would report
a green result on a log that has had its tail cut off, which is the one
tamper an operator would most want to catch.

The seal is what closes that gap: an HMAC over the head, made with a key the
log cannot reach. Every test below is written from the attacker's position —
what can be done to this log, and does the audit notice?
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.decision_sink import (
    AppendOnlyViolation,
    DecisionLedger,
    GovernanceSeal,
    audit_log,
    build_decision_ledger,
)
from core.migrations import latest_version
from kernel.tool_governance import ToolGuardian, build_execution_guardian
from schemas.governance import Disposition, EvaluatorKind, GuardianDecision, ToolCall

SECRET = b"k" * 32
OTHER_SECRET = b"x" * 32


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════


def _call(symbol: str = "AAPL", quantity: float = 10.0) -> ToolCall:
    return ToolCall(
        tool="broker.submit",
        operation="place",
        capability="broker.order.place",
        agent_id="agent.strategy",
        intent="rebalance into the momentum sleeve",
        arguments={
            "symbol": {"value": symbol, "provenance": "OPERATOR"},
            "quantity": {"value": quantity, "provenance": "MODEL_DERIVED"},
        },
    )


def _guardian(tmp_path: Path, **kwargs: object) -> tuple[ToolGuardian, DecisionLedger]:
    ledger = build_decision_ledger(tmp_path / "governance.db", SECRET)
    guardian = ToolGuardian(SECRET, sink=ledger.sink, **kwargs)  # type: ignore[arg-type]
    return guardian, ledger


def _seed(guardian: ToolGuardian, count: int = 6) -> None:
    """Make ``count`` real decisions, alternating dispositions."""
    for index in range(count):
        guardian.evaluate(_call(symbol=f"SYM{index}", quantity=float(index + 1)))


# ══════════════════════════════════════════════════════════════════════════
# Durability: the log survives the process
# ══════════════════════════════════════════════════════════════════════════


def test_a_decision_is_readable_after_the_process_dies(tmp_path: Path) -> None:
    """The defect this goal fixes, stated as a test."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 4)
    ledger.seal()

    # Everything the process knew is now gone. A second, entirely separate
    # handle on the same file is what a restart actually looks like.
    reopened = build_decision_ledger(tmp_path / "governance.db", SECRET)
    decisions = reopened.decisions()

    assert len(decisions) == 4
    assert [d.call_digest for d in decisions] == [d.call_digest for d in guardian.log()]
    assert reopened.audit().ok is True
    reopened.close()


def test_a_restarted_guardian_continues_the_same_chain(tmp_path: Path) -> None:
    """Resume, not a second chain.

    A fresh guardian against the same store would start at genesis on top of
    the existing log, interleaving two unrelated histories where neither
    verifies. Adopting the stored head is the only construction that keeps the
    chain a chain.
    """
    first, ledger = _guardian(tmp_path)
    _seed(first, 3)
    ledger.seal()

    resumed = ToolGuardian.resume(SECRET, ledger.sink)
    assert resumed.chain_hash == ledger.head()
    assert resumed.log() == []

    resumed.evaluate(_call(symbol="AFTER", quantity=99.0))
    combined = ledger.decisions()
    assert len(combined) == 4
    assert audit_log(combined).chain_intact is True
    assert combined[0].call_digest != combined[-1].call_digest


def test_the_durable_log_matches_the_in_memory_log(tmp_path: Path) -> None:
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 5)
    assert [d.chain_hash for d in guardian.durable_log()] == [
        d.chain_hash for d in guardian.log()
    ]


def test_an_attached_guardian_reports_its_sink(tmp_path: Path) -> None:
    guardian, ledger = _guardian(tmp_path)
    assert guardian.sink is ledger.sink
    plain = ToolGuardian(SECRET)
    assert plain.sink is None
    assert plain.durable_log() == []


def test_denials_survive_a_restart(tmp_path: Path) -> None:
    """The query an operator actually runs, after the incident.

    Built from the real execution guardian rather than a stub, so the denials
    are produced by a capital rule and not written by hand.
    """
    ledger = build_decision_ledger(tmp_path / "governance.db", SECRET)
    guardian = build_execution_guardian(SECRET, max_notional=100_000.0, sink=ledger.sink)
    guardian.register_deny_rule(
        "SANCTIONS",
        lambda call: call.value_of("symbol") == "BANNED",
        policy_id="policy.sanctions",
    )
    guardian.evaluate(_call(symbol="AAPL", quantity=1e9))  # clamped, not denied
    guardian.evaluate(_call(symbol="BANNED", quantity=1.0))  # denied outright
    ledger.seal()

    reopened = build_decision_ledger(tmp_path / "governance.db", SECRET)
    denials = reopened.denials()
    assert len(denials) == 1
    assert all(d.reasoning for d in denials)
    assert "SANCTIONS" in denials[0].reasoning
    # And the clamp is retained alongside it, so the reduction is auditable too.
    assert len(reopened.decisions()) == 2
    reopened.close()


# ══════════════════════════════════════════════════════════════════════════
# The schema refuses to be tampered with
# ══════════════════════════════════════════════════════════════════════════


def test_an_update_is_refused_by_the_database(tmp_path: Path) -> None:
    """Not by a Python guard. By the database.

    A tamper attempt that has to be defeated by every call site being correct
    is a tamper attempt that succeeds the first time a call site is not. Note
    that this goes around the store API entirely — raw SQL, the way an attacker
    with a file handle would — and the schema still refuses.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "UPDATE governance_decisions SET reasoning = 'innocent' WHERE seq = 2"
        )
    assert "append-only" in str(excinfo.value)
    assert "UPDATE" in str(excinfo.value)


def test_a_delete_is_refused_by_the_database(tmp_path: Path) -> None:
    """This is how a denial disappears."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    ledger.seal()
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute("DELETE FROM governance_decisions WHERE seq = 2")
    assert "DELETE" in str(excinfo.value)
    assert ledger.sink.count() == 3


def test_a_seal_cannot_be_deleted_either(tmp_path: Path) -> None:
    """Deleting the seal is the cheaper tamper, and it must not work.

    An auditor who can remove the anchor can then truncate the log and the
    audit reports "no seal found" rather than "the seal is missing" — which
    reads as an unstarted ledger instead of a compromised one.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 2)
    ledger.seal()
    with pytest.raises(sqlite3.IntegrityError):
        ledger.sink._connection.execute("DELETE FROM governance_seals WHERE seq = 2")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.sink._connection.execute(
            "UPDATE governance_seals SET signature = 'x' WHERE seq = 2"
        )
    assert len(ledger.sink.seals()) == 1


def test_an_out_of_sequence_insert_is_refused_by_the_schema(tmp_path: Path) -> None:
    """A splice that skips an entry leaves a hole no chain check would see.

    Driven through raw SQL so the *trigger* is what refuses it, not the store's
    own pre-check. The store derives the sequence number from the log, so it
    could never present an out-of-order value; the trigger is the only thing
    standing between an attacker with SQL access and a rewritten sequence.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    row = ledger.sink.read_all()[-1]
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        ledger.sink._connection.execute(
            "INSERT INTO governance_decisions (seq, chain_hash, previous_chain_hash, "
            "disposition, call_digest, reasoning, evaluator, model_id, decided_at, payload) "
            "VALUES (99, 'ff', ?, 'ALLOW', 'd', 'r', 'DETERMINISTIC', NULL, 't', '{}')",
            (row.chain_hash,),
        )
    assert "sequence break" in str(excinfo.value)
    assert ledger.sink.count() == 3


def test_an_insert_onto_a_stale_head_is_refused(tmp_path: Path) -> None:
    """The guard and the store are allowed to disagree, and the store wins.

    If the store trusted the caller's ``previous_chain_hash``, a caller with a
    stale view of the chain would write a decision that links to a head which
    is no longer the head — silently forking the log.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 2)
    genesis = ""
    stale = ledger.sink.read_all()[0]
    with pytest.raises(AppendOnlyViolation) as excinfo:
        ledger.sink.append(stale, previous_chain_hash=genesis)
    assert "does not match the stored head" in str(excinfo.value)


# ══════════════════════════════════════════════════════════════════════════
# Truncation — the case a chain alone cannot catch
# ══════════════════════════════════════════════════════════════════════════


def test_a_truncated_log_verifies_against_itself_and_that_is_the_problem(
    tmp_path: Path,
) -> None:
    """Documented deliberately: this is the trap the seal exists to escape.

    Read this test as a warning, not a passing assertion. Anyone extending the
    audit must know that ``chain_intact`` alone is insufficient, because it is
    exactly the check that looks sufficient.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 6)
    ledger.seal()

    decisions = ledger.sink.read_all()
    truncated = decisions[:3]

    # Every link still holds. This is the whole hazard.
    naive = audit_log(truncated)
    assert naive.chain_intact is True
    assert naive.head != ledger.head()

    # And the audit that actually catches it.
    caught = audit_log(truncated, ledger.sink.seals(), SECRET)
    assert caught.ok is False
    assert "no seal" in caught.describe() or "truncat" in caught.describe()


def test_the_seal_is_what_catches_a_cut_tail(tmp_path: Path) -> None:
    """The headline property of this goal."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 8)
    ledger.seal()
    before = ledger.audit()
    assert before.ok is True

    # Simulate the tail being lost: an auditor reads only the first 5.
    shortened = ledger.sink.read_all()[:5]
    after = audit_log(shortened, ledger.sink.seals(), SECRET)
    assert after.ok is False
    assert after.sealed_through is None or after.chain_intact is False


def test_a_fully_sealed_log_passes_its_own_audit(tmp_path: Path) -> None:
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 4)
    ledger.seal()
    audit = ledger.audit()
    assert audit.ok is True
    assert audit.chain_intact is True
    assert audit.sealed_through == 4
    assert audit.unsealed_entries == 0
    assert "verified" in audit.describe()


def test_an_unsealed_log_is_unanchored_not_clean(tmp_path: Path) -> None:
    """No seal is not a pass. It is an absence of evidence.

    Reporting an unsealed log as ``ok`` would make "nobody ever called seal()"
    indistinguishable from "everything checked out", which is the failure mode
    that lets a whole unanchored audit pass review.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    audit = ledger.audit()
    assert audit.ok is False
    assert audit.sealed_through is None
    assert "unanchored" in audit.describe()


def test_entries_after_a_seal_are_reported_as_an_unanchored_tail(
    tmp_path: Path,
) -> None:
    """Legitimate after a restart — and named as unverified rather than assumed.

    A system that keeps governing past its last checkpoint is working
    correctly. The audit still has to say the tail is unanchored, because until
    it is sealed a truncation inside that window is invisible.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    ledger.seal()
    _seed(guardian, 2)  # more decisions after the seal

    audit = ledger.audit()
    assert audit.chain_intact is True
    assert audit.seal_signature_valid is True
    assert audit.sealed_through == 3
    assert audit.unsealed_entries == 2
    assert audit.ok is False
    assert "unanchored" in audit.describe()


def test_resealing_covers_the_new_tail(tmp_path: Path) -> None:
    """The seal is a checkpoint, so it can be taken again."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    ledger.seal()
    _seed(guardian, 2)
    assert ledger.audit().ok is False
    ledger.seal()
    audit = ledger.audit()
    assert audit.ok is True
    assert audit.sealed_through == 5


def test_sealing_an_empty_log_returns_nothing(tmp_path: Path) -> None:
    """A seal over genesis would attest to no decisions at all."""
    ledger = build_decision_ledger(tmp_path / "empty.db", SECRET)
    assert ledger.seal() is None
    assert ledger.audit().ok is False


# ══════════════════════════════════════════════════════════════════════════
# The seal cannot be forged
# ══════════════════════════════════════════════════════════════════════════


def test_a_seal_signed_with_another_key_does_not_verify() -> None:
    """Rotating or losing the key must invalidate the seal, not silently pass it."""
    seal = GovernanceSeal.sign(1, "a" * 64, "2024-01-01T00:00:00+00:00", SECRET)
    assert seal.verify(SECRET) is True
    assert seal.verify(OTHER_SECRET) is False


def test_editing_a_seal_in_place_invalidates_its_signature() -> None:
    """Re-deriving from stored fields is what makes this non-forgeable.

    Comparing digests instead would let an editor change ``chain_hash`` and
    have the check pass on the new value — the signature would be verifying
    itself.
    """
    seal = GovernanceSeal.sign(1, "a" * 64, "2024-01-01T00:00:00+00:00", SECRET)
    assert GovernanceSeal(1, "b" * 64, seal.sealed_at, seal.signature).verify(SECRET) is False
    assert GovernanceSeal(99, seal.chain_hash, seal.sealed_at, seal.signature).verify(SECRET) is False
    assert GovernanceSeal(seal.seq, seal.chain_hash, "later", seal.signature).verify(
        SECRET
    ) is False


def test_a_forged_seal_is_reported_as_compromised(tmp_path: Path) -> None:
    """The message must not read as a clean log with a missing checkpoint."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 3)
    ledger.seal()
    forged = GovernanceSeal(3, ledger.head(), "2024-01-01T00:00:00+00:00", "deadbeef")
    audit = audit_log(ledger.sink.read_all(), [forged], SECRET)
    assert audit.ok is False
    assert audit.seal_signature_valid is False


def test_auditing_without_a_key_reports_no_signature_claim(tmp_path: Path) -> None:
    """Absence of a key is not evidence of validity.

    With no key the links can be checked but the seal cannot, so the audit
    refuses rather than assuming the best.
    """
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 2)
    ledger.seal()
    audit = audit_log(ledger.sink.read_all(), ledger.sink.seals(), None)
    assert audit.ok is False
    assert audit.seal_signature_valid is False


# ══════════════════════════════════════════════════════════════════════════
# An edited decision breaks the chain
# ══════════════════════════════════════════════════════════════════════════


def test_editing_a_decision_breaks_the_chain(tmp_path: Path) -> None:
    """The case a chain *does* catch, to confirm the mechanism still works."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 4)
    ledger.seal()

    tampered = ledger.sink.read_all()
    innocent = tampered[1].model_copy(update={"reasoning": "looks fine to me"})
    tampered[1] = innocent

    result = audit_log(tampered, ledger.sink.seals(), SECRET)
    assert result.chain_intact is False
    assert result.ok is False
    assert "broken" in result.describe()


def test_reordering_decisions_breaks_the_chain(tmp_path: Path) -> None:
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 4)
    reordered = list(ledger.sink.read_all())
    reordered[1], reordered[2] = reordered[2], reordered[1]
    assert audit_log(reordered).chain_intact is False


def test_removing_a_middle_decision_breaks_the_chain(tmp_path: Path) -> None:
    """Truncation from the end is the seal's job; removal from the middle is
    the chain's, because the surviving links no longer agree."""
    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 4)
    gapped = [d for i, d in enumerate(ledger.sink.read_all()) if i != 2]
    assert audit_log(gapped).chain_intact is False


# ══════════════════════════════════════════════════════════════════════════
# Round-trip fidelity
# ══════════════════════════════════════════════════════════════════════════


def test_every_field_survives_the_round_trip(tmp_path: Path) -> None:
    """A log that loses the reasoning is not an audit log.

    The per-decision tests elsewhere in the suite check dispositions. This one
    checks the fields a reader would need in order to reconstruct *why* a call
    was reduced — which are exactly the fields a naive "store the essentials"
    implementation drops.
    """
    guardian, ledger = _guardian(tmp_path)
    original = guardian.evaluate(
        ToolCall(
            tool="broker.submit",
            operation="place",
            capability="broker.order.place",
            agent_id="agent.strategy",
            intent="rebalance after the signal decay",
            arguments={
                "symbol": {"value": "MSFT", "provenance": "OPERATOR"},
                "quantity": {"value": 500.0, "provenance": "MODEL_DERIVED"},
                "limit_price": {"value": 410.25, "provenance": "OPERATOR"},
            },
        )
    )
    ledger.seal()

    stored = build_decision_ledger(tmp_path / "governance.db", SECRET).decisions()[0]
    assert stored.disposition == original.disposition
    assert stored.reasoning == original.reasoning
    assert stored.call_digest == original.call_digest
    assert stored.evaluator == original.evaluator
    assert stored.chain_hash == original.chain_hash
    assert stored.reason_codes == original.reason_codes


def test_the_migration_is_registered() -> None:
    """The durable ledger is a schema step, so it must be one version."""
    assert latest_version() >= 4


def test_a_fresh_database_gets_the_ledger_schema(tmp_path: Path) -> None:
    ledger = build_decision_ledger(tmp_path / "new.db", SECRET)
    tables = {
        str(r[0])
        for r in ledger.sink._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"governance_decisions", "governance_seals"} <= tables
    ledger.close()


def test_building_a_ledger_without_a_secret_is_refused(tmp_path: Path) -> None:
    """An unsealable audit cannot be verified, so it is not offered."""
    with pytest.raises(ValueError, match="sealing secret"):
        build_decision_ledger(tmp_path / "nokey.db", b"")


def test_the_guard_still_fails_closed_with_a_sink(tmp_path: Path) -> None:
    """Durability must not have softened the guard itself."""
    guardian, ledger = _guardian(tmp_path)
    assert guardian.FAIL_CLOSED is True
    guardian.register_deny_rule(
        "SANCTIONS",
        lambda call: call.value_of("symbol") == "BANNED",
        policy_id="policy.sanctions",
    )
    from schemas.governance import ToolGovernanceError

    with pytest.raises(ToolGovernanceError):
        guardian.authorize(_call(symbol="BANNED"))
    assert ledger.sink.count() == 1
    ledger.close()


def test_a_denied_call_is_still_recorded(tmp_path: Path) -> None:
    """A refusal is the decision most worth keeping.

    If a denial raised before reaching the log, the log would contain only the
    calls that succeeded — an audit trail of compliance with no record of what
    was stopped, which is the half nobody asks for until it is the only half
    they have.
    """
    guardian, ledger = _guardian(tmp_path)
    guardian.register_deny_rule(
        "SANCTIONS",
        lambda call: call.value_of("symbol") == "BANNED",
        policy_id="policy.sanctions",
    )
    from schemas.governance import ToolGovernanceError

    with pytest.raises(ToolGovernanceError):
        guardian.authorize(_call(symbol="BANNED"))
    decisions = ledger.sink.read_all()
    assert len(decisions) == 1
    assert decisions[0].disposition is Disposition.DENY
    assert "SANCTIONS" in decisions[0].reasoning or decisions[0].reason_codes


def test_the_evaluator_is_retained_on_disk(tmp_path: Path) -> None:
    """Deterministic or agent-made is the first question an audit asks.

    Losing it means a log where a model decision and a code decision are
    indistinguishable, which is precisely the distinction the deterministic-first
    ordering exists to preserve.
    """
    guardian, ledger = _guardian(tmp_path)
    guardian.evaluate(_call())
    assert ledger.sink.read_all()[0].evaluator is EvaluatorKind.DETERMINISTIC


def test_concurrent_reads_see_a_consistent_log(tmp_path: Path) -> None:
    """The sink is shared across threads; a partial read would be worse than
    no read, because it would look like a complete one."""
    import threading

    guardian, ledger = _guardian(tmp_path)
    _seed(guardian, 10)
    results: list[int] = []
    errors: list[Exception] = []

    def read() -> None:
        try:
            results.append(len(ledger.sink.read_all()))
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert results == [10] * 8


def test_the_connection_is_not_closed_by_the_caller_s_absence(tmp_path: Path) -> None:
    """Sanity: the store is usable without anyone holding a guardian.

    A durable audit that can only be read through the live process is not
    durable in the sense the goal requires.
    """
    ledger = build_decision_ledger(tmp_path / "solo.db", SECRET)
    ledger.sink.append(
        GuardianDecision(
            disposition=Disposition.ALLOW,
            reasoning="written directly",
            evaluator=EvaluatorKind.DETERMINISTIC,
            call_digest="deadbeef",
            decided_at="2024-01-01T00:00:00+00:00",
            chain_hash="abc123",
        ),
        previous_chain_hash="",
    )
    assert ledger.sink.count() == 1
    assert ledger.head() == "abc123"
    ledger.close()
    with pytest.raises(sqlite3.ProgrammingError):
        ledger.sink.read_all()
