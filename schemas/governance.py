"""Governance contracts: what a guard is, not how it decides.

This module holds the *interface* between an execution path and whatever
governs it, and it lives in ``schemas/`` because ``communities/`` may import
schema contracts but must never import ``kernel/`` directly. That boundary is
enforced by ``tests/test_architecture_boundaries.py``, and it is the reason the
contract is separated from the implementation in
:mod:`kernel.tool_governance`.

Splitting them is not ceremony. If the adapter imported ``ToolGuardian``
concretely, then either the guard becomes unreachable to communities (and the
governance plane is not enforced) or the boundary is broken (and the plane
manifest is a suggestion). With the protocol here, an adapter depends on the
contract, a composition root injects the implementation, and both rules hold at
once.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "DecisionSink",
    "Disposition",
    "EvaluatorKind",
    "GuardianDecision",
    "ParameterOverride",
    "PolicyReference",
    "ProvenanceTaggedArguments",
    "ToolCall",
    "ToolGovernanceError",
    "ToolGuard",
]


class Disposition(StrEnum):
    """What a guard decided about a proposed tool call."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    MODIFY = "MODIFY"
    ASK = "ASK"
    DEFER = "DEFER"


class EvaluatorKind(StrEnum):
    """Who produced the decision.

    ``COMPOSITE`` means a deterministic layer ran and an agent layer also
    voted. The agent's vote is recorded but cannot clear the deterministic one.
    """

    DETERMINISTIC = "DETERMINISTIC"
    AGENT = "AGENT"
    COMPOSITE = "COMPOSITE"


class GovernanceError(RuntimeError):
    """A governance envelope, decision, or configuration was refused."""


class ToolGovernanceError(GovernanceError):
    """A tool call was refused, or a decision could not be applied."""


class ParameterOverride(BaseModel):
    """A value a guard substituted, with the reason it did."""

    value: Any
    reason: str = Field(..., min_length=1)
    original: Any = None


class PolicyReference(BaseModel):
    """Which policy rule produced a decision, for replay."""

    policy_id: str
    policy_name: str = ""
    rule_id: str
    policy_version: str = "v1"


#: Argument values as ``{value, provenance}`` pairs. The wrapper is part of the
#: type rather than a convention so a bare value cannot be constructed.
ProvenanceTaggedArguments = dict[str, dict[str, Any]]


class ToolCall(BaseModel):
    """A proposed tool invocation, as an agent would issue it.

    Arguments are wrapped rather than bare so provenance travels with each value
    independently. ``{quantity: {value: 5, provenance: MODEL_DERIVED}}`` and
    ``{symbol: {value: "BTC/USD", provenance: OPERATOR}}`` are distinguishable
    even though both arrive in the same envelope — which is the difference
    between per-field taint tracking and a single label for the whole call.
    """

    model_config = {"frozen": True}

    tool: str = Field(..., min_length=1)
    operation: str = Field(default="invoke", min_length=1)
    capability: str = Field(default="", description="e.g. 'broker.order.place'")
    arguments: ProvenanceTaggedArguments = Field(
        default_factory=dict,
        description="arg name -> {value: any, provenance: str}",
    )
    agent_id: str = Field(..., min_length=1)
    session_id: str = Field(default="", description="")
    intent: str = Field(default="")

    @model_validator(mode="after")
    def _require_provenance(self) -> ToolCall:
        """Every argument must declare where its value came from.

        Required rather than optional because an unlabelled argument is
        indistinguishable from one the model invented, and the whole value of
        per-argument taint tracking is lost the moment one is optional.
        """
        for name, wrapped in self.arguments.items():
            if not isinstance(wrapped, dict) or "value" not in wrapped:
                raise ValueError(
                    f"argument {name!r} must be a {{value, provenance}} pair; got {wrapped!r}"
                )
            if not str(wrapped.get("provenance", "")).strip():
                raise ValueError(
                    f"argument {name!r} is missing provenance. Every argument must declare "
                    "where its value came from, or per-argument taint is untrackable."
                )
        return self

    def value_of(self, name: str) -> Any:
        """Unwrap one argument's value."""
        wrapped = self.arguments.get(name)
        if wrapped is None:
            raise KeyError(f"no argument named {name!r}")
        return wrapped["value"]

    def provenance_of(self, name: str) -> str:
        """Provenance label for one argument."""
        wrapped = self.arguments.get(name)
        if wrapped is None:
            raise KeyError(f"no argument named {name!r}")
        return str(wrapped.get("provenance", ""))

    def with_overrides(self, overrides: dict[str, Any]) -> ToolCall:
        """Return a copy with argument values replaced by the guard.

        The provenance label is preserved: a clamped quantity is still
        model-derived, and recording it as operator-supplied would launder the
        taint the guard is there to catch.
        """
        arguments = {name: dict(wrapped) for name, wrapped in self.arguments.items()}
        for name, value in overrides.items():
            if name in arguments:
                arguments[name] = {**arguments[name], "value": value}
            else:
                arguments[name] = {"value": value, "provenance": "GUARDIAN"}
        return self.model_copy(update={"arguments": arguments})

    def canonical(self) -> str:
        """Stable JSON for hashing and signing."""
        return json.dumps(
            {
                "tool": self.tool,
                "operation": self.operation,
                "capability": self.capability,
                "agent_id": self.agent_id,
                "session_id": self.session_id,
                "arguments": self.arguments,
            },
            sort_keys=True,
            default=str,
        )

    def digest(self) -> str:
        """Content hash binding a decision to the exact call it was made about."""
        return hashlib.sha256(self.canonical().encode()).hexdigest()


