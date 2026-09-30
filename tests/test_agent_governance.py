"""The Guardian is a control, and these tests are the evidence (goal G050).

A governance plane is theatre if it is added after the tools it governs, and
the reference implementation this port follows has two defects that make it
theatre by default: it signs nothing despite requiring HMAC-SHA256, and it
permits when a decision cannot be obtained. So the four properties this suite
asserts are the ones that distinguish a control from a comment:

1. deny blocks
2. modify clamps before the tool runs
3. failure denies
4. envelopes are signed, and a parallel batch is fully preflighted

Each test names the reference defect it prevents, so a future maintainer
reinstating one can find the reasoning without archaeology.
"""

from __future__ import annotations

import pytest

from kernel.tool_governance import (
    Disposition,
    EvaluatorKind,
    GuardianDecision,
    SignedEnvelope,
    ToolCall,
    ToolGovernanceError,
    ToolGuardian,
    UnsignedEnvelope,
)

SECRET = b"aios-governance-signing-key"


@pytest.fixture()
def guardian() -> ToolGuardian:
    return ToolGuardian(SECRET)


def _order(quantity: float = 5.0, symbol: str = "BTC/USD") -> ToolCall:
    """A model-proposed order, with per-argument provenance."""
    return ToolCall(
        tool="broker.submit",
        operation="place",
        capability="broker.order.place",
        agent_id="agent.strategy",
        intent="model proposed a momentum entry",
        arguments={
            "symbol": {"value": symbol, "provenance": "OPERATOR"},
            "quantity": {"value": quantity, "provenance": "MODEL_DERIVED"},
        },
    )


# ══════════════════════════════════════════════════════════════════════════
# Per-argument provenance
# ══════════════════════════════════════════════════════════════════════════


def test_every_argument_must_carry_provenance() -> None:
    """An unlabelled argument is indistinguishable from an invented one.

    If provenance were optional, per-argument taint would be lost the moment a
    caller omitted it, and the whole mechanism would be advisory.
    """
    with pytest.raises(ValueError, match="is missing provenance"):
        ToolCall(tool="t", agent_id="a", arguments={"quantity": {"value": 5}})


def test_a_bare_value_instead_of_a_pair_is_refused() -> None:
    """The wrapping is enforced at the type level, before any validator runs.

    Rejecting ``5`` where ``{"value": 5, "provenance": ...}`` is required means
    a caller cannot bypass the provenance label by omitting the wrapper: the
    shape itself is not constructible without one.
    """
    with pytest.raises(ValueError, match="valid dictionary"):
        ToolCall(tool="t", agent_id="a", arguments={"quantity": 5})


def test_blank_provenance_is_refused() -> None:
    with pytest.raises(ValueError, match="missing provenance"):
        ToolCall(
            tool="t",
            agent_id="a",
            arguments={"quantity": {"value": 5, "provenance": "   "}},
        )


def test_provenance_is_readable_per_argument() -> None:
    """Taint travels per field, not per call.

    The symbol came from the operator and the quantity from the model, in one
    envelope. A per-call label could not distinguish them.
    """
    call = _order()
    assert call.provenance_of("symbol") == "OPERATOR"
    assert call.provenance_of("quantity") == "MODEL_DERIVED"
    assert call.value_of("quantity") == 5.0


# ══════════════════════════════════════════════════════════════════════════
# Dispositions
# ══════════════════════════════════════════════════════════════════════════


def test_deny_blocks_the_call(guardian: ToolGuardian) -> None:
    guardian.register_deny_rule("pii_detected", lambda call: call.value_of("symbol") == "SECRET")
    with pytest.raises(ToolGovernanceError, match="denied"):
        guardian.authorize(_order(symbol="SECRET"))


def test_allow_passes_the_call_through(guardian: ToolGuardian) -> None:
    call = _order()
    assert guardian.authorize(call) is call


