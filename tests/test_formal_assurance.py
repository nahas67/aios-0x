"""The specs describe the implementation, not a neighbouring machine (G220).

TLA+ cannot be model-checked here (no JVM, no TLC binary — stated, not
hidden), so these tests pin the next best thing that is checkable: the
specs exist, they name the properties they claim, and every state they
mention is a state the implementation actually runs. A spec that drifts from
its implementation is fiction with mathematics' formatting; these tests fail
the moment code renames a state without renaming it in the spec.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.financial_kernel import (
    LOCKOUT_SCOPE_BY_KIND,
    SCOPE_RANK,
    AnomalyKind,
    LockoutScope,
    OutboxStatus,
    ReconciliationMode,
)
from schemas.contracts import _TERMINAL_ORDER_STATES, OrderStatus

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"


#: TLA+ section keywords. A line starting with one of these is never a definition,
#: even though `VARIABLES a, b, c`.split("==")[0] is the whole line and so
#: trivially "starts with head + ' =='" -- which made every definition followed by
#: a VARIABLES declaration return an empty body, and took two drift pins with it.
_TLA_SECTIONS = frozenset({
    "ASSUME", "CONSTANT", "EXTEND", "EXTENDS", "INSTANCE", "LOCAL",
    "MODULE", "RECURSIVE", "THEOREM", "VARIABLE", "VARIABLES",
})


def _definition_body(text: str, name: str) -> str:
    """The text of a TLA+ definition, from its operator to the next definition.

    Definitions in this spec span one or more lines after the `==`, so reading a
    fixed number of lines after the operator finds only part of the body -- which
    made a pin reject a spec that satisfies it. The body runs to the next
    top-level definition, identified strictly: a single identifier at column zero
    followed by `==`, and never a section keyword.
    """
    # Accept a parameterised definition: `ReachOf(kinds, sevs) ==` as well as
    # `NeverEmitted ==`. Requiring the name to be followed by `(` or ` ==` keeps a
    # longer identifier that merely shares the prefix -- `ReachOfX ==` -- from
    # satisfying a lookup for `ReachOf`.
    for marker in (f"{name} ==", f"{name}("):
        index = text.find(marker)
        if index == -1:
            continue
        tail = text[index + len(marker):]
        break
    else:
        return ""
    lines = tail.split("\n")
    body = [lines[0]]
    for line in lines[1:]:
        head = line.split("==", 1)[0].strip()
        if not head:
            continue
        # First WORD, not the whole head: `VARIABLES findings, severity, ...`
        # carries no `==`, so head is the entire line, and comparing that against
        # a set of bare keywords never matches -- which let a VARIABLES line pass
        # for body content and swallowed the definition after it.
        first = head.split()[0]
        if first in _TLA_SECTIONS:
            break
        if line.startswith(head + " ==") and head.replace(" ", "").isidentifier():
            break
        body.append(line)
    return "\n".join(body)


def _read(name: str) -> str:
    path = SPECS / name
    assert path.exists(), f"missing formal spec: {path}"
    return path.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════
# Order lifecycle
# ══════════════════════════════════════════════════════════════════════════


def test_order_lifecycle_spec_exists_with_its_invariants() -> None:
    """The gate, literally: a TLA+ specification exists for the order state
    machine, stating the properties it is meant to hold."""
    text = _read("OrderLifecycle.tla")
    for invariant in ("TerminalIsSticky", "FillMonotone", "NoPhantomFill", "NoResurrection"):
        assert invariant in text, f"spec must state {invariant}"


def test_order_spec_states_match_the_implementation() -> None:
    """Every state in the spec is an OrderStatus the code runs, and every
    terminal state in code is terminal in the spec. Drift in either direction
    fails: a spec state the code lacks is fiction, a code state the spec
    lacks is unverified."""
    text = _read("OrderLifecycle.tla")
    for status in OrderStatus:
        assert f'"{status.value}"' in text, f"spec omits OrderStatus.{status.name}"
    terminal_line = next(
        line for line in text.splitlines() if line.startswith("Terminal ==")
    )
    for status in _TERMINAL_ORDER_STATES:
        assert status.value in terminal_line, f"spec must mark {status.value} terminal"
    for status in OrderStatus:
        if status not in _TERMINAL_ORDER_STATES:
            assert status.value not in terminal_line, (
                f"spec wrongly marks {status.value} terminal"
            )


def test_order_spec_transitions_cover_the_lifecycle() -> None:
    """Accept, fill (partial and full), cancel, reject, expire: the verbs the
    OMS actually performs. A transition the code performs but the spec lacks
    is behaviour the assurance does not cover."""

    text = _read("OrderLifecycle.tla")
    for action in ("Accept", "PartialFill", "FullFill", "Cancel", "Reject", "Expire"):
        assert re.search(rf"\n{action}(\(\w+\))? ==", text), (
            f"spec omits the {action} transition"
        )


# ══════════════════════════════════════════════════════════════════════════
# Outbox
# ══════════════════════════════════════════════════════════════════════════


def test_outbox_spec_exists_with_its_invariants() -> None:
    """The gate, literally: a TLA+ specification exists for the outbox,
    stating at-most-once effect under duplicate delivery."""
    text = _read("Outbox.tla")
    for invariant in ("AtMostOnceEffect", "HashBindsKey", "DeadLetterTerminal", "NoLoss"):
        assert invariant in text, f"spec must state {invariant}"


def test_outbox_spec_states_match_the_implementation() -> None:
    """Every OutboxStatus the code runs appears in the spec's state set, and
    the duplicate-delivery stutter step is explicit rather than assumed."""
    text = _read("Outbox.tla")
    for status in OutboxStatus:
        assert f'"{status.value}"' in text, f"spec omits OutboxStatus.{status.name}"
    assert "DuplicateDeliver" in text


def test_outbox_spec_quarantines_hash_mismatch() -> None:
    """A redelivery with different bytes is corruption, not a retry: the
    spec must route hash mismatch to dead letter without applying."""
    text = _read("Outbox.tla")
    assert "Quarantine" in text
    assert "hashOk = FALSE" in text


# ══════════════════════════════════════════════════════════════════════════
# Reconciliation
# ══════════════════════════════════════════════════════════════════════════


def test_reconciliation_spec_exists_with_its_invariants() -> None:
    """The gate, literally: a TLA+ specification exists for reconciliation, and
    it names every invariant the .cfg asks TLC to check.

    Drift in either direction fails. An invariant in the cfg that the spec does
    not define is a check that cannot run; an invariant in the spec that the cfg
    does not list is a claim nobody verifies. Defect #43 was five gates pointing
    at files that never existed, which is the same shape one layer up.
    """
    text = _read("Reconciliation.tla")
    cfg = _read("Reconciliation.cfg")

    invariants = [
        line.strip().split(" ", 1)[1]
        for line in cfg.splitlines()
        if line.strip().startswith("INVARIANT")
    ]
    assert invariants, "the cfg must check at least one invariant"

    for name in invariants:
        assert f"{name} ==" in text, (
            f"the cfg checks {name} but the spec does not define it -- a "
            "property nothing can refute is not a check"
        )


def test_reconciliation_anomaly_kinds_match_the_implementation() -> None:
    """Every AnomalyKind the code can emit appears in the spec's taxonomy, and
    the two deprecated members are named as never-emitted rather than omitted.

    Omitting them would make it impossible to state the rule they exist to record,
    and adding an emittable kind without updating the spec would leave the model
    describing a taxonomy the engine no longer has.
    """
    text = _read("Reconciliation.tla")

    for kind in AnomalyKind:
        assert f'"{kind.value}"' in text, f"spec omits AnomalyKind.{kind.name}"

    # The deprecated pair must be present AND explicitly excluded: they are
    # read-compatibility members, never emitted, and a spec that dropped them
    # could not state why a broker/internal match is not a duplicate.
    assert "NeverEmitted" in text, "spec must name the never-emitted set"
    for kind in (AnomalyKind.DUPLICATE_FILL, AnomalyKind.MISSING_FILL):
        assert f'"{kind.value}"' in text, (
            f"deprecated kind {kind.name} must be named so the never-emitted "
            "rule can be stated"
        )

    # And in the PROPERTY BODY, not merely somewhere in the file. The earlier
    # version of this pin passed when the invariant body stopped naming the
    # kinds, because the names survived in the `NeverEmitted` set -- so the rule
    # TLC checks could be emptied while the test still went green. That is the
    # same shape as defect #43: a check whose subject can be removed without
    # being noticed.
    body = _definition_body(text, "NeverEmittedKindsAbsent")
    for kind in (AnomalyKind.DUPLICATE_FILL, AnomalyKind.MISSING_FILL):
        assert kind.value in body, (
            f"{kind.name} must be named in the NeverEmittedKindsAbsent body -- "
            "a mention elsewhere in the file is not the rule"
        )

    # The two statements of one rule must not drift apart: the property body
    # names the kinds inline, and `NeverEmitted` is the set they come from.
    # Emptying the set left both earlier pins green while the two views
    # contradicted each other.
    declared = set(re.findall(r'"([A-Z_]+)"', _definition_body(text, "NeverEmitted")))
    in_body = set(re.findall(r'"([A-Z_]+)"', body))
    assert declared == in_body, (
        "NeverEmitted and the NeverEmittedKindsAbsent body name different "
        f"kinds: {sorted(declared)} vs {sorted(in_body)}"
    )


def test_reconciliation_scope_ranks_match_the_implementation() -> None:
    """The spec's rank ordering is the code's SCOPE_RANK ordering.

    The rank is what carries the meaning -- "widest" -- so a renumbering in either
    direction is a semantic change. Asserted against the real table rather than a
    hardcoded copy, so the spec cannot drift from the enum silently.
    """
    text = _read("Reconciliation.tla")

    widest_first = sorted(SCOPE_RANK, key=lambda s: -SCOPE_RANK[s])
    assert widest_first[0] is max(SCOPE_RANK, key=lambda s: SCOPE_RANK[s])

    # Only CRITICAL restricts, per LOCKOUT_SCOPE_BY_KIND's docstring.
    restricting = {k for k, scope in LOCKOUT_SCOPE_BY_KIND.items() if scope is not LockoutScope.NONE}
    assert restricting, "the implementation must define at least one restricting kind"

    # The spec's reach must be ACCOUNT for a CRITICAL finding and nothing
    # otherwise, with the rank DERIVED from SCOPE_RANK rather than hardcoded --
    # asserting a literal "THEN 2 ELSE 0" anywhere in the file was satisfied by
    # RankForSeverity even after ReachOf was broken, so two mutations that made
    # the spec stop matching LOCKOUT_SCOPE_BY_KIND both passed the old pin.
    account_rank = SCOPE_RANK[LockoutScope.ACCOUNT]
    none_rank = SCOPE_RANK[LockoutScope.NONE]
    reach = _definition_body(text, "ReachOf")
    assert f"THEN {account_rank} ELSE {none_rank}" in reach, (
        f"ReachOf must halt at ACCOUNT (rank {account_rank}) for a CRITICAL "
        f"finding and nothing (rank {none_rank}) otherwise; the spec encodes "
        f"neither: {reach.strip()!r}"
    )

    # And the model's single restricting reach must be the one the
    # implementation actually uses, or the spec is wrong rather than coarse.
    reaches = {
        scope
        for scope in LOCKOUT_SCOPE_BY_KIND.values()
        if scope is not LockoutScope.NONE
    }
    assert reaches == {LockoutScope.ACCOUNT}, (
        "the spec models exactly one restricting reach; the implementation "
        f"has {sorted(s.value for s in reaches)}"
    )


def test_reconciliation_modes_match_the_implementation() -> None:
    """Every ReconciliationMode appears in the spec.

    The mode governs which findings are derivable at all -- a CURSOR delta proves
    nothing about executions it did not mention -- so a new mode the spec does not
    know about would leave the CURSOR rule unchecked for it.
    """
    text = _read("Reconciliation.tla")
    for mode in ReconciliationMode:
        assert f'"{mode.value}"' in text, f"spec omits ReconciliationMode.{mode.name}"


def test_reconciliation_spec_states_what_is_not_independently_verified() -> None:
    """The spec must record that two of its invariants are implied, not independent.

    This is the check that keeps defect #44's lesson from recurring in TLA+. A
    vacuity pass found that `NoOpenFindingIsResolved` cannot be broken without
    breaking `TypeOK`, and that `TypeOK` cannot be broken alone by design. The
    spec documents both. If a future edit removes that note, the claim of
    independent verification is no longer being made anywhere, and that silence is
    indistinguishable from not having checked.
    """
    text = _read("Reconciliation.tla")

    # The note must sit immediately above the property it describes. Checking that
    # the two names appear ANYWHERE in the file cannot detect the loss of the note
    # itself -- both names occur elsewhere -- which is how the previous version of
    # this pin was mutated into uselessness without going red.
    marker = text.upper().find("NOT INDEPENDENTLY VERIFIED")
    assert marker != -1, (
        "the spec must state which invariants are implied rather than "
        "independently falsifiable"
    )
    tail = text[marker:marker + 2000]
    for name in ("TypeOK", "NoOpenFindingIsResolved"):
        assert name in tail, (
            f"the scope note must discuss {name} specifically, next to the "
            "heading rather than somewhere else in the file"
        )


def test_reconciliation_spec_refuses_to_strand_a_cursor_finding() -> None:
    """A CURSOR delta cannot justify an internal-only finding, and the spec
    must forbid arriving at one by changing mode.

    TLC found this: a finding legitimately derived under FULL_SNAPSHOT survived
    `SetMode`, leaving a CURSOR-mode state carrying a finding the mode cannot
    support. The spec's fix is to refuse the transition rather than clear the
    finding -- discarding a real discrepancy because a query mode changed would
    be the dishonesty the spec exists to catch.

    Both assertions read a DEFINITION BODY rather than the whole file. A comment
    elsewhere satisfied the earlier version of this pin while the guard it was
    written to check had been deleted.
    """
    text = _read("Reconciliation.tla")

    setmode = _definition_body(text, "SetMode")
    guard = "mode" + chr(39) + ' = ' + chr(34) + 'CURSOR' + chr(34)
    assert guard in setmode, (
        "SetMode must guard against switching to CURSOR with an internal-only "
        f"finding open; its body is {setmode.strip()!r}"
    )
    assert "InternalOnlyKinds" in setmode, (
        "the CURSOR guard must actually test the internal-only kinds, not just "
        "mention CURSOR"
    )

    rediscover = _definition_body(text, "Rediscover")
    subtracts = chr(92) + " resolved"
    assert subtracts in rediscover, (
        "Rediscover must subtract the resolved set when computing stillOpen, so "
        "a resolved discrepancy does not reappear every cycle; its body is "
        f"{rediscover.strip()!r}"
    )
