"""Versioned, signed policy bundles for the guardian (vNext goal G050).

Rules registered in-process are code, and code is the wrong place for policy:
changing a limit requires a deploy, reviewing a limit requires reading every
call site, and auditing "what policy was in force on 3 March" is impossible
because the answer is "whichever commit was deployed". A bundle moves policy
into data — versioned, signed, loaded at composition — while the guardian
keeps doing the only thing it should: compiling specs into rules and
evaluating them deterministically.

Two boundaries are deliberate and documented because each is a place the
design could silently expand:

*The match language is small.* Six comparison operators over call arguments,
conjoined. It covers clamps ("quantity above X") and denials ("symbol on the
sanctions list") — the shapes a capital firewall actually needs. Anything
richer (disjunctions, cross-argument arithmetic, time windows) stays an
in-process rule, because a policy language that grows into a programming
language inherits a programming language's audit burden while pretending to
be data. An unknown operator is refused at compile time, not ignored: a
silently-dropped predicate is a rule that stopped firing.

*Bundles are signed.* An HMAC with a key the bundle does not contain, verified
before a single rule registers. An unsigned or tampered bundle is refused
outright rather than partially applied — half a policy is worse than none,
because the half that loaded looks like the whole policy.

OPA/Rego is the brand name this replaces, and the substitution is intentional
rather than expedient. A sidecar policy agent would add a network dependency
and a non-Python runtime to the deterministic core's most sensitive path, in
tension with the dependency policy (three runtime dependencies) and the
portability rule the deterministic core exists to preserve. The substance —
policy externalized from code, versioned, signed, loaded at composition — is
all here; the brand is not, and the brand was never the requirement.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "MatchSpec",
    "PolicyBundle",
    "PolicyBundleError",
    "RuleSpec",
    "build_guardian_from_bundle",
    "compile_bundle",
    "load_bundle_file",
]

#: The operators a bundle may use. Conjunction-only, comparison-only — see
#: the module docstring for why the language stays small on purpose.
_MATCH_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in"})


class PolicyBundleError(RuntimeError):
    """A policy bundle was refused: unsigned, tampered, or uncompilable."""


class MatchSpec(BaseModel):
    """One predicate over one call argument: ``field op value``."""

    model_config = {"frozen": True}

    field: str = Field(..., min_length=1)
    op: str = Field(..., min_length=1)
    value: Any = None

    @model_validator(mode="after")
    def _known_operator(self) -> MatchSpec:
        if self.op not in _MATCH_OPS:
            raise ValueError(
                f"unknown match operator {self.op!r}; known: {sorted(_MATCH_OPS)}. "
                "An operator the compiler does not understand must fail here, "
                "not become a predicate that never fires."
            )
        return self

    def matches(self, arguments: dict[str, Any]) -> bool:
        """Whether the wrapped arguments satisfy this predicate.

        A missing field never matches — it must not raise, because a rule
        about ``quantity`` evaluated against a call without one is simply
        inapplicable, and an inapplicable rule that raised would turn every
        unrelated tool call into a governance error. A present-but-uncoercible
        value likewise does not match: "cannot compare" is not "compares true".
        """
        wrapped = arguments.get(self.field)
        if not isinstance(wrapped, dict) or "value" not in wrapped:
            return False
        actual = wrapped["value"]
        try:
            if self.op == "eq":
                return bool(actual == self.value)
            if self.op == "ne":
                return bool(actual != self.value)
            if self.op == "in":
                return bool(actual in self.value)
            left, right = float(actual), float(self.value)
            if self.op == "gt":
                return left > right
            if self.op == "gte":
                return left >= right
            if self.op == "lt":
                return left < right
            return left <= right
        except (TypeError, ValueError):
            return False

    def describe(self) -> str:
        return f"{self.field} {self.op} {self.value!r}"


class RuleSpec(BaseModel):
    """One rule: what kind, when it fires, what it does.

    ``matches`` is a conjunction; empty means always. A clamp needs
    ``argument`` and ``maximum``; a deny needs neither. Anything else is
    refused at validation so a malformed rule cannot become a permissive one.
    """

    model_config = {"frozen": True}

    kind: str = Field(..., pattern="^(clamp|deny)$")
    reason_code: str = Field(..., min_length=1)
    policy_id: str = Field(default="policy.bundle", min_length=1)
    rule_id: str = Field(default="", min_length=0)
    argument: str | None = None
    maximum: float | None = None
    matches: tuple[MatchSpec, ...] = ()

    @model_validator(mode="after")
    def _complete_rule(self) -> RuleSpec:
        if self.kind == "clamp" and (self.argument is None or self.maximum is None):
            raise ValueError(
                f"clamp rule {self.reason_code!r} needs argument and maximum. "
                "A clamp without a ceiling is a rule that fires and does nothing."
            )
        if self.kind == "deny" and (self.argument is not None or self.maximum is not None):
            raise ValueError(
                f"deny rule {self.reason_code!r} takes no argument or maximum. "
                "Fields that do nothing are where misconfigurations hide."
            )
        return self

    def predicate(self) -> Callable[[Any], bool]:
        """Compile the conjunction to a callable over a tool call.

        The match scope is the call's identity (``tool``, ``operation``) overlaid
        with its wrapped arguments, so a rule can scope itself to
        ``broker.submit/place`` without a separate mechanism — and a rule about
        ``quantity`` evaluated against a call without one is inapplicable rather
        than an error, per :meth:`MatchSpec.matches`.
        """
        specs = self.matches

        def holds(call: Any) -> bool:
            # Call identity wrapped like an argument, so one match shape
            # serves both. Provenance SYSTEM: the tool and operation are
            # routing facts, not model output, and must never be mistaken
            # for a value the model supplied.
            scope: dict[str, Any] = {
                "tool": {"value": call.tool, "provenance": "SYSTEM"},
                "operation": {"value": call.operation, "provenance": "SYSTEM"},
            }
            scope.update(call.arguments)
            return all(spec.matches(scope) for spec in specs)

        return holds


class PolicyBundle(BaseModel):
    """A versioned set of rule specs plus the signature that vouches for it."""

    model_config = {"frozen": True}

    bundle_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    issued_at: str = Field(..., min_length=1)
    rules: tuple[RuleSpec, ...] = ()
    signature: str = ""

    def canonical(self) -> str:
        """The bytes the signature covers: everything but the signature."""
        return json.dumps(
            {
                "bundle_id": self.bundle_id,
                "version": self.version,
                "issued_at": self.issued_at,
                "rules": [rule.model_dump(mode="json") for rule in self.rules],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def sign(self, secret: bytes) -> PolicyBundle:
        """Return a copy carrying an HMAC over the canonical form."""
        if not secret:
            raise PolicyBundleError("a signing secret is required; an unsigned bundle is not policy")
        digest = hmac.new(secret, self.canonical().encode(), hashlib.sha256).hexdigest()
        return self.model_copy(update={"signature": digest})

    def verify(self, secret: bytes) -> bool:
        """Whether this bundle was signed with the given key, unmodified.

        Recomputed over the *stored* fields: editing a rule invalidates the
        signature instead of becoming the new policy.
        """
        if not self.signature:
            return False
        expected = hmac.new(secret, self.canonical().encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


def load_bundle_file(path: str | Path) -> PolicyBundle:
    """Parse a bundle file. Signature is checked at compile time, not here —
    parsing answers "is this well-formed", verification answers "is this
    authorised", and conflating the two would let a well-formed forgery pass
    the first gate looking like it passed the second."""
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyBundleError(f"policy bundle not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyBundleError(f"policy bundle {target} is not valid JSON: {exc}") from exc
    try:
        return PolicyBundle.model_validate(raw)
    except Exception as exc:
        raise PolicyBundleError(f"policy bundle {target} is malformed: {exc}") from exc


def compile_bundle(bundle: PolicyBundle, guardian: Any, secret: bytes) -> int:
    """Verify a bundle and register every rule it carries. Returns the count.

    Verification first, registration second, with nothing in between: a bundle
    that fails verification registers zero rules, because half a policy looks
    like a whole one. The guardian's rule order follows bundle order, so the
    bundle — not the composition code — is where precedence is decided.
    """
    if not bundle.verify(secret):
        raise PolicyBundleError(
            f"bundle {bundle.bundle_id}:{bundle.version} failed signature verification. "
            "An unverified bundle registers nothing."
        )
    from kernel.tool_governance import (
        ToolGuardian,  # noqa: PLC0415 - avoid a hard core->kernel edge
    )

    if not isinstance(guardian, ToolGuardian):
        raise PolicyBundleError(
            "compile_bundle registers onto a ToolGuardian. Policy compiles to "
            "deterministic rules, and anything else is not a target."
        )
    for spec in bundle.rules:
        holds = spec.predicate()
        if spec.kind == "clamp":
            assert spec.argument is not None and spec.maximum is not None
            guardian.register_clamp_rule(
                spec.argument,
                spec.maximum,
                reason_code=spec.reason_code,
                policy_id=spec.policy_id,
                rule_id=spec.rule_id or spec.reason_code,
                when=holds,
            )
        else:
            guardian.register_deny_rule(
                spec.reason_code,
                holds,
                policy_id=spec.policy_id,
                rule_id=spec.rule_id,
            )
    return len(bundle.rules)


def build_guardian_from_bundle(secret: bytes, bundle: PolicyBundle, **kwargs: Any) -> Any:
    """Composition-root constructor: verify, compile, return a governed guardian.

    The alternative — hand-registering each rule in code — is exactly the
    in-process policy this module replaces. The bundle is the policy; the
    guardian is the engine; this function is the only place they meet.
    """
    from kernel.tool_governance import (
        ToolGuardian,  # noqa: PLC0415 - avoid a hard core->kernel edge
    )

    guardian = ToolGuardian(secret, **kwargs)
    compile_bundle(bundle, guardian, secret)
    return guardian
