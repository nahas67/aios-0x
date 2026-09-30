"""The pre-trade checklist refuses the right order for the named reason (G140).

The defect class this suite exists to prevent is a firewall that passes an
order it should have refused — or refuses without saying which check fired,
leaving the operator to re-run the evaluation by hand. Each of the fifteen
checks therefore has a test that fails it individually and asserts the
refusal names the check, plus the adversarial cases: forgery, expiry, replay
across instruments, and a reduction that must never increase.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from core.capital_firewall import (
    CHECK_NAMES,
    CapitalFirewall,
    FirewallDecision,
    PreTradeOrder,
    issue,
)
from core.contamination import ObservationTiming, SurvivorshipReport
from core.security_master import (
    AssetClass,
    InstrumentIdentity,
    InstrumentStatus,
)

SEAL_A = "firewall-test-seal-001"
T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(seconds=60)


def _identity(
    instrument_id: str,
    ticker: str,
    mic: str,
    *,
    status: InstrumentStatus = InstrumentStatus.ACTIVE,
    lot_size: Decimal | None = Decimal("1"),
) -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=instrument_id,
        listing_id=f"{mic}:{instrument_id}",
        ticker=ticker,
        mic=mic,
        venue=mic,
        asset_class=AssetClass.EQUITY,
        currency="USD",
        lot_size=lot_size,
        status=status,
        valid_from=T0 - timedelta(days=365),
        recorded_from=T0 - timedelta(days=365),
        source="test",
    )


class StubMaster:
    """A security master with two live listings and one delisting on demand.

    ``resolve`` answers the trading-path question; ``as_of`` answers the
    point-in-time one. The split is what lets the liveness test fail check 7
    while check 6 still passes.
    """

    def __init__(self, *, delisted: tuple[str, ...] = (), lots: dict | None = None) -> None:
        self._delisted = set(delisted)
        self._lots = lots or {}

    def _row(self, instrument_id: str, ticker: str, mic: str) -> InstrumentIdentity:
        status = (
            InstrumentStatus.DELISTED
            if instrument_id in self._delisted
            else InstrumentStatus.ACTIVE
        )
        return _identity(
            instrument_id, ticker, mic, status=status, lot_size=self._lots.get(instrument_id)
        )

    def resolve(self, ticker: str, mic: str) -> InstrumentIdentity | None:
        table = {"ACME": "inst-acme", "OTHER": "inst-other"}
        instrument_id = table.get(ticker)
        if instrument_id is None or mic != "XNYS":
            return None
        if instrument_id in self._delisted:
            return self._row(instrument_id, ticker, mic)
        return _identity(
            instrument_id, ticker, mic, lot_size=self._lots.get(instrument_id, Decimal("1"))
        )

    def as_of(self, instrument_id: str, moment: datetime) -> InstrumentIdentity | None:
        _ = moment
        table = {"inst-acme": "ACME", "inst-other": "OTHER"}
        ticker = table.get(instrument_id)
        if ticker is None:
            return None
        return self._row(instrument_id, ticker, "XNYS")


class StubOracle:
    """A certification oracle that can be revoked mid-test."""

    def __init__(self, certified: bool = True) -> None:
        self.certified = certified

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        _ = (strategy_id, strategy_version)
        return object() if self.certified else None

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        _ = (strategy_id, strategy_version)
        return self.certified


def _clean_timing() -> ObservationTiming:
    return ObservationTiming(
        observation_id="trend_strength", decision_time=T0, feature_available_at=T0
    )


def _clean_survivorship() -> SurvivorshipReport:
    return SurvivorshipReport(
        tested_universe_size=2, disappeared_in_window=0, excluded_from_universe=0
    )


def _order(**overrides: Any) -> PreTradeOrder:
    params: dict[str, Any] = {
        "client_order_id": "ord-001",
        "strategy_id": "momentum-1",
        "strategy_version": "v1",
        "instrument_id": "inst-acme",
        "ticker": "ACME",
        "mic": "XNYS",
        "quantity": 5.0,
        "price": 10.0,
        "venue": "paper",
        "actor": "c5-execution",
    }
    params.update(overrides)
    return PreTradeOrder(**params)


def _issue_for(order: PreTradeOrder, *, max_quantity: float = 10.0, max_notional: float = 90.0):
    return issue(
        strategy_id=order.strategy_id,
        strategy_version=order.strategy_version,
        client_order_id=order.client_order_id,
        instrument_id=order.instrument_id,
        max_quantity=max_quantity,
        max_notional_usd=max_notional,
        issuer="capital-firewall",
        secret=SEAL_A,
        issued_at=T0,
        ttl_seconds=300.0,
        envelope_id=f"env-{order.client_order_id}",
    )


def _firewall(
    *,
    master: StubMaster | None = None,
    oracle: StubOracle | None = None,
    max_exposure: float = 100.0,
) -> CapitalFirewall:
    return CapitalFirewall(
        master=master or StubMaster(),
        oracle=oracle or StubOracle(),
        max_exposure_usd=max_exposure,
    )


def _evaluate(order: PreTradeOrder, firewall: CapitalFirewall, **overrides: Any) -> FirewallDecision:
    params: dict[str, Any] = {
        "order": order,
        "envelope": _issue_for(order),
        "secret": SEAL_A,
        "now": NOW,
        "timings": [_clean_timing()],
        "survivorship": _clean_survivorship(),
    }
    params.update(overrides)
    return firewall.evaluate(**params)  # type: ignore[arg-type]


def _names(decision: FirewallDecision) -> str:
    return " ".join([*decision.failed_checks, *decision.reasons])


# ══════════════════════════════════════════════════════════════════════════
# The honest path
# ══════════════════════════════════════════════════════════════════════════


def test_a_fully_passing_order_approves() -> None:
    """The firewall must not halt honest flow, or operators will route around it."""
    decision = _evaluate(_order(), _firewall())
    assert decision.decision == "APPROVE"
    assert decision.failed_checks == []
    assert decision.approved_quantity == 5.0
    assert decision.notional_usd == 50.0


def test_the_check_registry_names_all_fifteen() -> None:
    """A check without a stable name cannot be cited in a refusal."""
    assert len(CHECK_NAMES) == 15
    assert len(set(CHECK_NAMES)) == 15


# ══════════════════════════════════════════════════════════════════════════
# Checks 1–3: the envelope itself
# ══════════════════════════════════════════════════════════════════════════


def test_missing_envelope_is_refused_as_a_signature_failure() -> None:
    """An order with no permission is not an order with a small permission."""
    decision = _evaluate(_order(), _firewall(), envelope=None)
    assert decision.decision == "REJECT"
    assert "envelope_signature" in _names(decision)


def test_a_forged_envelope_is_refused_and_names_the_check() -> None:
    """Execution cannot mint its own permission by editing an issued envelope."""
    order = _order()
    forged = _issue_for(order).model_copy(update={"max_quantity": 999.0})
    decision = _evaluate(order, _firewall(), envelope=forged)
    assert decision.decision == "REJECT"
    assert "envelope_signature" in _names(decision)


def test_an_expired_envelope_is_refused_and_names_the_check() -> None:
    """A permission that outlives its TTL is a standing permission, not an expiry."""
    order = _order()
    decision = _evaluate(
        order, _firewall(), now=T0 + timedelta(seconds=3600)
    )
    assert decision.decision == "REJECT"
    assert "envelope_expiry" in _names(decision)


def test_replay_across_instruments_is_refused_as_a_scope_failure() -> None:
    """An envelope for one instrument authorizes nothing about another."""
    order = _order(instrument_id="inst-other", ticker="OTHER")
    envelope_for_acme = _issue_for(_order())
    decision = _evaluate(order, _firewall(), envelope=envelope_for_acme)
    assert decision.decision == "REJECT"
    assert "envelope_scope" in _names(decision)


def test_quantity_beyond_the_envelope_reduces_not_rejects() -> None:
    """Trading less than authorized is obedience; the firewall says how much less."""
    order = _order(quantity=12.0, price=5.0)
    envelope = _issue_for(order)
    decision = _evaluate(order, _firewall(), envelope=envelope)
    assert decision.decision == "REDUCE"
    assert "envelope_scope" in _names(decision)
    assert decision.approved_quantity == 10.0
    assert decision.reduced_envelope is not None
    assert decision.reduced_envelope.verify(SEAL_A) is True


# ══════════════════════════════════════════════════════════════════════════
# Checks 4–5: sizing
# ══════════════════════════════════════════════════════════════════════════


def test_notional_beyond_the_constitutional_cap_reduces() -> None:
    """The ratified $100 micro-live cap is enforced by arithmetic, not by policy text."""
    order = _order(quantity=5.0, price=30.0)
    envelope = _issue_for(order, max_quantity=50.0, max_notional=500.0)
    decision = _evaluate(order, _firewall(max_exposure=1000.0), envelope=envelope)
    assert decision.decision == "REDUCE"
    assert "notional_cap" in _names(decision)
    assert decision.approved_quantity < order.quantity
    assert decision.notional_usd <= 100.0


def test_a_non_positive_price_is_rejected_under_the_cap_check() -> None:
    """A notional that cannot be valued cannot be capped; the order is refused."""
    decision = _evaluate(_order(price=0.0), _firewall())
    assert decision.decision == "REJECT"
    assert "notional_cap" in _names(decision)


def test_a_non_positive_quantity_is_rejected_under_the_lot_check() -> None:
    """Zero or negative size is not a trade waiting to be rounded."""
    decision = _evaluate(_order(quantity=0.0), _firewall())
    assert decision.decision == "REJECT"
    assert "quantity_lot" in _names(decision)


def test_non_lot_compliant_quantity_rounds_down_only() -> None:
    """Rounding up would authorize size nobody approved; the floor is the only option."""
    master = StubMaster(lots={"inst-acme": Decimal("5")})
    order = _order(quantity=12.0, price=5.0)
    envelope = _issue_for(order, max_quantity=20.0, max_notional=500.0)
    decision = _evaluate(order, _firewall(master=master, max_exposure=1000.0), envelope=envelope)
    assert decision.decision == "REDUCE"
    assert "quantity_lot" in _names(decision)
    assert decision.approved_quantity == 10.0


# ══════════════════════════════════════════════════════════════════════════
# Checks 6–7: the instrument must be real and alive
# ══════════════════════════════════════════════════════════════════════════


def test_an_unresolvable_ticker_is_refused() -> None:
    """A symbol the master never heard of is not a tradeable instrument."""
    decision = _evaluate(_order(ticker="NOPE"), _firewall())
    assert decision.decision == "REJECT"
    assert "instrument_resolves" in _names(decision)


def test_a_ticker_reused_for_another_issuer_is_refused() -> None:
    """A reused ticker splicing two issuers into one series must not trade."""
    decision = _evaluate(_order(instrument_id="inst-impostor"), _firewall())
    assert decision.decision == "REJECT"
    assert "instrument_resolves" in _names(decision)


def test_a_delisted_instrument_is_refused_even_when_it_resolves() -> None:
    """A delisted row that still resolves is exactly the row that must not pass."""
    master = StubMaster(delisted=("inst-acme",))
    decision = _evaluate(_order(), _firewall(master=master))
    assert decision.decision == "REJECT"
    assert "instrument_live" in _names(decision)


# ══════════════════════════════════════════════════════════════════════════
# Checks 8–10: certification, time, and universe honesty
# ══════════════════════════════════════════════════════════════════════════


def test_an_uncertified_strategy_is_refused() -> None:
    """Capital must not move for a strategy whose verdict was revoked."""
    decision = _evaluate(_order(), _firewall(oracle=StubOracle(certified=False)))
    assert decision.decision == "REJECT"
    assert "strategy_certified" in _names(decision)


def test_a_feature_from_the_future_is_refused() -> None:
    """A decision built on unknowable inputs is wrong under every policy."""
    timing = ObservationTiming(
        observation_id="trend_strength",
        decision_time=T0,
        feature_available_at=T0 + timedelta(hours=1),
    )
    decision = _evaluate(_order(), _firewall(), timings=[timing])
    assert decision.decision == "REJECT"
    assert "no_look_ahead" in _names(decision)


def test_a_survivorship_biased_universe_is_refused() -> None:
    """A result produced on survivors must not authorize live capital."""
    dirty = SurvivorshipReport(
        tested_universe_size=2, disappeared_in_window=1, excluded_from_universe=1
    )
    decision = _evaluate(_order(), _firewall(), survivorship=dirty)
    assert decision.decision == "REJECT"
    assert "survivorship_clean" in _names(decision)


def test_a_missing_survivorship_report_is_refused() -> None:
    """A detector that never ran is not a detector that found nothing."""
    decision = _evaluate(_order(), _firewall(), survivorship=None)
    assert decision.decision == "REJECT"
    assert "survivorship_clean" in _names(decision)


# ══════════════════════════════════════════════════════════════════════════
# Checks 11–15: limits, venue, uniqueness, actor
# ══════════════════════════════════════════════════════════════════════════


def test_a_breached_daily_loss_limit_halts() -> None:
    """The loss halt is a halt: no smaller size repairs a blown day."""
    decision = _evaluate(_order(), _firewall(), daily_loss_pct=3.0)
    assert decision.decision == "REJECT"
    assert "daily_loss_limit" in _names(decision)


def test_exposure_beyond_the_strategy_limit_reduces() -> None:
    """Exposure is a sizing question, so the firewall answers with a size."""
    order = _order(quantity=5.0, price=10.0)
    envelope = _issue_for(order, max_quantity=20.0, max_notional=500.0)
    decision = _evaluate(order, _firewall(), envelope=envelope, current_exposure_usd=90.0)
    assert decision.decision == "REDUCE"
    assert "strategy_exposure" in _names(decision)
    assert decision.approved_quantity == 1.0


def test_an_unlisted_venue_is_refused() -> None:
    """An order routed somewhere ungoverned is not an order the firewall saw."""
    decision = _evaluate(_order(venue="dark-pool"), _firewall())
    assert decision.decision == "REJECT"
    assert "venue_allowlist" in _names(decision)


def test_a_replayed_client_order_id_is_refused() -> None:
    """Re-submitting an id must not create a second order's worth of capital."""
    decision = _evaluate(_order(), _firewall(), seen_order_ids={"ord-001"})
    assert decision.decision == "REJECT"
    assert "order_uniqueness" in _names(decision)


