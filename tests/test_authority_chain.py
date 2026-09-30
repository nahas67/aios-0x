"""The authority chain is executable, not aspirational.

Every other test in this suite checks that a component behaves correctly. This
one checks that the *order* of authority cannot be rearranged by accident. The
vNext architecture rests on a single claim: no model, prompt, or agent can
reach capital without passing through deterministic checks that a human
ratified.

That claim is only worth something if a test fails when it stops being true.
These tests fail when it does.

The invariants are stated as static source analysis wherever possible. Static
analysis is the right instrument because the failure mode being prevented is an
import or a comparison appearing in a diff, and a behavioural test will not
notice a new import until traffic is routed through it.

Gates for capabilities that do not exist yet do not skip. They assert the
inverse: that the goal registry honestly reports the capability as unimplemented.
A test suite that skips its own unbuilt work is a suite that reports green
while the invariant is unenforced, so the honest assertion is written instead.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "goals" / "goals.json"

#: Modules that make up the deterministic financial core. Nothing here may
#: acquire a dependency that can make a financial decision non-deterministic
#: (docs/DEPENDENCY_POLICY.md, zone rule).
DETERMINISTIC_CORE = (
    "core/financial_kernel.py",
    "core/financial_invariants.py",
    "core/ibor.py",
    "core/risk_firewall.py",
    "core/risk_governor.py",
    "core/safety_plane.py",
    "core/constitution.py",
    # Selection is arithmetic over bounds on point-in-time features, and it
    # decides whether capital moves. A model reaching this module would make
    # every certified playbook unfalsifiable, because the object that chose
    # among certified policies would no longer be reproducible.
    "kernel/playbook.py",
    # The capital firewall and the envelope are the pre-trade boundary: fifteen
    # named checks plus a sealed authorization the execution path cannot mint.
    # A model dependency here would make the boundary's answers unreproducible.
    "core/capital_firewall.py",
    "core/authorization.py",
    "communities/c5_execution/oms.py",
    "communities/c5_execution/reconciliation.py",
    "communities/c11_finance/ledger.py",
)

#: The deterministic core must never reach an LLM. These are the modules that
#: represent "the model was asked".
LLM_GATEWAYS = (
    "core.model_gateway",
    "core.model_router",
    "core.prompts",
    "core.agents",
    "kernel.prompts",
)

#: Modules permitted to place, route, or cancel an order. Every one of them is
#: a place an authority-chain check has to cover.
ORDER_SINKS = (
    "communities/c5_execution/adapters.py",
    "communities/c5_execution/oms.py",
    "simulation/paper_engine.py",
)

#: Patterns that indicate a venue call rather than bookkeeping.
_VENUE_CALL = re.compile(r"\b(create_order|place_order|submit_order|send_order|create_market_order)\b")

#: The decision the fast tier is permitted to express. Note what is absent: a
#: size. Enforced structurally below.
_ALLOWED_RECOMMENDATIONS = {"TRADE", "WAIT", "ESCALATE", "ABSTAIN"}


def _source(rel: str) -> str:
    path = ROOT / rel
    assert path.exists(), f"missing module: {rel}"
    return path.read_text(encoding="utf-8")


def _imports(rel: str) -> set[str]:
    """Absolute module names imported by a file, including function-local ones."""
    try:
        tree = ast.parse(_source(rel), filename=rel)
    except SyntaxError:  # pragma: no cover - ruff owns syntax errors
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _goal(goal_id: str) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for goal in registry["goals"]:
        if goal["id"] == goal_id:
            return goal
    raise AssertionError(f"goal {goal_id} is not in {REGISTRY_PATH}")


def _unbuilt(goal_id: str, capability: str) -> None:
    """Assert an unbuilt capability is recorded as such, then return.

    Called in place of a skip. The difference matters: a skipped test is
    invisible in a coverage report, whereas this assertion fails the moment
    somebody marks the goal LANDED without writing the code.
    """
    goal = _goal(goal_id)
    assert goal["status"] in {"NOT_STARTED", "PARTIAL"}, (
        f"{goal_id} is recorded as {goal['status']} but {capability} does not exist in "
        "project source. Implement the capability, or correct the registry."
    )


# ══════════════════════════════════════════════════════════════════════════
# I2 — the risk path contains no LLM
#
# A deterministic risk engine that can consult a model is not a deterministic
# risk engine. The firewall is the last thing between a proposal and capital,
# and its verdict must be a function of its inputs alone.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel", DETERMINISTIC_CORE)
def test_deterministic_core_never_imports_an_llm_gateway(rel: str) -> None:
    imported = _imports(rel)
    offenders = sorted(
        name
        for name in LLM_GATEWAYS
        if any(entry == name or entry.startswith(f"{name}.") for entry in imported)
    )
    assert offenders == [], (
        f"{rel} imports LLM plumbing {offenders}. The deterministic core must reach its "
        "verdict from its inputs alone; a model in this path makes the verdict "
        "non-reproducible and un-auditable."
    )


@pytest.mark.parametrize("rel", DETERMINISTIC_CORE)
def test_deterministic_core_does_not_call_a_model_by_alias(rel: str) -> None:
    """Catches the indirect route: a model reached through a friendly name."""
    source = _source(rel)
    # ``generate`` alone is too common (generate_uuid, a receipt id, a
    # sequence number). The signal is a call that takes text or a prompt.
    pattern = re.compile(
        r"\b(?:llm|chat|gpt|claude)\w*\s*\(|"
        r"\b(?:completion|generate)\w*\s*\(\s*(?:[\"'f]|\w*(?:prompt|text|query|message|content)\w*\s*[,)=])",
        re.IGNORECASE,
    )
    hits = [
        line.strip()
        for line in source.splitlines()
        if pattern.search(line)
        and not line.lstrip().startswith("#")
        and "def " not in line
        and "logger" not in line
    ]
    assert hits == [], (
        f"{rel} contains calls that look like model invocation: {hits}. Verify each is "
        "deterministic local computation, or route it through the model plane."
    )


# ══════════════════════════════════════════════════════════════════════════
# I3 — the fast tier cannot express a size
#
# The fastest way to break a capital system is to let a component in the 20 ms
# path return a size. If the schema has no field for quantity or notional, the
# capability is absent rather than merely discouraged.
# ══════════════════════════════════════════════════════════════════════════


def test_decision_schema_cannot_express_a_size() -> None:
    contracts = _source("schemas/contracts.py")
    match = re.search(r"class\s+TradeDecision\b.*?(?=\nclass\s|\Z)", contracts, re.DOTALL)
    if match is None:
        _unbuilt("G110", "a TradeDecision contract")
        return
    body = match.group(0)
    forbidden = re.findall(
        r"^\s*(quantity|notional|size|position_size_pct|amount|units|leverage|weight)\s*:",
        body,
        re.MULTILINE,
    )
    assert forbidden == [], (
        f"TradeDecision declares sizing fields {forbidden}. The decision tier proposes a "
        "playbook; the portfolio brain computes a size; the firewall authorizes it."
    )


def test_recommendation_action_space_is_closed() -> None:
    contracts = _source("schemas/contracts.py")
    match = re.search(
        r"class\s+(?:Recommendation|DecisionAction|TradeAction)\w*\b.*?(?=\nclass\s|\Z)",
        contracts,
        re.DOTALL,
    )
    if match is None:
        _unbuilt("G110", "a decision action enumeration")
        return
    members = set(re.findall(r"=\s*[\"']([A-Z_]+)[\"']", match.group(0)))
    if not members:
        _unbuilt("G110", "an enumerated decision action space")
        return
    assert members <= _ALLOWED_RECOMMENDATIONS, (
        f"decision action space {sorted(members)} exceeds {sorted(_ALLOWED_RECOMMENDATIONS)}. "
        "An unlisted action cannot be governed, so it must not be expressible."
    )


# ══════════════════════════════════════════════════════════════════════════
# I5 — execution may reduce an authorization, never increase it
#
# Checked structurally because the failure is a comparison that inverts during
# a refactor, which no behavioural test reliably catches.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel", ORDER_SINKS)
def test_order_sinks_reduce_rather_than_raise_the_cap(rel: str) -> None:
    """A notional guard must compare with '>' (refuse above the cap).

    The inverted comparison is the bug: 'notional < cap: raise' looks
    defensive in review and is exactly backwards at runtime.
    """
    source = _source(rel)
    inverted = re.findall(
        r"if\s+(\w*(?:notional|quantity|size)\w*)\s*(<=|<)\s*[^:\n]+:\s*\n\s*raise",
        source,
        re.IGNORECASE,
    )
    assert inverted == [], (
        f"{rel} compares {inverted} in the refusing direction. A cap guard must refuse when "
        "the value EXCEEDS the cap, so the comparison must be '>' or '>='."
    )


def test_every_venue_submit_demands_an_envelope() -> None:
    """No path from a tool call to a venue submit without a sealed envelope.

    Checked structurally: every ``submit`` implementation in the execution
    adapters must invoke the envelope boundary before touching a venue. A new
    adapter — or a refactor that moves venue contact above the check — fails
    here rather than opening an unenveloped path that no behavioural test
    routes through yet. The behavioural half lives in
    tests/test_envelope_wiring.py; this is the half that catches the diff.
    """
    source = _source("communities/c5_execution/adapters.py")
    tree = ast.parse(source, filename="adapters.py")
    submits = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "submit"
    ]
    assert len(submits) >= 2, (
        "expected at least the paper and CCXT submit implementations; "
        "the envelope check below must cover every one"
    )
    for node in submits:
        body = ast.dump(node)
        assert "_require_envelope" in body or "envelope" in body, (
            f"submit at line {node.lineno} never touches the envelope boundary. "
            "Every venue submit must demand a sealed authorization."
        )


def test_venue_calls_are_unreachable_from_the_intelligence_plane() -> None:
    """Every venue call must sit in the execution plane, never the AI plane.

    An LLM is permitted to propose. It is not permitted to call a venue. This
    is the check that would have caught AutoHedge's design at review time.
    """
    ai_plane = (
        "communities/c2_research",
        "communities/c3_verification",
        "communities/c8_evolution",
        "research",
    )
    offenders: list[str] = []
    for rel in ai_plane:
        base = ROOT / rel
        if not base.exists():
            continue
        paths = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            if _VENUE_CALL.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == [], (
        f"the intelligence/research plane calls a venue directly: {offenders}. Research "
        "produces proposals; it does not transact."
    )


# ══════════════════════════════════════════════════════════════════════════
# I9 — fail-closed is the default
#
# A control that permits on failure is not a control. This is the defect the
# agent-control-standard reference implementation ships with, so it is checked
# structurally rather than assumed.
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel", DETERMINISTIC_CORE)
def test_deterministic_core_has_no_permissive_exception_default(rel: str) -> None:
    source = _source(rel)
    offenders = re.findall(
        r"except\s+[\w.]+(?:\s+as\s+\w+)?\s*:\s*\n(?:\s*#.*\n)*\s*return\s+[^#\n]*"
        r"\b(?:True|ALLOW|PERMIT|PROCEED|ok|pass_through)\b",
        source,
        re.IGNORECASE,
    )
    assert offenders == [], (
        f"{rel} appears to swallow an exception into a permissive result: {offenders}"
    )


def test_safety_plane_release_requires_a_role_not_just_an_operator_id() -> None:
    """A non-empty operator_id string proves nothing.

    A lockout release must resolve a server-side role, or any caller reaching
    the function can clear a risk restriction by typing a name.
    """
    source = _source("core/safety_plane.py")
    assert "ROLE_MATRIX" in source, "safety plane must resolve authority through the RBAC matrix"
    match = re.search(r"def\s+release\w*\(.*?(?=\n    def |\Z)", source, re.DOTALL)
    assert match is not None, "safety plane must expose a release path"
    body = match.group(0)
    assert "operator_id" in body, "release must record who released it"
    assert re.search(r"role|RESET_LOCKOUT|capabilit", body, re.IGNORECASE), (
        "release must check a role or capability, not only a supplied operator id"
    )


# ══════════════════════════════════════════════════════════════════════════
# I8 — production systems never self-modify
#
# An artifact derived from a certified one must be re-certified. The cheapest
# implementation gives the child an empty evidence set, so an inherited
# sign-off is structurally impossible rather than merely discouraged.
# ══════════════════════════════════════════════════════════════════════════


def test_adaptation_cannot_inherit_a_parent_sign_off() -> None:
    """A derived artifact must start with no evidence.

    Scans both registries, because the derivation path lives wherever strategy
    versioning ended up: ``StrategyRegistry.adapt`` is the one that matters for
    certification, and ``ExperimentRegistry`` gained lineage in the same
    workstream. Checking only one file would let the other grow an inheriting
    path unnoticed.
    """
    derivation_sites = ("kernel/strategy_registry.py", "kernel/registries.py")
    found_any = False
    for rel in derivation_sites:
        if not (ROOT / rel).exists():
            continue
        source = _source(rel)
        derivations = list(
            re.finditer(
                r"def\s+(adapt\w*|derive\w*|fork\w*)\(.*?(?=\n    def |\nclass |\Z)",
                source,
                re.DOTALL,
            )
        )
        for match in derivations:
            found_any = True
            body = match.group(0)
            assert re.search(r"evidence|verdict|validation", body, re.IGNORECASE), (
                f"{rel}:{match.group(1)}() must explicitly reset or re-derive validation "
                "evidence, so a child artifact cannot inherit its parent's sign-off"
            )
    if not found_any:
        _unbuilt("G080", "a certification derivation path")


# ══════════════════════════════════════════════════════════════════════════
# I6 / I10 — claims resolve to a source; the claim gate is a boundary
# ══════════════════════════════════════════════════════════════════════════


def test_evidence_records_carry_a_source_hash() -> None:
    path = ROOT / "core" / "claim_ledger.py"
    if not path.exists():
        _unbuilt("G040", "a claim ledger")
        return
    source = path.read_text(encoding="utf-8")
    assert re.search(r"sha256|source_hash|content_hash", source, re.IGNORECASE), (
        "the claim ledger must record a content hash for every source artifact"
    )


def test_claim_log_is_append_only() -> None:
    path = ROOT / "core" / "claim_ledger.py"
    if not path.exists():
        _unbuilt("G040", "a claim ledger")
        return
    source = path.read_text(encoding="utf-8")
    offenders = re.findall(r"UPDATE\s+claims?\b", source, re.IGNORECASE)
    assert offenders == [], f"claim log mutated in place: {offenders}"


#: Performance claims, as distinct from operational telemetry. "metrics" in the
#: Prometheus sense is a series name and needs no provenance; "accuracy: 0.99"
#: is a claim about the future and does.
_PERFORMANCE_CLAIM = re.compile(
    r"(?i)\b(accuracy|win_rate|sharpe|sortino|profit_factor|hit_rate|precision|"
    r"directional_accuracy|calibration_score)\b"
)


def _claimed_performance_surfaces() -> list[str]:
    """Read-only API modules that expose a performance-claim field to clients."""
    surfaces: list[str] = []
    for path in sorted((ROOT / "api").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if _PERFORMANCE_CLAIM.search(path.read_text(encoding="utf-8")):
            surfaces.append(path.relative_to(ROOT).as_posix())
    return surfaces


def test_performance_claims_are_validated_before_leaving_the_process() -> None:
    """A claim gate in a document is advice. A claim gate in the API is control.

    Per the vNext statistical claim gate, a reported performance figure must
    carry its definition, N, coverage, period, universe, regime coverage,
    net-of-cost and out-of-sample result, interval, drawdown, tail risk,
    experiment count, and model and dataset versions. A bare accuracy number
    reaching a client is the failure this prevents.
    """
    surfaces = _claimed_performance_surfaces()
    if not surfaces:
        _unbuilt("G190", "an API surface reporting a performance claim")
        return
    ungated = [
        rel
        for rel in surfaces
        if not re.search(
            r"claim_gate|validate_claim|require_claim|ClaimGate",
            (ROOT / rel).read_text(encoding="utf-8"),
        )
    ]
    assert ungated == [], (
        f"these modules report a performance claim to clients without a claim validator: "
        f"{ungated}"
    )


# ══════════════════════════════════════════════════════════════════════════
# Zone isolation
# ══════════════════════════════════════════════════════════════════════════


def test_no_capital_credential_is_referenced_in_the_intelligence_plane() -> None:
    """Broker credentials and ledger keys must not be reachable from research."""
    forbidden = re.compile(
        r"(PRIVATE_KEY|SECRET_KEY|LEDGER_SIGN|SIGNING_KEY|BROKER_SECRET|API_SECRET)",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for rel in ("communities/c2_research", "communities/c3_verification", "communities/c8_evolution"):
        base = ROOT / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if forbidden.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert offenders == [], f"capital credentials referenced in the intelligence plane: {offenders}"


def test_constitutional_live_route_gate_is_still_in_force() -> None:
    """CONSTITUTION.md section 1 forbids live routing.

    This exists to make the prohibition fail loudly if it is weakened in code
    without the amendment procedure, which requires an ADR and a human
    signature. An amendment deliberately removes this test and adds a new one
    asserting the amended limit.
    """
    adapters = _source("communities/c5_execution/adapters.py")
    assert "real-money routing is constitutionally disabled" in adapters, (
        "the constitutional live-routing prohibition has been removed from the CCXT adapter"
    )
    assert "MAX_ORDER_NOTIONAL_USD" in adapters, (
        "the micro-live notional cap is a ratified constitutional limit; removing it requires "
        "an ADR amending CONSTITUTION.md section 1"
    )


def test_constitution_pin_matches_the_document() -> None:
    """The constitution is enforced by hash. Verify the pin is current.

    A stale pin means every boot raises, which is the correct fail-closed
    behaviour but a confusing one; asserting it here names the real cause.
    """
    from core.constitution import _PINNED_SHA256, compute_sha256

    current = compute_sha256()
    assert current == _PINNED_SHA256, (
        f"CONSTITUTION.md sha256 is {current} but core/constitution.py pins "
        f"{_PINNED_SHA256}. Either amend via the section 4 procedure, or restore the document."
    )
