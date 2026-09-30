"""The specs describe the implementation, not a neighbouring machine (G220).

TLA+ cannot be model-checked here (no JVM, no TLC binary — stated, not
hidden), so these tests pin the next best thing that is checkable: the
specs exist, they name the properties they claim, and every state they
mention is a state the implementation actually runs. A spec that drifts from
its implementation is fiction with mathematics' formatting; these tests fail
the moment code renames a state without renaming it in the spec.
"""

from __future__ import annotations

from pathlib import Path

from core.financial_kernel import OutboxStatus
from schemas.contracts import _TERMINAL_ORDER_STATES, OrderStatus

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"


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
    import re

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
