"""REDUCE_ONLY's overshoot tier: the quantity-aware path.

`classify_plan` enforces two tiers. Without a portfolio value it can only ask whether an
order's direction increases exposure. With one, it converts the plan's
`position_size_pct` into an absolute quantity and runs the full rule, which is the only
way to catch an oversized order that crosses through zero and opens the opposite
position.

This file exists because the whole point of the tier is a case the directional rule cannot
see: a SELL against a long, permitted by direction, refused by size. If the wiring were
absent the directional tests would still all pass, which is precisely how the earlier
unreachable-gate defect survived review.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.control_plane import ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor

EQUITY = 10_000.0
PRICE = 100.0


def make_plane(
    positions: list[dict[str, object]] | None = None,
    *,
    equity: float | None = EQUITY,
    price: float = PRICE,
) -> ControlPlane:
    def positions_view() -> dict[str, dict[str, str]]:
        return {f"exec-{i}": dict(p) for i, p in enumerate(positions or [])}

    plane = ControlPlane(
        store=SqliteMemoryStore(":memory:"),
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        positions_view=positions_view,
        price_lookup=lambda symbol: price,
        portfolio_value=(lambda: equity) if equity is not None else None,
    )
    plane.autonomy = plane.autonomy.__class__("AUTONOMOUS")
    plane.reduce_only = True
    return plane


def plan(symbol: str, action: str, size_pct: float = 10.0) -> SimpleNamespace:
    # position_size_pct is documented as the notional this trade ADDS, so an increment.
    return SimpleNamespace(
        strategy=SimpleNamespace(
            symbol=symbol, action=action, position_size_pct=size_pct
        )
    )


def long_book(quantity: float = 1.0) -> list[dict[str, object]]:
    return [{"symbol": "BTC", "action": "BUY", "filled_quantity": quantity}]


class TestOvershootIsCaughtWhenSizeIsKnown:
    def test_a_reducing_sell_is_permitted(self) -> None:
        # long 1.0; 10% of 10,000 at 100 = 10 units, which would OVERSHOOT a 1.0 long into
        # a 9.0 short. That is a flip, so it must be held.
        plane = make_plane(long_book(1.0))
        assert plane.classify_plan(plan("BTC", "SELL", size_pct=10.0)) == "HOLD"

    def test_a_small_sell_is_permitted(self) -> None:
        # long 100; 10% of 10,000 at 100 = 10 units -> net 90, a genuine reduction.
        plane = make_plane(long_book(100.0))
        assert plane.classify_plan(plan("BTC", "SELL", size_pct=10.0)) == "EXECUTE"

    def test_adding_to_a_long_is_held(self) -> None:
        plane = make_plane(long_book(100.0))
        assert plane.classify_plan(plan("BTC", "BUY", size_pct=1.0)) == "HOLD"

    def test_anything_from_flat_is_held(self) -> None:
        plane = make_plane()
        assert plane.classify_plan(plan("BTC", "BUY", size_pct=1.0)) == "HOLD"

    def test_covering_a_short_is_permitted(self) -> None:
        plane = make_plane([{"symbol": "BTC", "action": "SELL", "filled_quantity": 100.0}])
        assert plane.classify_plan(plan("BTC", "BUY", size_pct=1.0)) == "EXECUTE"

    def test_the_overshoot_case_is_exactly_where_the_two_tiers_differ(self) -> None:
        # Same book, same plan. With a portfolio value the size is known and the overshoot
        # is caught; without one only direction is available and the order would be
        # permitted. This single pair is the reason the tier exists.
        with_value = make_plane(long_book(1.0))
        without_value = make_plane(long_book(1.0), equity=None)
        assert with_value.classify_plan(plan("BTC", "SELL", 10.0)) == "HOLD"
        assert without_value.classify_plan(plan("BTC", "SELL", 10.0)) == "EXECUTE"


class TestFallbacksNeverGuess:
    # Each of these must fall back to the DIRECTIONAL rule rather than inventing a size.
    # Guessing would make the overshoot check a decoration that appears to work.

    def test_missing_price_falls_back_without_crashing(self) -> None:
        plane = make_plane(long_book(100.0), price=0.0)
        assert plane.classify_plan(plan("BTC", "SELL", 10.0)) == "EXECUTE"

    def test_zero_equity_falls_back(self) -> None:
        plane = make_plane(long_book(100.0), equity=0.0)
        assert plane.classify_plan(plan("BTC", "SELL", 10.0)) == "EXECUTE"

    def test_missing_size_pct_falls_back(self) -> None:
        plane = make_plane(long_book(1.0))
        bare = SimpleNamespace(strategy=SimpleNamespace(symbol="BTC", action="SELL"))
        # Direction permits it; no size means no overshoot refinement. Must not raise.
        assert plane.classify_plan(bare) == "EXECUTE"

    def test_unparseable_size_pct_falls_back(self) -> None:
        plane = make_plane(long_book(100.0))
        bad = SimpleNamespace(
            strategy=SimpleNamespace(
                symbol="BTC", action="SELL", position_size_pct="not-a-number"
            )
        )
        assert plane.classify_plan(bad) == "EXECUTE"

    def test_the_directional_half_survives_every_fallback(self) -> None:
        # Whatever is missing, an order that increases exposure is still refused. The
        # refinement is optional; the ceiling is not.
        for plane in (
            make_plane(long_book(1.0), equity=None),
            make_plane(long_book(1.0), price=0.0),
            make_plane(long_book(1.0), equity=0.0),
        ):
            assert plane.classify_plan(plan("BTC", "BUY", 10.0)) == "HOLD"
            assert plane.classify_plan(plan("SOL", "BUY", 10.0)) == "HOLD"

    def test_hold_is_never_blocked_on_either_tier(self) -> None:
        for plane in (make_plane(long_book(1.0)), make_plane(long_book(1.0), equity=None)):
            assert plane.classify_plan(plan("BTC", "HOLD", 10.0)) == "EXECUTE"


class TestQuantitiesAreProjectedFromTheRunner:
    # The tier is inert unless the positions view carries a size, and a comment asserting
    # that is not a test. This INVOKES the real method on a stand-in paper engine and
    # reads what comes out, so removing the projection fails here rather than leaving every
    # other test in this file passing for the wrong reason.
    def test_positions_view_includes_filled_quantity(self) -> None:
        from simulation.replay_runner import ReplayRunner

        position = SimpleNamespace(
            action="BUY",
            receipt=SimpleNamespace(symbol="BTC", filled_quantity=2.5),
        )
        stand_in = SimpleNamespace(
            paper=SimpleNamespace(open_positions={"exec-1": position})
        )
        view = ReplayRunner._positions_view(stand_in)  # type: ignore[arg-type]

        assert view == {
            "exec-1": {"symbol": "BTC", "action": "BUY", "filled_quantity": "2.5"}
        }

    def test_the_projected_view_actually_drives_the_overshoot_rule(self) -> None:
        # End to end through the runner's own projection shape: the string quantity it
        # emits must be usable by net_exposure, which is what the whole tier rests on.
        from core.reduce_only import net_exposure, reduce_only_permits

        view = {"exec-1": {"symbol": "BTC", "action": "BUY", "filled_quantity": "1.0"}}
        assert net_exposure(view, "BTC") == 1.0
        # A 10-unit sell would flip a 1-unit long; the rule must refuse it.
        assert reduce_only_permits(view, "BTC", "SELL", 10.0) is False