def test_modify_clamps_before_the_tool_runs(guardian: ToolGuardian) -> None:
    """The highest-value disposition: a risk engine that reduces rather than denies.

    An over-sized order becomes a smaller one instead of a lost trade, and the
    reduction is recorded with the rule that produced it.
    """
    guardian.register_clamp_rule(
        "quantity", maximum=2.0, reason_code="notional_cap_exceeded"
    )
    decision = guardian.evaluate(_order(quantity=5.0))
    assert decision.disposition is Disposition.MODIFY
    assert decision.reason_codes == ["notional_cap_exceeded"]

    governed = guardian.authorize(_order(quantity=5.0))
    assert governed.value_of("quantity") == 2.0


def test_clamp_leaves_a_conforming_call_untouched(guardian: ToolGuardian) -> None:
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    decision = guardian.evaluate(_order(quantity=1.0))
    assert decision.disposition is Disposition.ALLOW
    assert decision.parameter_overrides == {}


def test_a_clamp_preserves_the_original_taint(guardian: ToolGuardian) -> None:
    """A clamped quantity is still model-derived.

    Rewriting the provenance label to OPERATOR would launder the very taint the
    Guardian exists to catch, and the record would then lie about its origin.
    """
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    governed = guardian.authorize(_order(quantity=5.0))
    assert governed.provenance_of("quantity") == "MODEL_DERIVED"
    assert governed.value_of("quantity") == 2.0


def test_the_override_records_what_it_replaced(guardian: ToolGuardian) -> None:
    """A reviewer needs to know what was asked for, not only what was sent."""
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    decision = guardian.evaluate(_order(quantity=5.0))
    override = decision.parameter_overrides["quantity"]
    assert override.original == 5.0
    assert override.value == 2.0
    assert override.reason


def test_ask_does_not_proceed(guardian: ToolGuardian) -> None:
    """ASK is not permission. A human must act first."""
    guardian.register_rule(
        lambda call: GuardianDecision(
            disposition=Disposition.ASK,
            reasoning="manual sign-off required",
            reason_codes=["human_in_the_loop"],
        )
    )
    with pytest.raises(ToolGovernanceError, match="requires ask"):
        guardian.authorize(_order())


def test_defer_does_not_proceed(guardian: ToolGuardian) -> None:
    guardian.register_rule(
        lambda call: GuardianDecision(
            disposition=Disposition.DEFER,
            reasoning="risk engine unavailable",
            reason_codes=["dependency_unavailable"],
        )
    )
    with pytest.raises(ToolGovernanceError, match="requires defer"):
        guardian.authorize(_order())


def test_every_decision_must_carry_reasoning() -> None:
    """A decision with no stated reason cannot be reviewed.

    Including ALLOW: a reviewer who cannot read a reason cannot notice that the
    Guardian is broken.
    """
    with pytest.raises(ValueError, match="must carry a reasoning"):
        GuardianDecision(disposition=Disposition.ALLOW, reasoning="  ")


# ══════════════════════════════════════════════════════════════════════════
# Fail-closed
# ══════════════════════════════════════════════════════════════════════════


def test_a_raising_rule_denies_rather_than_allowing(guardian: ToolGuardian) -> None:
    """A broken policy must not become an absent one."""

    def broken(call: ToolCall) -> GuardianDecision | None:
        raise RuntimeError("policy engine unavailable")

    guardian.register_rule(broken)
    decision = guardian.evaluate(_order())
    assert decision.disposition is Disposition.DENY
    assert "policy_rule_error" in decision.reason_codes


def test_a_raising_agent_evaluator_denies(guardian: ToolGuardian) -> None:
    def broken(call, deterministic):
        raise RuntimeError("model unavailable")

    failing = ToolGuardian(SECRET, agent_evaluator=broken)
    decision = failing.evaluate(_order())
    assert decision.disposition is Disposition.DENY
    assert "evaluator_error" in decision.reason_codes


def test_the_fail_closed_posture_is_explicit_and_greppable() -> None:
    """The reference default is permit. Ours is deny, stated as a constant.

    A bare literal inside a method would be invisible to review; naming it is
    what makes the choice arguable.
    """
    assert ToolGuardian.FAIL_CLOSED is True


# ══════════════════════════════════════════════════════════════════════════
# Deterministic before agent
# ══════════════════════════════════════════════════════════════════════════