class GuardianDecision(BaseModel):
    """A guard's answer, with everything needed to replay it."""

    model_config = {"frozen": True}

    disposition: Disposition
    reasoning: str = Field(..., min_length=1, description="Required for every disposition")
    reason_codes: list[str] = Field(
        default_factory=list, description="Machine-routable denial categories"
    )
    parameter_overrides: dict[str, ParameterOverride] = Field(default_factory=dict)
    policy_references: list[PolicyReference] = Field(default_factory=list)
    evaluator: EvaluatorKind = EvaluatorKind.DETERMINISTIC
    model_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    call_digest: str = Field(default="", description="Digest of the call this answers")
    chain_hash: str = Field(default="", description="Tamper-evident audit head after this decision")
    decided_at: str = Field(default="")

    @model_validator(mode="after")
    def _require_reasoning(self) -> GuardianDecision:
        """The spec requires reasoning on every non-allow disposition.

        Enforced for all of them including ALLOW here, because a decision with
        no stated reason cannot be reviewed, and a reviewer who cannot review a
        decision cannot notice that the guard is broken.
        """
        if not self.reasoning.strip():
            raise ValueError("every decision must carry a reasoning string")
        return self

    def applies_to(self, call: ToolCall) -> bool:
        """Whether this decision was made about this exact call.

        A decision that arrives without a matching digest is refused: replaying
        an ALLOW from a cheaper call against an expensive one is the exact
        attack the digest prevents.
        """
        if not self.call_digest:
            return False
        return self.call_digest == call.digest()


class ToolGuard(ABC):
    """The boundary an execution path depends on.

    Two methods, deliberately. ``evaluate`` produces a decision that can be
    logged, chained, and audited; ``apply`` turns an existing decision into the
    call to execute. Keeping them separate means a caller that needs both the
    decision and the governed call judges once — deciding twice would append two
    audit entries for one order and overstate how many judgements were made.
    """

    @abstractmethod
    def evaluate(self, call: ToolCall) -> GuardianDecision:
        """Judge a proposed call, appending the result to the audit chain."""

    @abstractmethod
    def apply(self, decision: GuardianDecision, call: ToolCall) -> ToolCall:
        """Resolve a decision into the call to execute, or raise on refusal.

        Must never widen a call. A reduction is a lower bound; a guard that can
        enlarge an order is not a guard.
        """


class DecisionSink(Protocol):
    """Durable storage for guarded decisions.

    Lives beside :class:`ToolGuard` rather than in ``kernel/`` or ``core/``
    because it is a contract both of them need: the guard depends on it and the
    SQLite implementation satisfies it, and neither should import the other to
    express that.

    The central guarantee is carried by the *absence* of methods. There is no
    ``update`` and no ``delete``, so no caller can reach for one, and there is
    nothing to review for whether it is used correctly. Adding either later
    would be a change to the guarantee rather than an addition to the
    interface.
    """

    def append(self, decision: GuardianDecision, previous_chain_hash: str) -> None:
        """Persist one decision, linked to the head that preceded it.

        ``previous_chain_hash`` is passed rather than looked up so the guard and
        the store can disagree: the store re-derives the current head and
        refuses a stale one. A single shared truth about "where the chain is"
        would mean one bug silently rewrites history.
        """

    def read_all(self) -> list[GuardianDecision]:
        """Every decision, in chain order."""

    def head(self) -> str:
        """Current chain hash, or ``""`` when the log is empty."""
