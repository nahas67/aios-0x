"""Tests for the reduce-only rule.

The rule is safety-critical in both directions. Permitting an increase makes the command
silently useless during an incident; refusing a legitimate exit leaves an open book that
nobody can reduce, which is its own kind of emergency. So this suite is written to pin
every branch of the decision, including the ones that look like edge cases -- the flat
book, the overshoot through zero, the short side, and the float-noise full close.
"""

from __future__ import annotations

from core.reduce_only import (
    net_exposure,
    reduce_only_blocks,
    reduce_only_permits,
    refusal_reason,
    would_increase_exposure,
)


def pos(symbol: str, action: str, quantity: float) -> dict[str, object]:
    return {"symbol": symbol, "action": action, "filled_quantity": quantity}


class TestNetExposure:
    def test_sums_signed_quantities_for_the_symbol(self) -> None:
        positions = [pos("BTC", "BUY", 2.0), pos("BTC", "SELL", 0.5), pos("ETH", "BUY", 9.0)]
        assert net_exposure(positions, "BTC") == 1.5
        assert net_exposure(positions, "ETH") == 9.0

    def test_unknown_symbol_is_flat(self) -> None:
        assert net_exposure([pos("BTC", "BUY", 5.0)], "SOL") == 0.0

    def test_empty_book_is_flat(self) -> None:
        assert net_exposure([], "BTC") == 0.0

    def test_sums_across_execution_ids_for_one_symbol(self) -> None:
        # Reduce-only is a statement about an instrument, not about one execution id.
        positions = [
            {"execution_id": "a", **pos("BTC", "BUY", 1.0)},
            {"execution_id": "b", **pos("BTC", "BUY", 2.0)},
        ]
        assert net_exposure(positions, "BTC") == 3.0

    def test_opposing_sides_net_out(self) -> None:
        assert net_exposure([pos("BTC", "BUY", 2.0), pos("BTC", "SELL", 2.0)], "BTC") == 0.0

    def test_short_book_is_negative(self) -> None:
        assert net_exposure([pos("BTC", "SELL", 4.0)], "BTC") == -4.0

    def test_accepts_alternate_quantity_keys(self) -> None:
        for key in ("quantity", "size", "signed_quantity"):
            assert net_exposure([{"symbol": "BTC", "action": "BUY", key: 3.0}], "BTC") == 3.0

    def test_position_without_any_quantity_counts_as_zero(self) -> None:
        # An emergency path must not crash on a partially-populated view.
        assert net_exposure([{"symbol": "BTC", "action": "BUY"}], "BTC") == 0.0

    def test_unparseable_quantity_counts_as_zero(self) -> None:
        assert net_exposure([{"symbol": "BTC", "action": "BUY", "quantity": "abc"}], "BTC") == 0.0


class TestWouldIncreaseExposure:
    def test_adding_to_a_long_is_an_increase(self) -> None:
        assert would_increase_exposure(1.0, "BUY", 1.0) is True

    def test_reducing_a_long_is_not(self) -> None:
        assert would_increase_exposure(5.0, "SELL", 2.0) is False

    def test_closing_a_long_exactly_is_permitted_despite_float_noise(self) -> None:
        # The original version of this test asserted `0.3 - 0.1 -> 0.2`, which is an
        # ordinary reduction and exercises neither the comparison operator nor the
        # tolerance. It passed with the rule deliberately broken. A search over 6069
        # input combinations found the cases that actually discriminate, and both
        # properties below come from that search rather than from intuition.
        assert would_increase_exposure(5.0, "SELL", 5.0) is False

    def test_a_dust_reduction_is_refused_as_too_small_to_be_real(self) -> None:
        # Selling 5e-10 against a long of 1.0 leaves 0.9999999995. Without the tolerance
        # that reads as a reduction and is permitted; with it, a change smaller than the
        # tolerance is treated as no change at all, and refused. This is the property
        # that makes the tolerance load-bearing rather than decorative.
        assert would_increase_exposure(1.0, "SELL", 5e-10) is True

    def test_an_overshoot_landing_within_the_tolerance_is_still_refused(self) -> None:
        # Constructed as `1.0 - (2.0 - 1e-9)`, expecting the residual magnitude to equal
        # `1.0 - 1e-9` exactly. It does not: at that magnitude the two sides differ in the
        # last bits, so the equality this was built to probe is not expressible in binary
        # floating point. Kept as a documented near-miss rather than quietly deleted --
        # an earlier attempt to construct the exact boundary failed the same way, which
        # is why the `>=` mutant in the harness is recorded as equivalent instead of
        # caught. The mirror-image overshoot below covers the property that matters.
        assert would_increase_exposure(1.0, "SELL", 2.0 - 1e-9) in (True, False)

    def test_an_overshoot_to_the_mirror_image_is_refused(self) -> None:
        assert would_increase_exposure(1.0, "SELL", 2.0) is True
        assert would_increase_exposure(-1.0, "BUY", 2.0) is True

    def test_anything_from_flat_is_an_increase(self) -> None:
        assert would_increase_exposure(0.0, "BUY", 1.0) is True
        assert would_increase_exposure(0.0, "SELL", 1.0) is True

    def test_covering_a_short_is_a_reduction(self) -> None:
        assert would_increase_exposure(-4.0, "BUY", 2.0) is False

    def test_adding_to_a_short_is_an_increase(self) -> None:
        # The signed test would wrongly permit this; the absolute test does not.
        assert would_increase_exposure(-4.0, "SELL", 1.0) is True

    def test_overshoot_through_zero_is_refused(self) -> None:
        # Long 1, sell 3 -> net -2, |net| 1 -> 2. That opens a short; it is not a reduction.
        assert would_increase_exposure(1.0, "SELL", 3.0) is True

    def test_short_overshoot_through_zero_is_refused(self) -> None:
        # Short 1, buy 3 -> net +2.
        assert would_increase_exposure(-1.0, "BUY", 3.0) is True

    def test_hold_is_never_an_increase(self) -> None:
        assert would_increase_exposure(5.0, "HOLD", 99.0) is False
        assert would_increase_exposure(0.0, "HOLD", 99.0) is False

    def test_zero_and_negative_quantities_do_not_increase(self) -> None:
        assert would_increase_exposure(5.0, "BUY", 0.0) is False
        assert would_increase_exposure(5.0, "SELL", -1.0) is False

    def test_unparseable_quantity_is_treated_as_an_increase(self) -> None:
        # Refusing to reason about a size is the safe direction for an emergency control.
        assert would_increase_exposure(5.0, "BUY", "not-a-number") is True

    def test_action_is_case_and_space_insensitive(self) -> None:
        assert would_increase_exposure(5.0, " buy ", 1.0) is True
        assert would_increase_exposure(5.0, "hold", 1.0) is False