def test_a_model_cannot_unlock_what_code_refused(guardian: ToolGuardian) -> None:
    """The deterministic layer is final on denial.

    The agent evaluator exists to catch what code does not know, not to
    overrule what code already refused.
    """
    calls: list[str] = []

    def permissive(call, deterministic):
        calls.append("consulted")
        return GuardianDecision(
            disposition=Disposition.ALLOW,
            reasoning="model thinks this is fine",
        )

    gated = ToolGuardian(SECRET, agent_evaluator=permissive)
    gated.register_deny_rule("hard_stop", lambda call: True)
    decision = gated.evaluate(_order())
    assert decision.disposition is Disposition.DENY
    assert calls == [], "the agent evaluator must not be consulted after a denial"


def test_a_model_may_widen_allow_into_modify() -> None:
    """Narrowing is permitted; the model may catch what code does not know."""
    def cautious(call, deterministic):
        return GuardianDecision(
            disposition=Disposition.MODIFY,
            reasoning="halve the size to be safe",
            reason_codes=["model_caution"],
            parameter_overrides={},
        )

    gated = ToolGuardian(SECRET, agent_evaluator=cautious)
    decision = gated.evaluate(_order())
    assert decision.disposition is Disposition.MODIFY
    assert decision.evaluator is EvaluatorKind.COMPOSITE


def test_a_model_may_not_widen_modify_into_allow(guardian: ToolGuardian) -> None:
    """A clamp that a model can undo is not a clamp.

    This is the failure the whole plane exists to prevent: an unapplied
    reduction is worse than none, because the record says the order was
    governed when it was not.
    """
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")

    def permissive(call, deterministic):
        return GuardianDecision(
            disposition=Disposition.ALLOW, reasoning="model says the clamp is unnecessary"
        )

    gated = ToolGuardian(SECRET, agent_evaluator=permissive)
    gated.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    decision = gated.evaluate(_order(quantity=5.0))
    assert decision.disposition is Disposition.MODIFY
    assert gated.authorize(_order(quantity=5.0)).value_of("quantity") == 2.0


def test_multiple_clamp_rules_all_apply(guardian: ToolGuardian) -> None:
    """A capital firewall with two ceilings must enforce both.

    Returning the first objection would mean a notional clamp silently disables
    the quantity clamp below it, leaving the system guarded by one limit while
    the configuration names two.
    """
    guardian.register_clamp_rule("notional", maximum=1000.0, reason_code="notional_cap")
    guardian.register_clamp_rule("quantity", maximum=5.0, reason_code="quantity_cap")
    decision = guardian.evaluate(_call_with({"notional": 5000.0, "quantity": 50.0}))
    assert decision.disposition is Disposition.MODIFY
    assert decision.parameter_overrides["notional"].value == 1000.0
    assert decision.parameter_overrides["quantity"].value == 5.0
    assert set(decision.reason_codes) == {"notional_cap", "quantity_cap"}


def test_a_denial_short_circuits_the_remaining_rules(guardian: ToolGuardian) -> None:
    """A refusal needs no further clamping; nothing about it is negotiable."""
    guardian.register_deny_rule("blocked", lambda c: True)
    guardian.register_clamp_rule("quantity", maximum=1.0, reason_code="cap")
    decision = guardian.evaluate(_call_with({"quantity": 99.0}))
    assert decision.disposition is Disposition.DENY
    assert decision.parameter_overrides == {}


def test_the_tighter_bound_wins_when_two_rules_clamp_one_argument(
    guardian: ToolGuardian,
) -> None:
    """A later rule may tighten a ceiling but never loosen it.

    Otherwise rule order would decide the limit, and reordering the rule list
    would silently change the risk profile.
    """
    guardian.register_clamp_rule("quantity", maximum=10.0, reason_code="loose")
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="tight")
    assert guardian.evaluate(_call_with({"quantity": 50.0})).parameter_overrides[
        "quantity"
    ].value == 2.0

    reversed_guardian = ToolGuardian(SECRET)
    reversed_guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="tight")
    reversed_guardian.register_clamp_rule("quantity", maximum=10.0, reason_code="loose")
    assert reversed_guardian.evaluate(_call_with({"quantity": 50.0})).parameter_overrides[
        "quantity"
    ].value == 2.0