def test_an_unauthorized_actor_is_refused() -> None:
    """A caller outside the allowlist cannot spend the strategy's permission."""
    decision = _evaluate(_order(actor="intruder"), _firewall())
    assert decision.decision == "REJECT"
    assert "actor_authorized" in _names(decision)


# ══════════════════════════════════════════════════════════════════════════
# Reduction discipline
# ══════════════════════════════════════════════════════════════════════════


def test_reduction_never_increases_quantity_or_notional() -> None:
    """A REDUCE verdict that widens anything is an escalation wearing a reduction."""
    cases = [
        (_order(quantity=5.0, price=30.0), {"max_exposure": 1000.0}, (50.0, 500.0)),
        (_order(quantity=12.0, price=5.0), {}, (10.0, 90.0)),
    ]
    for order, fw_kwargs, (env_qty, env_notional) in cases:
        envelope = _issue_for(order, max_quantity=env_qty, max_notional=env_notional)
        decision = _evaluate(order, _firewall(**fw_kwargs), envelope=envelope)
        assert decision.decision == "REDUCE"
        assert 0 < decision.approved_quantity < order.quantity
        assert decision.reduced_envelope is not None
        assert decision.reduced_envelope.max_quantity <= envelope.max_quantity
        assert decision.reduced_envelope.max_notional_usd <= envelope.max_notional_usd
        assert decision.reduced_envelope.verify(SEAL_A) is True


def test_a_reduced_envelope_still_covers_the_reduced_trade() -> None:
    """The narrowed permission must authorize exactly the size it carries."""
    order = _order(quantity=5.0, price=30.0)
    envelope = _issue_for(order, max_quantity=50.0, max_notional=500.0)
    decision = _evaluate(order, _firewall(max_exposure=1000.0), envelope=envelope)
    assert decision.decision == "REDUCE"
    assert decision.reduced_envelope is not None
    assert decision.approved_quantity <= decision.reduced_envelope.max_quantity
    assert decision.notional_usd <= decision.reduced_envelope.max_notional_usd + 1e-9