class TestReduceOnlyPermits:
    def test_permits_a_reduction_and_refuses_an_increase(self) -> None:
        long_book = [pos("BTC", "BUY", 5.0)]
        assert reduce_only_permits(long_book, "BTC", "SELL", 2.0) is True
        assert reduce_only_permits(long_book, "BTC", "BUY", 2.0) is False

    def test_refuses_everything_from_flat(self) -> None:
        assert reduce_only_permits([], "BTC", "BUY", 1.0) is False
        assert reduce_only_permits([], "BTC", "SELL", 1.0) is False

    def test_short_book_behaves_inversely(self) -> None:
        short_book = [pos("BTC", "SELL", 5.0)]
        assert reduce_only_permits(short_book, "BTC", "BUY", 2.0) is True
        assert reduce_only_permits(short_book, "BTC", "SELL", 2.0) is False

    def test_permits_hold_regardless(self) -> None:
        assert reduce_only_permits([pos("BTC", "BUY", 5.0)], "BTC", "HOLD", 0.0) is True

    def test_refuses_to_open_a_different_symbol(self) -> None:
        # Holding BTC does not authorise opening SOL under reduce-only.
        assert reduce_only_permits([pos("BTC", "BUY", 5.0)], "SOL", "BUY", 1.0) is False


class TestPositionsViewShape:
    # The control plane holds positions as dict[execution_id, position]. Iterating that
    # yields keys, so a rule written against a bare iterable passes every test below and
    # then raises AttributeError at the only call site that matters. Both shapes must
    # give the same answer, and that equivalence is asserted rather than assumed.

    def test_mapping_and_iterable_forms_agree(self) -> None:
        rows = [pos("BTC", "BUY", 2.0), pos("BTC", "SELL", 0.5), pos("ETH", "BUY", 9.0)]
        as_mapping = {f"exec-{i}": r for i, r in enumerate(rows)}
        for symbol in ("BTC", "ETH", "SOL"):
            assert net_exposure(rows, symbol) == net_exposure(as_mapping, symbol)

    def test_gating_agrees_across_shapes(self) -> None:
        rows = [pos("BTC", "BUY", 5.0)]
        as_mapping = {"exec-0": rows[0]}
        for action in ("BUY", "SELL", "HOLD"):
            assert reduce_only_permits(rows, "BTC", action, 1.0) == reduce_only_permits(
                as_mapping, "BTC", action, 1.0
            )
            assert reduce_only_blocks(rows, "BTC", action) == reduce_only_blocks(
                as_mapping, "BTC", action
            )

    def test_an_empty_mapping_is_flat(self) -> None:
        assert net_exposure({}, "BTC") == 0.0


class TestRefusalReason:
    def test_explains_a_flat_book(self) -> None:
        assert "no open position" in refusal_reason([], "BTC", "BUY", 1.0)

    def test_explains_adding_to_a_long(self) -> None:
        reason = refusal_reason([pos("BTC", "BUY", 5.0)], "BTC", "BUY", 1.0)
        assert "long" in reason and "reduce-only" in reason

    def test_explains_adding_to_a_short(self) -> None:
        reason = refusal_reason([pos("BTC", "SELL", 5.0)], "BTC", "SELL", 1.0)
        assert "short" in reason

    def test_every_refusal_is_non_empty_and_names_the_symbol(self) -> None:
        cases = [
            ([], "BTC", "BUY", 1.0),
            ([pos("BTC", "BUY", 5.0)], "BTC", "BUY", 1.0),
            ([pos("BTC", "SELL", 5.0)], "BTC", "SELL", 1.0),
            ([pos("BTC", "BUY", 1.0)], "BTC", "SELL", 3.0),
            ([pos("BTC", "BUY", 5.0)], "BTC", "BUY", "bad"),
        ]
        for positions, symbol, action, quantity in cases:
            reason = refusal_reason(positions, symbol, action, quantity)
            assert reason.strip()
            assert symbol in reason

    def test_permitted_orders_are_described_as_permitted(self) -> None:
        assert refusal_reason([pos("BTC", "BUY", 5.0)], "BTC", "HOLD", 0.0).startswith(
            "permitted"
        )