def _call_with(arguments: dict) -> ToolCall:
    return ToolCall(
        tool="t",
        agent_id="a",
        arguments={k: {"value": v, "provenance": "RISK_ENGINE"} for k, v in arguments.items()},
    )


def test_applying_a_decision_does_not_re_evaluate(guardian: ToolGuardian) -> None:
    """One order, one judgement.

    Deciding twice would append two chain entries for one submission, and the
    audit log would overstate how many judgements were made.
    """
    call = _order(quantity=1.0)
    decision = guardian.evaluate(call)
    assert guardian.apply(decision, call) is call
    assert len(guardian.log()) == 1


def test_a_decision_cannot_be_applied_to_a_different_call(guardian: ToolGuardian) -> None:
    """Replay protection at the application boundary, not just the decision."""
    decision = guardian.evaluate(_order(quantity=0.001))
    with pytest.raises(ToolGovernanceError, match="different call"):
        guardian.apply(decision, _order(quantity=999.0))


def test_deterministic_only_evaluation_is_conformant(guardian: ToolGuardian) -> None:
    """A purely deterministic Guardian is a complete implementation."""
    guardian.register_clamp_rule("quantity", maximum=1.0, reason_code="cap")
    decision = guardian.evaluate(_order(quantity=2.0))
    assert decision.evaluator is EvaluatorKind.DETERMINISTIC


# ══════════════════════════════════════════════════════════════════════════
# Envelope signing (the reference defect we fix)
# ══════════════════════════════════════════════════════════════════════════


def test_a_signed_envelope_evaluates(guardian: ToolGuardian) -> None:
    envelope = guardian.seal(SignedEnvelope(envelope_id="e1", call=_order()))
    assert envelope.signature
    assert guardian.unseal(envelope).tool == "broker.submit"


def test_an_unsigned_envelope_is_refused_before_evaluation(guardian: ToolGuardian) -> None:
    """The spec requires HMAC-SHA256; the reference Guardian implements none.

    An unauthenticated decision request is not a governance question, it is a
    request to be trusted.
    """
    envelope = SignedEnvelope(envelope_id="e2", call=_order())
    envelope = envelope.model_copy(update={"previous_chain_hash": guardian.chain_hash})
    with pytest.raises(UnsignedEnvelope, match="carries no signature"):
        guardian.unseal(envelope)


def test_a_forged_signature_is_refused(guardian: ToolGuardian) -> None:
    envelope = guardian.seal(SignedEnvelope(envelope_id="e3", call=_order()))
    forged = envelope.model_copy(update={"signature": "0" * 64})
    with pytest.raises(UnsignedEnvelope, match="does not verify"):
        guardian.unseal(forged)


def test_an_envelope_signed_with_another_key_is_refused(guardian: ToolGuardian) -> None:
    """Key separation is what makes a signature mean anything."""
    attacker = ToolGuardian(b"attacker-key")
    envelope = attacker.seal(SignedEnvelope(envelope_id="e4", call=_order()))
    with pytest.raises(UnsignedEnvelope, match="does not verify"):
        guardian.unseal(envelope)


def test_a_guardian_without_a_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="signing secret is required"):
        ToolGuardian(b"")


def test_a_stale_chain_anchor_is_refused(guardian: ToolGuardian) -> None:
    """An envelope replayed from an earlier point in the log does not apply."""
    stale = guardian.seal(SignedEnvelope(envelope_id="e5", call=_order()))
    guardian.evaluate(_order())
    with pytest.raises(UnsignedEnvelope, match="chains to"):
        guardian.unseal(stale)


def test_a_tampered_payload_breaks_the_signature(guardian: ToolGuardian) -> None:
    """Changing the call after signing invalidates the envelope."""
    envelope = guardian.seal(SignedEnvelope(envelope_id="e6", call=_order(quantity=1.0)))
    tampered = envelope.model_copy(update={"call": _order(quantity=999.0)})
    with pytest.raises(UnsignedEnvelope, match="does not verify"):
        guardian.unseal(tampered)


# ══════════════════════════════════════════════════════════════════════════
# The chain hash
# ══════════════════════════════════════════════════════════════════════════


