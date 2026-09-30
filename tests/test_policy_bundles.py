"""Policy lives in versioned, signed data — not in code (goal G050).

Rules registered in-process are code: changing a limit requires a deploy,
reviewing one requires reading every call site, and "what policy was in force
on 3 March" is unanswerable. This suite covers the bundle that fixes that,
and the properties that make a bundle trustworthy rather than merely
convenient:

*A tampered bundle registers nothing.* Half a policy looks like a whole one,
so verification precedes registration with nothing in between.

*The match language stays small.* Six operators, conjunction-only. An unknown
operator fails at compile time rather than becoming a predicate that never
fires — a silently-dropped predicate is a rule that stopped firing.

*Inapplicable is not an error.* A rule about ``quantity`` evaluated against
a call without one simply does not match. Raising would turn every unrelated
tool call into a governance error, and a firewall that errors on everything
is a firewall operators route around.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.policy_bundles import (
    MatchSpec,
    PolicyBundle,
    PolicyBundleError,
    RuleSpec,
    build_guardian_from_bundle,
    compile_bundle,
    load_bundle_file,
)
from kernel.tool_governance import ToolGuardian
from schemas.governance import Disposition, ToolCall

SECRET = b"k" * 32
OTHER_SECRET = b"x" * 32
BUNDLE_PATH = Path(__file__).resolve().parent.parent / "policies" / "capital_v1.json"


def _call(
    tool: str = "broker.submit",
    operation: str = "place",
    symbol: str = "AAPL",
    quantity: float = 10.0,
    notional: float | None = None,
) -> ToolCall:
    arguments: dict[str, dict[str, object]] = {
        "symbol": {"value": symbol, "provenance": "OPERATOR"},
        "quantity": {"value": quantity, "provenance": "MODEL_DERIVED"},
    }
    if notional is not None:
        arguments["notional"] = {"value": notional, "provenance": "MODEL_DERIVED"}
    return ToolCall(
        tool=tool,
        operation=operation,
        capability="broker.order.place",
        agent_id="agent.strategy",
        intent="policy bundle check",
        arguments=arguments,
    )


def _bundle() -> PolicyBundle:
    return PolicyBundle(
        bundle_id="test-v1",
        version="v1",
        issued_at="2024-01-15T00:00:00+00:00",
        rules=(
            RuleSpec(
                kind="clamp",
                reason_code="quantity_cap_exceeded",
                policy_id="risk.capital",
                rule_id="clamp_quantity",
                argument="quantity",
                maximum=100.0,
                matches=(
                    MatchSpec(field="tool", op="eq", value="broker.submit"),
                ),
            ),
            RuleSpec(
                kind="deny",
                reason_code="SANCTIONS",
                policy_id="policy.sanctions",
                rule_id="deny_sanctioned_symbol",
                matches=(MatchSpec(field="symbol", op="in", value=["BANNED"]),),
            ),
        ),
    ).sign(SECRET)


# ══════════════════════════════════════════════════════════════════════════
# Signing: tampered or unsigned registers nothing
# ══════════════════════════════════════════════════════════════════════════


def test_a_signed_bundle_verifies() -> None:
    assert _bundle().verify(SECRET) is True


def test_a_bundle_signed_with_another_key_does_not_verify() -> None:
    assert _bundle().verify(OTHER_SECRET) is False


def test_editing_a_rule_invalidates_the_signature() -> None:
    """Recomputed over the stored fields: the edit is what gets checked."""
    bundle = _bundle()
    edited_rules = (
        bundle.rules[0].model_copy(update={"maximum": 999999.0}),
        bundle.rules[1],
    )
    edited = bundle.model_copy(update={"rules": edited_rules})
    assert edited.verify(SECRET) is False


def test_an_unsigned_bundle_compiles_nothing() -> None:
    """Half a policy looks like a whole one, so verification precedes
    registration with nothing in between."""
    bundle = PolicyBundle(
        bundle_id="unsigned", version="v1", issued_at="t", rules=(),
    )
    guardian = ToolGuardian(SECRET)
    with pytest.raises(PolicyBundleError, match="signature verification"):
        compile_bundle(bundle, guardian, SECRET)
    assert guardian._rules == []


def test_a_tampered_bundle_compiles_nothing() -> None:
    bundle = _bundle()
    tampered = bundle.model_copy(
        update={"rules": (bundle.rules[0].model_copy(update={"maximum": 1e12}), bundle.rules[1])}
    )
    guardian = ToolGuardian(SECRET)
    with pytest.raises(PolicyBundleError, match="signature verification"):
        compile_bundle(tampered, guardian, SECRET)
    assert guardian._rules == []


def test_compiling_onto_something_other_than_a_guardian_is_refused() -> None:
    """Policy compiles to deterministic rules. Anything else is not a target,
    and accepting one would let policy land somewhere unevaluated."""
    with pytest.raises(PolicyBundleError, match="ToolGuardian"):
        compile_bundle(_bundle(), object(), SECRET)


# ══════════════════════════════════════════════════════════════════════════
# Compilation: specs become rules that cite the bundle
# ══════════════════════════════════════════════════════════════════════════


def test_a_clamp_from_a_bundle_fires_and_cites_it() -> None:
    guardian = ToolGuardian(SECRET)
    assert compile_bundle(_bundle(), guardian, SECRET) == 2
    decision = guardian.evaluate(_call(quantity=500.0))
    assert decision.disposition is Disposition.MODIFY
    assert decision.reason_codes == ["quantity_cap_exceeded"]
    assert decision.parameter_overrides["quantity"].value == 100.0
    refs = decision.policy_references
    assert len(refs) == 1
    assert refs[0].policy_id == "risk.capital"
    assert refs[0].rule_id == "clamp_quantity"


def test_a_scoped_clamp_does_not_fire_off_scope() -> None:
    """The bundle's clamp is scoped to broker.submit: an unrelated tool with
    a ``quantity`` argument must not be clamped by it. An unscoped clamp
    would make every new tool quietly subject to broker limits."""
    guardian = ToolGuardian(SECRET)
    compile_bundle(_bundle(), guardian, SECRET)
    decision = guardian.evaluate(_call(tool="research.query", operation="search", quantity=999999.0))
    assert decision.disposition is Disposition.ALLOW


def test_a_deny_from_a_bundle_fires_with_its_reason() -> None:
    guardian = ToolGuardian(SECRET)
    compile_bundle(_bundle(), guardian, SECRET)
    decision = guardian.evaluate(_call(symbol="BANNED"))
    assert decision.disposition is Disposition.DENY
    assert "SANCTIONS" in decision.reasoning


def test_a_non_matching_call_passes_cleanly() -> None:
    guardian = ToolGuardian(SECRET)
    compile_bundle(_bundle(), guardian, SECRET)
    decision = guardian.evaluate(_call(symbol="AAPL", quantity=10.0))
    assert decision.disposition is Disposition.ALLOW


# ══════════════════════════════════════════════════════════════════════════
# The match language: small, total, inapplicable-is-not-error
# ══════════════════════════════════════════════════════════════════════════


def test_an_unknown_operator_fails_at_compile_time() -> None:
    """A predicate the compiler does not understand must fail here, not
    become a rule that never fires."""
    with pytest.raises(ValueError, match="unknown match operator"):
        MatchSpec(field="quantity", op="approx", value=10.0)


def test_a_clamp_without_a_ceiling_is_refused() -> None:
    """A clamp that fires and does nothing is worse than no rule: it logs a
    reduction that never happened."""
    with pytest.raises(ValueError, match="needs argument and maximum"):
        RuleSpec(kind="clamp", reason_code="EMPTY")


def test_a_deny_with_sizing_fields_is_refused() -> None:
    """Fields that do nothing are where misconfigurations hide."""
    with pytest.raises(ValueError, match="takes no argument"):
        RuleSpec(kind="deny", reason_code="X", argument="quantity", maximum=1.0)


def test_a_missing_field_does_not_match_and_does_not_raise() -> None:
    """A rule about ``quantity`` against a call without one is inapplicable.
    Raising would turn every unrelated tool call into a governance error."""
    spec = MatchSpec(field="quantity", op="gt", value=10.0)
    assert spec.matches({"symbol": {"value": "AAPL", "provenance": "OPERATOR"}}) is False


def test_an_uncoercible_value_does_not_match() -> None:
    """'Cannot compare' is not 'compares true'. A non-numeric quantity must
    not satisfy a numeric bound by accident."""
    spec = MatchSpec(field="quantity", op="gt", value=10.0)
    assert spec.matches({"quantity": {"value": "many", "provenance": "MODEL_DERIVED"}}) is False


def test_comparison_boundaries_are_exact() -> None:
    """Equality satisfies gte/lte and fails gt/lt. A boundary off by an
    epsilon is a limit that triggers one unit early or late, forever."""
    args = {"quantity": {"value": 100.0, "provenance": "X"}}
    assert MatchSpec(field="quantity", op="gte", value=100.0).matches(args) is True
    assert MatchSpec(field="quantity", op="lte", value=100.0).matches(args) is True
    assert MatchSpec(field="quantity", op="gt", value=100.0).matches(args) is False
    assert MatchSpec(field="quantity", op="lt", value=100.0).matches(args) is False
    assert MatchSpec(field="quantity", op="eq", value=100.0).matches(args) is True
    assert MatchSpec(field="quantity", op="ne", value=100.0).matches(args) is False


def test_conjunction_requires_every_match() -> None:
    spec = RuleSpec(
        kind="deny",
        reason_code="X",
        matches=(
            MatchSpec(field="tool", op="eq", value="broker.submit"),
            MatchSpec(field="symbol", op="eq", value="BANNED"),
        ),
    )
    holds = spec.predicate()
    assert holds(_call(tool="broker.submit", symbol="BANNED")) is True
    assert holds(_call(tool="research.query", operation="search", symbol="BANNED")) is False
    assert holds(_call(tool="broker.submit", symbol="AAPL")) is False


# ══════════════════════════════════════════════════════════════════════════
# Files: the shipped example bundle loads, signs, and governs
# ══════════════════════════════════════════════════════════════════════════


def test_the_shipped_bundle_is_well_formed() -> None:
    """The example file must parse even unsigned — parsing answers
    'well-formed', verification answers 'authorised', and the test below
    covers the second."""
    bundle = load_bundle_file(BUNDLE_PATH)
    assert bundle.bundle_id == "capital-example-v1"
    assert len(bundle.rules) == 3
    assert bundle.verify(SECRET) is False


def test_the_shipped_bundle_governs_once_signed() -> None:
    """Sign-then-compile is the deployment flow: the file ships unsigned
    (no secret is committed), the deployer signs, the guardian verifies."""
    bundle = load_bundle_file(BUNDLE_PATH).sign(SECRET)
    guardian = ToolGuardian(SECRET)
    assert compile_bundle(bundle, guardian, SECRET) == 3
    clamped = guardian.evaluate(_call(notional=500.0, quantity=5.0))
    assert clamped.disposition is Disposition.MODIFY
    assert clamped.parameter_overrides["notional"].value == 100.0
    denied = guardian.evaluate(_call(symbol="BANNED"))
    assert denied.disposition is Disposition.DENY


def test_a_missing_bundle_file_is_refused_with_its_path(tmp_path) -> None:
    with pytest.raises(PolicyBundleError, match="not found"):
        load_bundle_file(tmp_path / "absent.json")


def test_a_malformed_bundle_file_names_its_problem(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"bundle_id": 42}', encoding="utf-8")
    with pytest.raises(PolicyBundleError, match="malformed"):
        load_bundle_file(path)


def test_build_guardian_from_bundle_is_the_composition_path() -> None:
    """One function where bundle meets engine, so hand-registration is never
    the easier path at a composition root."""
    guardian = build_guardian_from_bundle(SECRET, _bundle())
    assert len(guardian._rules) == 2
    assert guardian.evaluate(_call(symbol="BANNED")).disposition is Disposition.DENY
