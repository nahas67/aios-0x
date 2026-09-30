"""Tool-call governance: deterministic first, chain-hashed, fail-closed.

A guard inspects what an agent is about to do and answers allow, deny, modify,
ask, or defer. That is the whole concept, and the concept is not novel. What
matters is the four properties the reference implementation
(GenAI-Security-Project/agent-control-standard v0.1.0) gets wrong or omits, all
of which are corrected here rather than inherited:

1. **Per-argument provenance.** Every argument is a ``{value, provenance}``
   pair, not a bare value. This is the single most valuable part of the spec,
   because it makes taint per-field rather than per-call: a quantity derived
   from a model is distinguishable from a symbol the model was merely told
   about, even when both arrive in the same envelope.

2. **Signed envelopes.** The spec requires baseline HMAC-SHA256; the reference
   Guardian implements none (its issue #70). An unsigned governance decision is
   an unauthenticated instruction, so every envelope here carries a signature
   over a canonical payload and an unsigned envelope is refused.

3. **Fail-closed.** The reference default is ``proceed`` when a decision cannot
   be obtained, so a broken governance path silently stops governing (its
   issues #32 and #37). Here the default is deny, and a guard that raises
   denies.

4. **Deterministic before agent.** Any LLM evaluator runs *after* the
   deterministic policy layer and must clear it on the way back. A model
   cannot unlock what code refused, and cannot loosen what code reduced.

The ``modify`` disposition is the interesting one: the guard rewrites
arguments before the tool runs. That is how a risk engine clamps a position
size, forces a LIMIT order, or injects a paper-trading flag at the tool
boundary rather than trusting a caller to have applied them.

The wire types live in :mod:`schemas.governance` because ``communities/`` may
import schema contracts but never ``kernel/``. This module supplies the
implementation that a composition root injects.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from schemas.governance import (
    DecisionSink,
    Disposition,
    EvaluatorKind,
    GovernanceError,
    GuardianDecision,
    ParameterOverride,
    PolicyReference,
    ToolCall,
    ToolGovernanceError,
    ToolGuard,
)

__all__ = [
    "Disposition",
    "GovernanceError",
    "GuardianDecision",
    "SignedEnvelope",
    "ToolCall",
    "ToolGovernanceError",
    "ToolGuard",
    "ToolGuardian",
    "UnsignedEnvelope",
    "build_execution_guardian",
    "guardian_secret_from_env",
]


class UnsignedEnvelope(GovernanceError):
    """An envelope arrived without a valid signature.

    An unsigned governance decision is an unauthenticated instruction from
    whoever can reach the socket. It is refused rather than evaluated.
    """


class SignedEnvelope(BaseModel):
    """A governance envelope carrying an HMAC over its canonical payload.

    Signing is what makes the audit chain worth anything. Without it, anyone
    who can reach the socket can assert a decision, and the chain hash records
    the forgery as faithfully as it records a real one.
    """

    envelope_id: str = Field(..., min_length=1)
    call: ToolCall
    issued_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    signature: str = Field(
        default="", description="hex HMAC-SHA256; empty means unsigned and is refused"
    )
    previous_chain_hash: str = Field(default="", description="Prior audit head")

    def payload(self) -> str:
        return json.dumps(
            {
                "envelope_id": self.envelope_id,
                "call": self.call.canonical(),
                "issued_at": self.issued_at,
                "previous_chain_hash": self.previous_chain_hash,
            },
            sort_keys=True,
        )

    def sign(self, secret: bytes) -> SignedEnvelope:
        """Return a copy carrying the HMAC over the payload."""
        mac = hmac.new(secret, self.payload().encode(), hashlib.sha256)
        return self.model_copy(update={"signature": mac.hexdigest()})

    def verify(self, secret: bytes) -> bool:
        """Constant-time signature check."""
        if not self.signature:
            return False
        expected = hmac.new(secret, self.payload().encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


#: A policy rule. Receives the call and returns a decision or None to abstain.
#: Raises are treated as deny, never as abstain.
PolicyRule = Callable[[ToolCall], "GuardianDecision | None"]

#: Default secret source environment variable. A per-deployment key in an env
#: var rather than a constant, because a guard signing with a key that lives in
#: the source tree is not authenticating anything.
GOVERNANCE_SECRET_ENV = "AIOS_GOVERNANCE_SECRET"


def _is_tighter(candidate: Any, existing: Any) -> bool:
    """Whether ``candidate`` is a tighter bound than ``existing``.

    A reduction is a lower bound, so tighter means smaller. Non-numeric
    overrides (an order type forced to LIMIT, say) are kept as given: a
    governance rewrite is not a negotiation, and a rule that cannot state a
    numeric bound should not be silently overridden by another that also cannot.
    """
    try:
        return float(candidate) < float(existing)
    except (TypeError, ValueError):
        return True


class ToolGuardian(ToolGuard):
    """Deterministic-first governance over proposed tool calls.

    Ordering is the design. The deterministic policy layer runs first and its
    verdict is final: an optional agent evaluator sees only the intermediate
    result, never the policy source, and must clear the deterministic layer on
    the way back. A model cannot unlock what code refused.

    The chain hash is a rolling SHA-256 over ``(previous_chain_hash, decision)``.
    It makes the decision log tamper-evident against *editing* — removing,
    reordering, or modifying any decision breaks every subsequent link. It does
    not detect *truncation*, because a shortened chain recomputes perfectly;
    see :mod:`core.decision_sink` for the seal that closes that gap.

    When a ``sink`` is supplied every decision is also written through to
    durable storage, and :meth:`resume` adopts an existing log's head so a
    restarted guardian continues the same chain rather than opening a second,
    incompatible one.
    """

    #: Refuse when no decision can be obtained. The reference implementation
    #: defaults to permit here, which means a broken guard silently stops
    #: governing. This constant exists so the choice is explicit and greppable.
    FAIL_CLOSED = True

    def __init__(
        self,
        secret: bytes,
        *,
        agent_evaluator: Callable[[ToolCall, GuardianDecision], GuardianDecision | None]
        | None = None,
        model_id: str = "",
        sink: DecisionSink | None = None,
    ) -> None:
        if not secret:
            raise ValueError("a signing secret is required; an unsigned guard is not a control")
        self._secret = secret
        self._rules: list[PolicyRule] = []
        self._agent_evaluator = agent_evaluator
        self._model_id = model_id
        self._chain_hash = ""
        self._log: list[GuardianDecision] = []
        self._sequence = 0
        self._sink = sink

    @classmethod
    def resume(
        cls,
        secret: bytes,
        sink: DecisionSink,
        **kwargs: Any,
    ) -> ToolGuardian:
        """Rebuild a guardian that continues an existing durable log.

        The alternative — constructing a fresh guardian against the same store —
        would start a second chain at genesis on top of the first, producing a
        log in which two unrelated histories are interleaved and neither
        verifies. Adopting the stored head is the only construction that keeps
        the chain a chain.
        """
        guardian = cls(secret, sink=sink, **kwargs)
        guardian._chain_hash = sink.head()
        guardian._sequence = len(sink.read_all())
        return guardian

    # ------------------------------------------------------------ policy layer

    def register_rule(self, rule: PolicyRule) -> None:
        """Add a deterministic rule. Rules run in registration order."""
        self._rules.append(rule)

    def register_clamp_rule(
        self,
        argument: str,
        maximum: float,
        *,
        reason_code: str,
        policy_id: str = "risk.capital",
        rule_id: str = "clamp_notional",
        when: Callable[[ToolCall], bool] | None = None,
    ) -> None:
        """Register the rule that makes ``modify`` useful: clamp an argument.

        This is the deterministic reduction a risk engine performs at the tool
        boundary. It fires instead of denying, so an over-sized order becomes a
        smaller one rather than a lost trade — and the reduction is recorded
        with the rule that produced it.

        ``when`` scopes the clamp to matching calls (policy bundles use this
        so a notional ceiling for broker orders does not clamp an unrelated
        tool that happens to take a ``quantity``). Unscoped by default, which
        preserves the existing behaviour of every current caller.
        """

        def rule(call: ToolCall) -> GuardianDecision | None:
            if when is not None and not when(call):
                return None
            wrapped = call.arguments.get(argument)
            if wrapped is None:
                return None
            try:
                current = float(wrapped["value"])
            except (TypeError, ValueError):
                return None
            if current <= maximum:
                return None
            return GuardianDecision(
                disposition=Disposition.MODIFY,
                reasoning=(
                    f"{argument}={current:g} exceeds the {argument} maximum of {maximum:g}; "
                    "clamped rather than denied."
                ),
                reason_codes=[reason_code],
                parameter_overrides={
                    argument: ParameterOverride(
                        value=maximum,
                        reason=f"clamped to {argument} maximum",
                        original=current,
                    )
                },
                policy_references=[
                    PolicyReference(
                        policy_id=policy_id, rule_id=rule_id, policy_name=argument
                    )
                ],
            )

        self.register_rule(rule)

    def register_deny_rule(
        self,
        reason_code: str,
        predicate: Callable[[ToolCall], bool],
        *,
        policy_id: str = "policy.deny",
        rule_id: str = "",
    ) -> None:
        """Register a rule that denies outright when a predicate holds.

        The default ``rule_id`` is the reason code rather than the literal
        ``"deny"``, because the rule id ends up in the audit record's reasoning
        and ``"denied by deny"`` names nothing. An operator reading the durable
        log months later needs the entry to identify its own cause without a
        lookup, and the reason code is the string the caller already chose to be
        specific about what went wrong. Enforced by
        ``test_denials_survive_a_restart``.
        """
        effective_rule_id = rule_id or reason_code

        def rule(call: ToolCall) -> GuardianDecision | None:
            if not predicate(call):
                return None
            return GuardianDecision(
                disposition=Disposition.DENY,
                reasoning=f"denied by {effective_rule_id} ({reason_code})",
                reason_codes=[reason_code],
                policy_references=[
                    PolicyReference(policy_id=policy_id, rule_id=effective_rule_id)
                ],
            )

        self.register_rule(rule)

    # -------------------------------------------------------------- decisions

    def _next_chain_hash(self, decision: GuardianDecision) -> str:
        """Roll the audit head. Any edit to any decision breaks the next link."""
        self._sequence += 1
        blob = "|".join(
            [
                self._chain_hash,
                decision.disposition,
                decision.call_digest,
                decision.reasoning,
                str(self._sequence),
            ]
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def _deterministic_pass(self, call: ToolCall) -> GuardianDecision | None:
        """Run every rule and combine the outcomes.

        Combines rather than returning the first objection, because a capital
        firewall with a notional ceiling AND a quantity ceiling must apply both.
        Stopping at the first match means a notional clamp silently disables the
        quantity clamp below it, and the system believes it is guarded by two
        limits when it is guarded by one.

        Precedence on combination: any DENY wins, then ASK, then DEFER, then
        MODIFY. Multiple MODIFYs merge their overrides, and where two rules clamp
        the same argument the tighter bound wins -- a firewall that lets a later
        rule loosen an earlier one is not a firewall.
        """
        escalate: GuardianDecision | None = None
        escalation_rank = -1
        overrides: dict[str, ParameterOverride] = {}
        reason_codes: list[str] = []
        references: list[PolicyReference] = []
        applied = 0

        for rule in self._rules:
            try:
                outcome = rule(call)
            except Exception as exc:  # noqa: BLE001 - a broken rule must not pass
                return GuardianDecision(
                    disposition=Disposition.DENY,
                    reasoning=f"policy rule raised: {exc}",
                    reason_codes=["policy_rule_error"],
                )
            if outcome is None:
                continue
            applied += 1
            reason_codes.extend(outcome.reason_codes)
            references.extend(outcome.policy_references)

            if outcome.disposition is Disposition.DENY:
                return outcome
            if outcome.disposition in {Disposition.ASK, Disposition.DEFER}:
                rank = 1 if outcome.disposition is Disposition.ASK else 0
                if rank >= escalation_rank:
                    escalation_rank = rank
                    escalate = outcome
                continue
            if outcome.disposition is not Disposition.MODIFY:
                continue
            for name, override in outcome.parameter_overrides.items():
                existing = overrides.get(name)
                if existing is None or _is_tighter(override.value, existing.value):
                    overrides[name] = override

        if escalate is not None:
            return escalate
        if not overrides:
            return None
        return GuardianDecision(
            disposition=Disposition.MODIFY,
            reasoning=(
                f"{len(overrides)} argument(s) reduced by {applied} policy rule(s): "
                + ", ".join(f"{name}->{ov.value!r}" for name, ov in sorted(overrides.items()))
            ),
            reason_codes=reason_codes,
            parameter_overrides=overrides,
            policy_references=references,
        )

    def evaluate(self, call: ToolCall) -> GuardianDecision:
        """Decide one tool call, deterministically first.

        Returns a decision rather than raising so a caller can log and report
        the reasoning. Use :meth:`apply` to resolve it into a callable value.
        """
        deterministic = self._deterministic_pass(call)
        evaluator = EvaluatorKind.DETERMINISTIC

        if deterministic is not None and deterministic.disposition is Disposition.DENY:
            # The deterministic layer is final on denial. An agent evaluator
            # is not consulted: a model cannot unlock what code refused.
            return self._record(call, deterministic, EvaluatorKind.DETERMINISTIC)

        if self._agent_evaluator is not None:
            baseline = deterministic if deterministic is not None else _allow_sentinel(call)
            try:
                override = self._agent_evaluator(call, baseline)
            except Exception as exc:  # noqa: BLE001 - fail closed
                return self._record(
                    call,
                    GuardianDecision(
                        disposition=Disposition.DENY,
                        reasoning=f"agent evaluator raised: {exc}",
                        reason_codes=["evaluator_error"],
                        evaluator=EvaluatorKind.AGENT,
                        model_id=self._model_id,
                    ),
                    EvaluatorKind.AGENT,
                )
            if override is not None:
                merged = _merge(deterministic, override)
                if merged.disposition is not Disposition.ALLOW:
                    return self._record(call, merged, EvaluatorKind.COMPOSITE)
                evaluator = EvaluatorKind.COMPOSITE

        if deterministic is not None:
            return self._record(call, deterministic, evaluator)
        return self._record(
            call,
            GuardianDecision(
                disposition=Disposition.ALLOW,
                reasoning="no policy rule objected",
                call_digest=call.digest(),
            ),
            evaluator,
        )

    def _record(
        self,
        call: ToolCall,
        decision: GuardianDecision,
        evaluator: EvaluatorKind,
    ) -> GuardianDecision:
        """Stamp digest, chain hash, and evaluator, then append to the log.

        Durable write happens *before* the in-memory head advances. The reverse
        order would let a process crash between the two, leaving the sink one
        decision behind the chain — a log whose head no longer corresponds to
        what the guard believes it authorised. The decision is stamped and
        written; only then does the in-memory state move.
        """
        stamped = decision.model_copy(
            update={
                "call_digest": call.digest(),
                "evaluator": evaluator,
                "model_id": decision.model_id or (self._model_id or None),
                "decided_at": datetime.now(UTC).isoformat(),
                "chain_hash": "",
            }
        )
        prior_head = self._chain_hash
        chain = self._next_chain_hash(stamped)
        final = stamped.model_copy(update={"chain_hash": chain})
        if self._sink is not None:
            self._sink.append(final, previous_chain_hash=prior_head)
        self._chain_hash = chain
        self._log.append(final)
        return final

    def apply(self, decision: GuardianDecision, call: ToolCall) -> ToolCall:
        """Resolve an already-made decision into the call to execute.

        Split from :meth:`authorize` so a caller that needs both the decision
        (for the audit trail) and the governed call (for the venue) evaluates
        once. Deciding twice would append two entries to the chain for one
        order, and the log would overstate how many judgements were made.
        """
        if not decision.applies_to(call):
            raise ToolGovernanceError(
                f"decision {decision.call_digest[:12] or '(unbound)'} was made about a "
                f"different call than {call.digest()[:12]}. A decision is bound to the call "
                "it was made about and cannot be replayed against another."
            )
        if decision.disposition is Disposition.DENY:
            raise ToolGovernanceError(
                f"tool {call.tool}.{call.operation} denied "
                f"[{','.join(decision.reason_codes) or 'unspecified'}]: {decision.reasoning}"
            )
        if decision.disposition in {Disposition.ASK, Disposition.DEFER}:
            raise ToolGovernanceError(
                f"tool {call.tool}.{call.operation} requires "
                f"{decision.disposition.lower()} and may not proceed automatically: "
                f"{decision.reasoning}"
            )
        if decision.disposition is Disposition.MODIFY:
            return call.with_overrides(
                {name: override.value for name, override in decision.parameter_overrides.items()}
            )
        return call

    def authorize(self, call: ToolCall) -> ToolCall:
        """Decide and resolve in one step: the call to execute, or raise on deny."""
        return self.apply(self.evaluate(call), call)

    # ------------------------------------------------------------------ audit

    @property
    def chain_hash(self) -> str:
        """Current audit head."""
        return self._chain_hash

    def log(self) -> list[GuardianDecision]:
        """Every decision in order, as a copy. Never truncated: this is the trail.

        A copy, so a caller cannot remove a decision by mutating the result.
        Tampering is still detectable via :meth:`verify_chain`, which accepts a
        list to check.
        """
        return list(self._log)

    @property
    def sink(self) -> DecisionSink | None:
        """The durable sink, if one is attached."""
        return self._sink

    def durable_log(self) -> list[GuardianDecision]:
        """Every decision, read back from durable storage.

        Distinct from :meth:`log` on purpose. This is the answer to "what did
        this system decide", obtained from a store that does not depend on the
        process still running — the only version of the question that survives
        a restart.
        """
        if self._sink is None:
            return []
        decisions: list[GuardianDecision] = self._sink.read_all()
        return decisions

    def verify_chain(self, decisions: list[GuardianDecision] | None = None) -> bool:
        """Recompute the chain and confirm every link still holds.

        Args:
            decisions: Log to verify. Defaults to the in-memory log.

        A chain that verifies proves no decision was *edited*, reordered, or
        removed from the middle. It cannot prove a decision was correct — a
        guard that consistently decides wrongly produces a perfectly valid
        chain — and it cannot detect *truncation*, since a shortened chain
        recomputes perfectly. For either of those, use
        :meth:`core.decision_sink.DecisionLedger.audit` against a seal.

        The head check is skipped when an explicit list is supplied. Requiring
        the recomputed head to equal ``self._chain_hash`` only makes sense when
        verifying this guardian's own log; against a log read back from storage
        the comparison is against a head the current process never computed, so
        it would report every durable log as broken. That was the previous
        behaviour, and it made the read side unusable.
        """
        entries = list(decisions if decisions is not None else self._log)
        previous = ""
        for index, decision in enumerate(entries):
            blob = "|".join(
                [
                    previous,
                    decision.disposition,
                    decision.call_digest,
                    decision.reasoning,
                    str(index + 1),
                ]
            )
            expected = hashlib.sha256(blob.encode()).hexdigest()
            if expected != decision.chain_hash:
                return False
            previous = decision.chain_hash
        if decisions is not None:
            return True
        return previous == self._chain_hash

    # ---------------------------------------------------------------- signing

    def seal(self, envelope: SignedEnvelope) -> SignedEnvelope:
        """Sign an envelope, chaining it to the current audit head."""
        return envelope.model_copy(
            update={"previous_chain_hash": self._chain_hash}
        ).sign(self._secret)

    def unseal(self, envelope: SignedEnvelope) -> ToolCall:
        """Verify an envelope's signature, then decide it.

        Refuses an unsigned or badly signed envelope before evaluating it: an
        unauthenticated decision request is not a governance question, it is
        a request to be trusted.
        """
        if not envelope.signature:
            raise UnsignedEnvelope(
                "envelope carries no signature. The spec requires HMAC-SHA256 and an "
                "unsigned decision request cannot be evaluated safely."
            )
        if not envelope.verify(self._secret):
            raise UnsignedEnvelope("envelope signature does not verify")
        if envelope.previous_chain_hash != self._chain_hash:
            raise UnsignedEnvelope(
                f"envelope chains to {envelope.previous_chain_hash[:12] or '(empty)'}, "
                f"but the audit head is {self._chain_hash[:12] or '(empty)'}"
            )
        return self.authorize(envelope.call)


def _allow_sentinel(call: ToolCall) -> GuardianDecision:
    """A neutral decision to hand an agent evaluator when rules did not object."""
    return GuardianDecision(
        disposition=Disposition.ALLOW,
        reasoning="deterministic layer raised no objection",
        call_digest=call.digest(),
    )


def _merge(
    deterministic: GuardianDecision | None,
    agent: GuardianDecision,
) -> GuardianDecision:
    """Combine the two layers under a single rule: deny wins, then ask, then defer.

    The agent may narrow an allow into a modify or a deny. It may never widen a
    modify into an allow, because an unapplied clamp is the failure this whole
    plane exists to prevent.
    """
    if deterministic is None:
        return agent
    precedence = {
        Disposition.ALLOW: 0,
        Disposition.MODIFY: 1,
        Disposition.DEFER: 2,
        Disposition.ASK: 3,
        Disposition.DENY: 4,
    }
    if precedence[deterministic.disposition] >= precedence[agent.disposition]:
        return deterministic
    return agent


def build_execution_guardian(
    secret: bytes,
    *,
    max_notional: float | None = None,
    max_quantity: float | None = None,
    sink: DecisionSink | None = None,
) -> ToolGuardian:
    """The guardian an execution adapter is bound to by default.

    Registers the two reductions a capital firewall needs at the tool boundary:
    a notional ceiling and a quantity ceiling. Both are clamps rather than
    denials, so an over-sized proposal becomes a smaller one instead of a lost
    trade, and the reduction is recorded with the rule that produced it.

    A denial is reserved for the cases where no smaller version of the order is
    acceptable. That distinction matters: a firewall that denies everything
    over the line trains operators to route around it.

    ``sink`` is a parameter rather than something the caller wires afterwards
    because the default is an in-memory log, and a production deployment that
    forgets to attach durable storage is exactly the deployment whose decisions
    are unrecoverable. Making it explicit here keeps the omission visible at the
    composition root instead of buried in a wiring detail.
    """
    guardian = ToolGuardian(secret, sink=sink)
    if max_notional is not None:
        guardian.register_clamp_rule(
            "notional",
            maximum=max_notional,
            reason_code="notional_cap_exceeded",
            policy_id="risk.capital",
            rule_id="clamp_notional",
        )
    if max_quantity is not None:
        guardian.register_clamp_rule(
            "quantity",
            maximum=max_quantity,
            reason_code="quantity_cap_exceeded",
            policy_id="risk.capital",
            rule_id="clamp_quantity",
        )
    return guardian


def guardian_secret_from_env(env: dict[str, str] | None = None) -> bytes:
    """Read the signing secret from the environment, or explain what is missing.

    Raising rather than substituting a default: a guard signing with a hardcoded
    key is a guard whose signatures prove only that whoever holds the source can
    forge decisions.
    """
    source = env if env is not None else os.environ
    secret = source.get(GOVERNANCE_SECRET_ENV, "")
    if not secret:
        raise GovernanceError(
            f"{GOVERNANCE_SECRET_ENV} is not set. The execution guard signs every "
            "envelope; a default or hardcoded key would make the signature prove nothing. "
            "Set the variable to a per-deployment secret, or construct the guard "
            "explicitly in a test with a throwaway key."
        )
    return secret.encode()