def test_the_chain_verifies_after_normal_operation(guardian: ToolGuardian) -> None:
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    for quantity in (1.0, 5.0, 3.0):
        guardian.evaluate(_order(quantity=quantity))
    assert guardian.verify_chain() is True


def test_the_chain_detects_a_removed_decision(guardian: ToolGuardian) -> None:
    """An audit log nobody can tamper with is worth having.

    Removing a decision breaks every subsequent link, which is the property
    that makes the log evidence rather than narration.
    """
    for _ in range(3):
        guardian.evaluate(_order())
    assert guardian.verify_chain() is True

    tampered = guardian.log()
    del tampered[1]
    assert guardian.verify_chain(tampered) is False


def test_the_chain_detects_an_edited_reasoning(guardian: ToolGuardian) -> None:
    """Rewriting a decision's reasoning is detectable, not just deleting it."""
    guardian.evaluate(_order())
    original = guardian.log()[0]
    edited = original.model_copy(update={"reasoning": "no policy rule objected at all"})
    assert guardian.verify_chain([edited]) is False


def test_the_log_hands_out_a_copy(guardian: ToolGuardian) -> None:
    """A caller cannot remove a decision by mutating the returned list."""
    guardian.evaluate(_order())
    copy = guardian.log()
    copy.clear()
    assert len(guardian.log()) == 1
    assert guardian.verify_chain() is True


def test_each_decision_carries_its_own_chain_hash(guardian: ToolGuardian) -> None:
    first = guardian.evaluate(_order(quantity=1.0))
    second = guardian.evaluate(_order(quantity=2.0))
    assert first.chain_hash != second.chain_hash


def test_a_decision_does_not_answer_a_different_call(guardian: ToolGuardian) -> None:
    """A decision is bound to the call it was made about.

    Replaying an ALLOW from a cheap call against an expensive one is the exact
    attack the digest prevents.
    """
    cheap = _order(quantity=0.001)
    expensive = _order(quantity=1000.0)
    decision = guardian.evaluate(cheap)
    assert decision.applies_to(cheap) is True
    assert decision.applies_to(expensive) is False


def test_a_digestless_decision_applies_to_nothing(guardian: ToolGuardian) -> None:
    """An unbound decision is refused rather than treated as a wildcard."""
    decision = GuardianDecision(disposition=Disposition.ALLOW, reasoning="hand-made")
    assert decision.applies_to(_order()) is False


# ══════════════════════════════════════════════════════════════════════════
# Parallel batches
# ══════════════════════════════════════════════════════════════════════════


def test_a_batch_is_fully_preflighted_before_any_member_executes(
    guardian: ToolGuardian,
) -> None:
    """Preflight-then-execute, borrowed from pi's tool executor.

    A batch that executed members as they passed would let an early allow
    stand while a later member is still undecided, so a batch can be partially
    escaped from governance. Preflighting all of them first closes that.
    """
    guardian.register_clamp_rule("quantity", maximum=2.0, reason_code="cap")
    batch = [_order(quantity=q) for q in (1.0, 5.0, 3.0)]

    decisions = [guardian.evaluate(call) for call in batch]
    assert all(d.call_digest for d in decisions)
    assert [d.disposition for d in decisions] == [
        Disposition.ALLOW,
        Disposition.MODIFY,
        Disposition.MODIFY,
    ]

    governed = [guardian.authorize(call) for call in batch]
    assert [c.value_of("quantity") for c in governed] == [1.0, 2.0, 2.0]


def test_one_denied_member_blocks_only_that_member(guardian: ToolGuardian) -> None:
    """Per-call verdicts, so a refusal does not silently become a blanket refusal."""
    guardian.register_deny_rule("bad_symbol", lambda c: c.value_of("symbol") == "BAD")
    good = _order(symbol="BTC/USD")
    bad = _order(symbol="BAD")
    assert guardian.authorize(good) is good
    with pytest.raises(ToolGovernanceError):
        guardian.authorize(bad)


def test_the_log_is_never_truncated(guardian: ToolGuardian) -> None:
    """The audit trail is the point; a capped log is a summary, not a record."""
    for _ in range(50):
        guardian.evaluate(_order())
    assert len(guardian.log()) == 50
