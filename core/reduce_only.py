"""Reduce-only: block orders that increase exposure, permit those that reduce it.

WHY THIS EXISTS. ARCHITECTURE.txt section 8 names REDUCE_ONLY among the eight
emergency commands. Five of the eight had no counterpart in the tree, and REDUCE_ONLY was
the operationally worst of them: containment was entirely global, so an operator who
wanted exposure down had exactly two options -- do nothing, or flatten everything. There
was no middle setting. This module is that middle setting.

THE RULE, stated once so it cannot drift between the docs, the tests and the enforcement
site. Standard broker reduce-only semantics:

    An order is PERMITTED if and only if it strictly reduces the ABSOLUTE net exposure of
    its symbol. An order is REFUSED when it would leave |net| greater than or equal to the
    |net| it started with.

Three consequences follow, and all three are deliberate:

  * From FLAT, every order is refused. A reduce-only order against no position opens one,
    which is an increase from zero. Refusing is what makes the command mean "reduce", not
    "stop".
  * An overshoot is REFUSED. Selling 3 against a long 1 would cross through zero and open
    a short of 2, taking |net| from 1 to 2. That is an increase wearing reduce-only
    clothing, and permitting it would let the command flip the book rather than shrink it.
  * HOLD is permitted. It changes no exposure, so it cannot increase any.

This is measured on ABSOLUTE net exposure rather than signed, because "reduce" for a
short position means buying it back, not selling more of it. A signed test would invert
every short-side decision.

WHY A PURE MODULE. The enforcement site is `ControlPlane.classify_plan`, which has no
component-test framework to test against, and this rule is safety-critical: an off-by-one
here either blocks every legitimate exit (a stuck book nobody can reduce) or permits an
increase (the command silently does nothing during an incident). So the decision lives
here, with no imports from the rest of the tree, and is exhaustively unit-tested.

The comparison uses a relative epsilon rather than an exact zero test because the
quantities are floats converted from decimal strings at the venue boundary, and
`0.1 + 0.2 != 0.3`. An exact comparison would refuse a legitimate full close roughly one
time in ten.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: Relative tolerance for float comparisons on venue-sourced quantities. Large enough to
#: absorb accumulated binary rounding, small enough that it can never matter next to a
#: real position.
_EPS = 1e-9


def _as_positions(
    source: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Normalise the two shapes this rule is called with.

    The control plane holds its positions as `dict[execution_id, position]` -- that is the
    shape `_positions_view` returns and the one the composition root actually supplies.
    Iterating that dict yields its KEYS, so a rule written against a plain iterable of
    positions raises `AttributeError: 'str' object has no attribute 'get'` the moment it
    is wired up. Every unit test here passed a list and so never saw it; only the
    integration test against the real call site did. Accepting both is deliberate, and
    the mapping form is the one that matters.
    """
    if isinstance(source, Mapping):
        return list(source.values())
    return list(source)


def net_exposure(
    positions: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]], symbol: str
) -> float:
    """Signed net quantity held in ``symbol``. Positive is long, negative is short.

    ``positions`` is the control plane's positions view: keyed by execution id, with each
    value carrying at least ``symbol``, ``action`` and a quantity. A bare iterable of
    positions is also accepted. The quantity key has been spelled three ways in this
    tree, so all are read and a position with none of them counts as zero rather than
    crashing an emergency path.

    Summing by symbol rather than by execution id is deliberate: reduce-only is a
    statement about net exposure in an instrument, and a book holding the same symbol
    across several execution ids is still one exposure.
    """
    total = 0.0
    for position in _as_positions(positions):
        if str(position.get("symbol", "")) != symbol:
            continue
        action = str(position.get("action", "BUY")).upper()
        quantity = _quantity_of(position)
        total += quantity if action == "BUY" else -quantity
    return total


def _quantity_of(position: Mapping[str, Any]) -> float:
    for key in ("filled_quantity", "quantity", "size", "signed_quantity"):
        raw = position.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def would_increase_exposure(current_net: float, action: str, quantity: float) -> bool:
    """Whether ``action`` of ``quantity`` would leave |net| at or above where it started.

    This is the whole rule. ``current_net`` is signed; the comparison is on absolute
    values, so it behaves correctly for shorts.
    """
    side = action.strip().upper()
    if side == "HOLD":
        return False

    try:
        size = float(quantity)
    except (TypeError, ValueError):
        # An unparseable size cannot be shown to be an increase, and refusing to reason
        # about it is the safe direction for an emergency control.
        return True

    if size <= 0:
        # A non-positive order changes no exposure.
        return False

    signed = current_net + (size if side == "BUY" else -size)
    return abs(signed) >= abs(current_net) - _EPS


def reduce_only_permits(
    positions: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    symbol: str,
    action: str,
    quantity: float,
) -> bool:
    """True when the order may proceed under reduce-only for ``symbol``."""
    return not would_increase_exposure(net_exposure(positions, symbol), action, quantity)


def reduce_only_blocks(
    positions: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    symbol: str,
    action: str,
) -> bool:
    """Directional half of the rule, for gates that do not know the order's size.

    `ControlPlane.classify_plan` sees a plan's symbol and action but not an absolute
    quantity -- the strategy contract carries `position_size_pct`, a percentage of
    portfolio risk, which is not comparable to a venue quantity without a portfolio value
    the classification path does not hold. Rather than invent a conversion, this answers
    the part that is answerable and is the safety-critical half: does the order's
    direction increase the exposure at all?

    True for any order against a flat book, for BUY against a long, and for SELL against a
    short. False only where the order can only shrink the position.

    WHAT THIS DOES NOT DO: it cannot detect an overshoot, because an overshoot is defined
    by size. Selling 3 against a long 1 passes here and is correctly refused by
    `would_increase_exposure`, which is wired where a quantity exists. This is stated
    plainly rather than left for an operator to discover during an incident.
    """
    side = action.strip().upper()
    if side == "HOLD":
        return False
    current = net_exposure(positions, symbol)
    if abs(current) <= _EPS:
        return True
    if side == "BUY":
        return current > 0
    if side == "SELL":
        return current < 0
    # An unrecognised side is treated as an increase: refusing to reason about a side is
    # the safe direction for an emergency control.
    return True


def refusal_reason(
    positions: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    symbol: str,
    action: str,
    quantity: float,
) -> str:
    """A human-readable reason, for the audit record and the operator surface.

    An emergency control that refuses without saying why trains operators to retry it, and
    a retry against a reduce-only gate can turn a controlled reduction into an incident.
    """
    current = net_exposure(positions, symbol)
    side = action.strip().upper()
    if side == "HOLD":
        return "permitted: HOLD changes no exposure"
    if abs(current) <= _EPS:
        return f"reduce-only: no open position in {symbol}, so any order would open one"
    direction = "long" if current > 0 else "short"
    if side == "BUY" and current > 0:
        return f"reduce-only: BUY adds to an existing long in {symbol}"
    if side == "SELL" and current < 0:
        return f"reduce-only: SELL adds to an existing short in {symbol}"
    return (
        f"reduce-only: {side} {quantity} against a {direction} of {abs(current):g} in "
        f"{symbol} would not reduce the position"
    )
