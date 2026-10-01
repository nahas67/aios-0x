"""The goal registry is a machine-enforced object, not documentation.

``docs/goals/goals.json`` is the single source of truth for vNext goal status
(``docs/goals/README.md``). These tests make the registry's own rules
non-negotiable: no unknown statuses, no duplicate ids, no dangling
dependencies, no gate without a check scheme, and no ``LANDED`` goal whose
evidence is empty.

The last rule is the one that matters. A goal is LANDED only when code and
tests back it, so a document cannot promote a goal by assertion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "goals" / "goals.json"

VALID_STATUSES = frozenset({"LANDED", "PARTIAL", "NOT_STARTED", "BLOCKED", "SUPERSEDED"})
VALID_SCHEMES = frozenset({"test", "lint", "constitution", "manual"})

ALLOWED_GOAL_KEYS = frozenset(
    {
        "id",
        "title",
        "layer",
        "workstream",
        "status",
        "depends_on",
        "blocked_by",
        "summary",
        "gates",
        "evidence",
        "blocker",
        "notes",
        "adoption_note",
        "refusal_note",
        "status_note",
    }
)


def _registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        pytest.fail(f"goal registry missing: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _goals() -> list[dict[str, Any]]:
    goals = _registry().get("goals")
    assert isinstance(goals, list) and goals, "registry must declare a non-empty goals list"
    return goals


def _by_id() -> dict[str, dict[str, Any]]:
    return {goal["id"]: goal for goal in _goals()}


# --------------------------------------------------------------------- shape


def test_registry_declares_its_own_vocabulary() -> None:
    """The registry publishes the vocabularies the validator enforces.

    Keeping the vocabulary in the data means a reader of the JSON does not
    have to open this file to know what is legal.
    """
    registry = _registry()
    assert registry["schema_version"] == 1
    assert set(registry["statuses"]) == VALID_STATUSES
    assert set(registry["check_schemes"]) == VALID_SCHEMES


def test_every_goal_uses_a_known_status() -> None:
    unknown = [
        f"{goal['id']}={goal['status']!r}"
        for goal in _goals()
        if goal.get("status") not in VALID_STATUSES
    ]
    assert unknown == [], f"unknown goal status: {unknown}"


def test_goal_ids_are_unique_and_well_formed() -> None:
    ids = [goal["id"] for goal in _goals()]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert duplicates == [], f"duplicate goal ids: {duplicates}"
    malformed = [i for i in ids if not (isinstance(i, str) and i.startswith("G") and i[1:].isdigit())]
    assert malformed == [], f"malformed goal ids: {malformed}"


def test_goals_declare_no_unknown_keys() -> None:
    """An unrecognised key is almost always a typo that silently disables a gate."""
    unknown = [
        f"{goal['id']}: {sorted(set(goal) - ALLOWED_GOAL_KEYS)}"
        for goal in _goals()
        if set(goal) - ALLOWED_GOAL_KEYS
    ]
    assert unknown == [], f"unknown goal keys: {unknown}"


# ------------------------------------------------------------------ closure


def test_dependencies_reference_known_goals() -> None:
    known = set(_by_id())
    dangling = [
        f"{goal['id']} -> {ref}"
        for goal in _goals()
        for ref in (*goal.get("depends_on", []), *goal.get("blocked_by", []))
        if ref not in known
    ]
    assert dangling == [], f"dangling goal references: {dangling}"


def test_dependency_graph_is_acyclic() -> None:
    """A cycle would make the workstream order unschedulable.

    Implemented as a depth-first search so the assertion names the actual
    cycle rather than reporting a generic failure.
    """
    by_id = _by_id()
    state: dict[str, int] = {}  # 0 unvisited, 1 on stack, 2 done
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        stack.append(node)
        for dependency in by_id.get(node, {}).get("depends_on", []):
            if dependency not in by_id:
                continue
            if state.get(dependency) == 1:
                cycles.append([*stack[stack.index(dependency) :], dependency])
            elif state.get(dependency, 0) == 0:
                visit(dependency, stack)
        stack.pop()
        state[node] = 2

    for goal_id in sorted(by_id):
        if state.get(goal_id, 0) == 0:
            visit(goal_id, [])
    assert cycles == [], f"cyclic goal dependencies: {cycles}"


def test_every_dependency_appears_before_its_dependent_in_file_order() -> None:
    """Ordering sanity: a prerequisite should not be declared after its consumer.

    This is a readability invariant rather than a correctness one - the
    registry is meant to be read top to bottom as the build order.
    """
    order = {goal["id"]: index for index, goal in enumerate(_goals())}
    inversions = [
        f"{goal['id']} depends on later {dependency}"
        for goal in _goals()
        for dependency in goal.get("depends_on", [])
        if dependency in order and order[dependency] > order[goal["id"]]
    ]
    assert inversions == [], f"goal ordering inversions: {inversions}"


# -------------------------------------------------------------------- gates


def test_every_goal_has_at_least_one_gate() -> None:
    """A goal with no gate is a wish, not a goal."""
    empty = [goal["id"] for goal in _goals() if not goal.get("gates")]
    assert empty == [], f"goals without gates: {empty}"


def test_every_gate_declares_a_known_check_scheme() -> None:
    bad = [
        f"{goal['id']} -> {gate.get('check')!r}"
        for goal in _goals()
        for gate in goal.get("gates", [])
        if gate.get("check", "").split(":", 1)[0] not in VALID_SCHEMES
    ]
    assert bad == [], f"unknown check scheme: {bad}"


def test_test_gates_name_an_executable_path() -> None:
    """A ``test:`` gate must name a file, and the claim in the goal's evidence
    that the gate does not yet exist is recorded honestly.

    Gates for unwritten goals legitimately point at files that do not exist
    yet; what must not happen is a gate with no path at all.
    """
    bad = [
        f"{goal['id']} -> {gate.get('check')!r}"
        for goal in _goals()
        for gate in goal.get("gates", [])
        if gate.get("check", "").startswith("test:")
        and not gate["check"].split(":", 1)[1].strip().endswith(".py")
    ]
    assert bad == [], f"test gate without a .py target: {bad}"


def test_gate_statements_are_assertions() -> None:
    """Every gate states what is true when it passes.

    Without this a gate can degrade into a restatement of the goal title,
    which passes review while enforcing nothing.
    """
    weak = [
        f"{goal['id']} -> {gate.get('statement')!r}"
        for goal in _goals()
        for gate in goal.get("gates", [])
        if len(str(gate.get("statement", "")).split()) < 8
    ]
    assert weak == [], f"gate statements too short to assert: {weak}"


# ------------------------------------------------------------------- status


def test_landed_goals_carry_evidence() -> None:
    """The anti-aspiration rule: a goal cannot be LANDED on assertion alone.

    This is the single most important test in the file. A registry that
    permits LANDED-without-evidence is a wishlist wearing a schema.
    """
    hollow = [goal["id"] for goal in _goals() if goal.get("status") == "LANDED" and not goal.get("evidence")]
    assert hollow == [], f"LANDED goals with no evidence: {hollow}"


def test_landed_goals_evidence_paths_exist() -> None:
    """Evidence must point at files that are actually in the repository."""
    missing: list[str] = []
    for goal in _goals():
        if goal.get("status") != "LANDED":
            continue
        for reference in goal.get("evidence", []):
            if not (ROOT / reference).exists():
                missing.append(f"{goal['id']} -> {reference}")
    assert missing == [], f"LANDED goals cite missing evidence: {missing}"


def test_blocked_goals_state_what_blocks_them() -> None:
    """A blocked goal without a stated blocker is just a delayed one.

    ``blocker`` and ``blocked_by`` are separate on purpose: the first is prose
    a human reads, the second is a machine-checked dependency edge.
    """
    bad = [
        goal["id"]
        for goal in _goals()
        if goal.get("status") == "BLOCKED" and not (goal.get("blocker") and goal.get("blocked_by"))
    ]
    assert bad == [], f"BLOCKED goals missing blocker or blocked_by: {bad}"


def test_not_started_goals_for_missing_capabilities_say_why() -> None:
    """A NOT_STARTED goal for a capability someone believes exists should
    carry a blocker explaining the absence, so a reader does not assume the
    work was attempted and abandoned."""
    bad = [
        goal["id"]
        for goal in _goals()
        if goal.get("status") == "NOT_STARTED" and not (goal.get("blocker") or goal.get("notes"))
    ]
    assert bad == [], f"NOT_STARTED goals without explanation: {bad}"


def test_no_goal_sits_between_workstreams_unexplained() -> None:
    """Every goal maps to a workstream, and the W0..W12 sequence is closed.

    An unmapped goal means the vNext program has an item nobody scheduled.
    """
    workstreams = {goal.get("workstream") for goal in _goals()}
    assert None not in workstreams, "a goal has no workstream"
    unexpected = sorted(ws for ws in workstreams if ws and not re.match(r"^W\d+$", str(ws)))
    assert unexpected == [], f"unexpected workstream ids: {unexpected}"


# ------------------------------------------------------------------- guards


def test_registry_does_not_claim_goals_the_code_lacks() -> None:
    """Guard the most dangerous failure mode: a registry that marks a goal
    LANDED because someone said so.

    This test asserts the inverse direction for the two capability groups that
    a vNext program is most likely to overstate. It reads the source rather
    than trusting the registry, so editing the registry cannot make it pass.
    """

    def occurrences(pattern: str) -> int:
        total = 0
        for path in ROOT.rglob("*.py"):
            if any(part in {".venv-fresh", "__pycache__", ".vt-study"} for part in path.parts):
                continue
            if "tests" in path.parts or "docs" in path.parts:
                continue
            try:
                total += len(re.findall(pattern, path.read_text(encoding="utf-8"), re.IGNORECASE))
            except (UnicodeDecodeError, OSError):  # pragma: no cover
                continue
        return total

    by_id = _by_id()
    for goal_id, capability in (("G080", r"\b(purged|embargo|cpcv|deflated_sharpe)\b"), ("G120", r"\bplaybook\b")):
        goal = by_id[goal_id]
        present = occurrences(capability) > 0
        if not present:
            assert goal["status"] in {"NOT_STARTED", "PARTIAL"}, (
                f"{goal_id} claims {goal['status']} but no {capability!r} implementation "
                "exists in project source"
            )


def test_landed_goals_have_gates_that_exist() -> None:
    """A `test:` gate on a LANDED goal must name a file that exists.

    ``test_test_gates_name_an_executable_path`` already requires the path to end
    in ``.py`` and explicitly allows unwritten goals to name files that do not yet
    exist. That allowance is right for BLOCKED and NOT_STARTED work and wrong for
    a goal marked LANDED: a landed goal whose gate points at a missing file is
    claiming a proof that cannot be produced, and every reader of the registry
    reasonably assumes the gate runs.

    This is not hypothetical. Five gates across four LANDED goals pointed at
    files that never existed -- test_financial_invariants.py,
    test_reconciliation.py, test_selective_decision.py (three gates) and
    test_regime_engine.py. Four were repointed at the tests that actually own the
    property; one was deleted because the capability it described was never
    built.

    BLOCKED goals are exempt, and ``test_blocked_goals_state_what_blocks_them``
    separately requires them to explain themselves.
    """
    missing = [
        f"{goal['id']} -> {gate['check'].split(':', 1)[1].strip()}"
        for goal in _goals()
        if goal["status"] != "BLOCKED"
        for gate in goal.get("gates", [])
        if gate.get("check", "").startswith("test:")
        and not (ROOT / gate["check"].split(":", 1)[1].strip()).exists()
    ]
    assert missing == [], (
        "a non-BLOCKED goal's gate must name a test file that exists: "
        f"{missing}"
    )


#: CamelCase with at least two humps. All-caps acronyms are excluded because
#: PIT / CPCV / OOS / TLC / SBOM are vocabulary, not code identifiers.
_CAMEL_IDENTIFIER = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z0-9]*)+)\b")

#: Prose that looks like an identifier but is not a code symbol.
_NOT_IDENTIFIERS = {"Layer"}


def _source_blob() -> str:
    """Every project source file, excluding vendored, generated and prose trees.

    Frontend sources count too: a goal may legitimately name a type that lives
    only in the React app, and the question is whether the thing exists anywhere
    the system runs.

    ``tests`` and ``docs`` are excluded, and that exclusion is load-bearing
    rather than tidiness. This file's own docstrings quote the very identifiers
    it is looking for, so a blob that included them would satisfy every lookup
    with the rule's explanation of what it is checking. A vacuity check caught
    exactly that: reintroducing ``RegimeSnapshot`` into G100 passed the rule,
    because the rule was reading this paragraph. The sibling rule above already
    excluded these directories for the same reason.
    """
    skip = {".venv-fresh", "__pycache__", ".vt-study", "node_modules", "tests", "docs"}
    parts: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(p in skip for p in path.parts):
            continue
        parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    for suffix in ("*.ts", "*.tsx"):
        for path in (ROOT / "frontend" / "src").rglob(suffix):
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def test_goals_do_not_name_artifacts_the_code_lacks() -> None:
    """Every identifier a goal claims to have built must exist somewhere.

    ``test_registry_does_not_claim_goals_the_code_lacks`` already guards this
    failure mode -- "a registry that marks a goal LANDED because someone said so"
    -- but it hardcodes two goals, so only two were ever checked. G100 was marked
    LANDED with the objective "RegimeSnapshot ... plus a per-strategy domain of
    competence": the engine has always exposed ``RegimeState``, and the word
    "competence" appears nowhere in the tree. Neither was noticed.

    Deriving the identifiers from each objective instead of listing them means a
    new overclaim is caught the moment it is written, with no edit to this file.
    Across the current registry exactly one identifier is unresolved, so the rule
    produces no false positives while still failing on the one real case.

    Editing the registry to name a type that does not exist is exactly how this
    test is meant to fail. Renaming a real type breaks it too, which is correct:
    the objective should be updated in the same change.
    """
    blob = _source_blob()

    unresolved: dict[str, list[str]] = {}
    for goal in _goals():
        text = " ".join(
            str(goal.get(key, "")) for key in ("title", "summary", "objective")
        )
        names = {
            name
            for name in _CAMEL_IDENTIFIER.findall(text)
            if name not in _NOT_IDENTIFIERS
        }
        absent = sorted(name for name in names if name not in blob)
        if absent:
            unresolved[goal["id"]] = absent

    assert unresolved == {}, (
        "a goal names an artifact that exists in no source file -- either the "
        f"objective overclaims, or the type was renamed: {unresolved}"
    )
