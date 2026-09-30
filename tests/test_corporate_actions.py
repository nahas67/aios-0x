"""Corporate actions change a security's economics, not just its name.

A price series without action adjustment is wrong at every ex-date, and the
error is invisible: the chart is drawn on the same unadjusted series, so it
looks continuous and behaves discontinuously. Any feature computed across a
split boundary — a return, a moving average, a volatility estimate — inherits
the error.

These tests use real corporate-action shapes and assert the two properties that
matter: an adjustment is correct, and it is confined to the window it should
touch. The second is the one a naive implementation gets wrong, because
applying every action in the file to every observation produces a series that
is smooth, plausible, and wrong everywhere.

Each test names the economic situation it models, so a future reader can tell
which real-world event the fixture is standing in for.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from core.security_master import (
    ActionType,
    CorporateAction,
    CorporateActionEngine,
    InstrumentStatus,
)

ANCHOR = datetime(2024, 1, 1, tzinfo=UTC)
EX = datetime(2021, 6, 1, tzinfo=UTC)  # the ex-date
BEFORE_EX = datetime(2021, 5, 28, tzinfo=UTC)
AFTER_EX = datetime(2021, 6, 2, tzinfo=UTC)


def _action(
    action_type: ActionType,
    effective: datetime,
    *,
    action_id: str,
    ratio_old: str | None = None,
    ratio_new: str | None = None,
    cash: str | None = None,
    new_ticker: str | None = None,
    successor: str | None = None,
    record_date: date | None = None,
    ex_date: date | None = None,
) -> CorporateAction:
    return CorporateAction(
        action_id=action_id,
        instrument_id="acme",
        action_type=action_type,
        announced_at=effective - timedelta(days=30),
        effective_at=effective,
        record_date=record_date,
        ex_date=ex_date,
        ratio_old=Decimal(ratio_old) if ratio_old else None,
        ratio_new=Decimal(ratio_new) if ratio_new else None,
        cash_amount=Decimal(cash) if cash else None,
        new_ticker=new_ticker,
        successor_instrument_id=successor,
        source="fixture",
    )


# ══════════════════════════════════════════════════════════════════════════
# Splits: a stock split 2-for-1
# ══════════════════════════════════════════════════════════════════════════


def _two_for_one_split() -> CorporateAction:
    return _action(
        ActionType.SPLIT, EX, action_id="split-2-1", ratio_old="1", ratio_new="2",
        ex_date=EX.date(),
    )


def test_a_two_for_one_split_halves_the_earlier_price() -> None:
    """Model: ACME trades at 200, splits 2-for-1, and trades at 100 after.

    The economically continuous value is 100 at both instants, so the earlier
    observation must be back-adjusted by 1/2.
    """
    engine = CorporateActionEngine([_two_for_one_split()])
    before = engine.adjust_price("acme", BEFORE_EX, Decimal("200"), anchor=ANCHOR)
    after = engine.adjust_price("acme", AFTER_EX, Decimal("100"), anchor=ANCHOR)
    assert before == after == Decimal(100)


def test_a_split_doubles_the_earlier_share_count() -> None:
    """One pre-split share becomes two, which is the reciprocal of the price."""
    engine = CorporateActionEngine([_two_for_one_split()])
    quantity = engine.adjust_quantity("acme", BEFORE_EX, Decimal(1), anchor=ANCHOR)
    assert quantity == Decimal(2)


def test_a_post_split_observation_is_left_alone() -> None:
    """The split is already in the 100. Applying it again would give 50."""
    engine = CorporateActionEngine([_two_for_one_split()])
    factor = engine.adjustment("acme", AFTER_EX, anchor=ANCHOR)
    assert factor.price_factor == Decimal(1)
    assert factor.quantity_factor == Decimal(1)


def test_a_four_for_one_split_scales_by_one_quarter() -> None:
    engine = CorporateActionEngine(
        [_action(ActionType.SPLIT, EX, action_id="s4", ratio_old="1", ratio_new="4")]
    )
    factor = engine.adjustment("acme", BEFORE_EX, anchor=ANCHOR)
    assert factor.price_factor == Decimal("0.25")
    assert factor.quantity_factor == Decimal(4)


def test_a_reverse_split_scales_up() -> None:
    """Model: a distressed company reverses 1-for-10. Fewer shares, higher price."""
    engine = CorporateActionEngine(
        [_action(ActionType.REVERSE_SPLIT, EX, action_id="rev", ratio_old="10", ratio_new="1")]
    )
    factor = engine.adjustment("acme", BEFORE_EX, anchor=ANCHOR)
    assert factor.price_factor == Decimal(10)
    assert factor.quantity_factor == Decimal("0.1")


# ══════════════════════════════════════════════════════════════════════════
# Chained actions
# ══════════════════════════════════════════════════════════════════════════


def test_chained_splits_compound_across_the_whole_history() -> None:
    """Model: 2-for-1 in 2019, then 3-for-1 in 2021.

    A single 2018 observation is 6 post-split shares, so it scales by 1/6.
    """
    engine = CorporateActionEngine(
        [
            _action(
                ActionType.SPLIT,
                datetime(2019, 4, 1, tzinfo=UTC),
                action_id="s2019",
                ratio_old="1",
                ratio_new="2",
            ),
            _action(
                ActionType.SPLIT,
                datetime(2021, 4, 1, tzinfo=UTC),
                action_id="s2021",
                ratio_old="1",
                ratio_new="3",
            ),
        ]
    )
    factor = engine.adjustment("acme", datetime(2018, 1, 1, tzinfo=UTC), anchor=ANCHOR)
    assert factor.price_factor == Decimal(1) / Decimal(6)
    assert factor.quantity_factor == Decimal(6)
    assert factor.applied == 2


def test_an_observation_inside_the_chain_sees_only_later_actions() -> None:
    """Model: a 2020 price already reflects the 2019 split but not the 2021 one."""
    engine = CorporateActionEngine(
        [
            _action(
                ActionType.SPLIT,
                datetime(2019, 4, 1, tzinfo=UTC),
                action_id="s2019",
                ratio_old="1",
                ratio_new="2",
            ),
            _action(
                ActionType.SPLIT,
                datetime(2021, 4, 1, tzinfo=UTC),
                action_id="s2021",
                ratio_old="1",
                ratio_new="3",
            ),
        ]
    )
    factor = engine.adjustment("acme", datetime(2020, 1, 1, tzinfo=UTC), anchor=ANCHOR)
    assert factor.applied == 1
    assert factor.price_factor == Decimal(1) / Decimal(3)


def test_split_then_reverse_split_returns_to_the_original_scale() -> None:
    """Model: 2-for-1 then 1-for-2. The two cancel exactly."""
    engine = CorporateActionEngine(
        [
            _action(
                ActionType.SPLIT,
                datetime(2020, 1, 1, tzinfo=UTC),
                action_id="up",
                ratio_old="1",
                ratio_new="2",
            ),
            _action(
                ActionType.REVERSE_SPLIT,
                datetime(2021, 1, 1, tzinfo=UTC),
                action_id="down",
                ratio_old="2",
                ratio_new="1",
            ),
        ]
    )
    factor = engine.adjustment("acme", datetime(2019, 12, 31, tzinfo=UTC), anchor=ANCHOR)
    assert factor.price_factor == Decimal(1)
    assert factor.quantity_factor == Decimal(1)


# ══════════════════════════════════════════════════════════════════════════
# Dividends
# ══════════════════════════════════════════════════════════════════════════


def test_a_dividend_moves_cash_but_not_share_count() -> None:
    """Model: a $1.00 dividend. Share count is unchanged; the holder got cash."""
    engine = CorporateActionEngine(
        [_action(ActionType.DIVIDEND, EX, action_id="div", cash="1.00")]
    )
    factor = engine.adjustment("acme", BEFORE_EX, anchor=ANCHOR)
    assert factor.quantity_factor == Decimal(1)
    assert factor.cash_per_share == Decimal("1.00")


def test_dividends_accumulate_across_the_window() -> None:
    engine = CorporateActionEngine(
        [
            _action(
                ActionType.DIVIDEND, datetime(2020, 3, 1, tzinfo=UTC), action_id="d1", cash="0.50"
            ),
            _action(
                ActionType.DIVIDEND, datetime(2021, 3, 1, tzinfo=UTC), action_id="d2", cash="0.75"
            ),
        ]
    )
    factor = engine.adjustment("acme", datetime(2019, 12, 31, tzinfo=UTC), anchor=ANCHOR)
    assert factor.cash_per_share == Decimal("1.25")


def test_a_dividend_is_not_folded_into_the_price_factor() -> None:
    """Total return needs the dividend separately from the price.

    Folding it in would make it impossible to tell price appreciation from cash
    paid out, which is the distinction a performance report exists to make.
    """
    engine = CorporateActionEngine(
        [_action(ActionType.DIVIDEND, EX, action_id="div", cash="1.00")]
    )
    assert engine.adjustment("acme", BEFORE_EX, anchor=ANCHOR).price_factor == Decimal(1)


# ══════════════════════════════════════════════════════════════════════════
# Identity actions
# ══════════════════════════════════════════════════════════════════════════


def test_a_delisting_is_a_terminal_identity_transition() -> None:
    """Model: ACME is acquired and delisted. It can never trade again."""
    engine = CorporateActionEngine(
        [_action(ActionType.DELISTING, EX, action_id="delist", successor="acme-holdco")]
    )
    transitions = engine.identity_transitions("acme")
    assert transitions == [(EX, InstrumentStatus.DELISTED, "acme-holdco")]


def test_a_symbol_change_is_tracked_over_time() -> None:
    """Model: the company rebrands from ACME to ACMECORP.

    Joining a 2019 series to a ticker that did not exist until 2021 is a silent
    corruption, so the engine answers the question directly.
    """
    engine = CorporateActionEngine(
        [_action(ActionType.SYMBOL_CHANGE, EX, action_id="rebrand", new_ticker="ACME")]
    )
    assert engine.ticker_at("acme", BEFORE_EX) is None
    assert engine.ticker_at("acme", AFTER_EX) == "ACME"


def test_a_merger_records_the_successor() -> None:
    """Model: ACME merges into MEGACORP. The chain must name the successor."""
    engine = CorporateActionEngine(
        [_action(ActionType.MERGER, EX, action_id="merger", successor="megacorp")]
    )
    transitions = engine.identity_transitions("acme")
    assert transitions == [(EX, InstrumentStatus.DELISTED, "megacorp")]


# ══════════════════════════════════════════════════════════════════════════
# Engine invariants
# ══════════════════════════════════════════════════════════════════════════


def test_the_transform_inverts_exactly_for_a_long_chain() -> None:
    """Round-tripping must recover the raw value bit for bit.

    If it does not, re-fitting a strategy on adjusted data silently rewrites
    the history it claims to have used.
    """
    engine = CorporateActionEngine(
        [
            _action(
                ActionType.SPLIT,
                datetime(2019, 4, 1, tzinfo=UTC),
                action_id="s1",
                ratio_old="1",
                ratio_new="7",
            ),
            _action(
                ActionType.SPLIT,
                datetime(2021, 4, 1, tzinfo=UTC),
                action_id="s2",
                ratio_old="1",
                ratio_new="3",
            ),
        ]
    )
    moment = datetime(2018, 1, 1, tzinfo=UTC)
    raw = Decimal("1234.5678")
    adjusted = engine.adjust_price("acme", moment, raw, anchor=ANCHOR)
    assert engine.unadjust_price("acme", moment, adjusted, anchor=ANCHOR) == raw


def test_an_instrument_with_no_actions_adjusts_to_itself() -> None:
    engine = CorporateActionEngine()
    assert engine.adjust_price("acme", ANCHOR, Decimal("10")) == Decimal("10")
    assert engine.adjustment("acme", ANCHOR).is_identity


def test_an_instrument_with_another_instruments_actions_is_unaffected() -> None:
    """Action chains are per instrument. Leaking across them is a real bug shape."""
    other = CorporateAction(
        action_id="other-split",
        instrument_id="globex",
        action_type=ActionType.SPLIT,
        announced_at=datetime(2020, 1, 1, tzinfo=UTC),
        effective_at=datetime(2020, 6, 1, tzinfo=UTC),
        ratio_old=Decimal(1),
        ratio_new=Decimal(10),
        source="fixture",
    )
    engine = CorporateActionEngine([other])
    assert engine.adjustment("acme", datetime(2019, 1, 1, tzinfo=UTC), anchor=ANCHOR).is_identity
    factor = engine.adjustment("globex", datetime(2019, 1, 1, tzinfo=UTC), anchor=ANCHOR)
    assert factor.price_factor == Decimal("0.1")


def test_actions_are_returned_in_effective_time_order() -> None:
    """Ordering is the basis of the windowing, so it is a contract."""
    late = _action(ActionType.SPLIT, datetime(2021, 1, 1, tzinfo=UTC), action_id="b", ratio_old="1", ratio_new="2")
    early = _action(ActionType.SPLIT, datetime(2019, 1, 1, tzinfo=UTC), action_id="a", ratio_old="1", ratio_new="2")
    engine = CorporateActionEngine([late, early])
    assert [a.action_id for a in engine.actions("acme")] == ["a", "b"]


def test_anchoring_before_the_observation_is_refused() -> None:
    """A nonsensical frame is an error, not a silently clamped answer.

    Clamping would hide a caller bug that produces a plausible-looking factor.
    """
    engine = CorporateActionEngine([_two_for_one_split()])
    with pytest.raises(ValueError, match="after the requested anchor"):
        engine.adjustment("acme", ANCHOR, anchor=BEFORE_EX)
