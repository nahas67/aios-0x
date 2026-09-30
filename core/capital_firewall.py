"""Deterministic pre-trade capital firewall (vNext goal G140).

The strategy firewall asks whether a strategy may trade. This module asks
whether *this order* may trade, through fifteen named checks evaluated in a
fixed order, and seals the answer in an
:class:`~core.authorization.AuthorizationEnvelope` that execution can check
but cannot mint: the only minting path is :func:`issue` here, which takes the
HMAC secret as an explicit argument and never reads it from anywhere else.

Verdicts:

* ``APPROVE`` — every check passed; the order trades as proposed.
* ``REDUCE`` — only sizing checks failed and a smaller quantity satisfies
  them all; the verdict carries the reduced quantity and a narrowed envelope.
* ``REJECT`` — anything else failed; no smaller size repairs a forged
  signature, an expired permission, a delisted instrument, a revoked
  certification, a leak from the future, or a missing identity.

Every refusal names the check that failed, so a rejection is auditable
without re-running the evaluation. Enforced by
``tests/test_capital_firewall.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from core.authorization import AuthorizationEnvelope
from core.contamination import ObservationTiming, SurvivorshipReport
from core.security_master import InstrumentIdentity

__all__ = [
    "CHECK_ACTOR_AUTHORIZED",
    "CHECK_DAILY_LOSS_LIMIT",
    "CHECK_ENVELOPE_EXPIRY",
    "CHECK_ENVELOPE_SCOPE",
    "CHECK_ENVELOPE_SIGNATURE",
    "CHECK_INSTRUMENT_LIVE",
    "CHECK_INSTRUMENT_RESOLVES",
    "CHECK_NAMES",
    "CHECK_NO_LOOK_AHEAD",
    "CHECK_NOTIONAL_CAP",
    "CHECK_ORDER_UNIQUENESS",
    "CHECK_QUANTITY_LOT",
    "CHECK_STRATEGY_CERTIFIED",
    "CHECK_STRATEGY_EXPOSURE",
    "CHECK_SURVIVORSHIP_CLEAN",
    "CHECK_VENUE_ALLOWLIST",
    "MICRO_LIVE_NOTIONAL_CAP_USD",
    "CapitalFirewall",
    "CertificationOracle",
    "FirewallDecision",
    "PreTradeOrder",
    "SecurityMasterReader",
    "issue",
]

#: Ratified constitutional micro-live cap (CONSTITUTION.md section 1).
#: Mirrors ``CcxtExecutionAdapter.MAX_ORDER_NOTIONAL_USD``. Lowering is a
#: policy change; raising requires a ratified amendment — never raise it here.
MICRO_LIVE_NOTIONAL_CAP_USD = 100.0

CHECK_ENVELOPE_SIGNATURE = "envelope_signature"
CHECK_ENVELOPE_EXPIRY = "envelope_expiry"
CHECK_ENVELOPE_SCOPE = "envelope_scope"
CHECK_NOTIONAL_CAP = "notional_cap"
CHECK_QUANTITY_LOT = "quantity_lot"
CHECK_INSTRUMENT_RESOLVES = "instrument_resolves"
CHECK_INSTRUMENT_LIVE = "instrument_live"
CHECK_STRATEGY_CERTIFIED = "strategy_certified"
CHECK_NO_LOOK_AHEAD = "no_look_ahead"
CHECK_SURVIVORSHIP_CLEAN = "survivorship_clean"
CHECK_DAILY_LOSS_LIMIT = "daily_loss_limit"
CHECK_STRATEGY_EXPOSURE = "strategy_exposure"
CHECK_VENUE_ALLOWLIST = "venue_allowlist"
CHECK_ORDER_UNIQUENESS = "order_uniqueness"
CHECK_ACTOR_AUTHORIZED = "actor_authorized"

CHECK_NAMES: tuple[str, ...] = (
    CHECK_ENVELOPE_SIGNATURE,
    CHECK_ENVELOPE_EXPIRY,
    CHECK_ENVELOPE_SCOPE,
    CHECK_NOTIONAL_CAP,
    CHECK_QUANTITY_LOT,
    CHECK_INSTRUMENT_RESOLVES,
    CHECK_INSTRUMENT_LIVE,
    CHECK_STRATEGY_CERTIFIED,
    CHECK_NO_LOOK_AHEAD,
    CHECK_SURVIVORSHIP_CLEAN,
    CHECK_DAILY_LOSS_LIMIT,
    CHECK_STRATEGY_EXPOSURE,
    CHECK_VENUE_ALLOWLIST,
    CHECK_ORDER_UNIQUENESS,
    CHECK_ACTOR_AUTHORIZED,
)


class CertificationOracle(Protocol):
    """Answers "is this strategy certified right now" — live, not snapshotted.

    A ``Protocol`` rather than a registry import, mirroring
    ``kernel.playbook.CertificationOracle``: the firewall depends on the
    question, and a test can supply an oracle that revokes on demand.
    """

    def verdict_for(self, strategy_id: str, strategy_version: str) -> Any | None:
        """The current verdict, or ``None`` when there is none."""
        ...  # pragma: no cover - protocol surface

    def is_certified(self, strategy_id: str, strategy_version: str) -> bool:
        """Whether that strategy may currently be traded."""
        ...  # pragma: no cover - protocol surface


class SecurityMasterReader(Protocol):
    """The two temporal reads the firewall needs, nothing more.

    ``resolve`` is the trading-path lookup (ticker reuse across issuers must
    not splice two companies into one series); ``as_of`` is the point-in-time
    truth (a delisted row must not pass). :class:`InstrumentIdentity.is_live`
    decides tradeability on the returned row.
    """

    def resolve(self, ticker: str, mic: str) -> InstrumentIdentity | None:
        """Current identity for a ticker on a venue, if any."""
        ...  # pragma: no cover - protocol surface

    def as_of(self, instrument_id: str, moment: datetime) -> InstrumentIdentity | None:
        """The instrument as it truly was at ``moment``, if any."""
        ...  # pragma: no cover - protocol surface


class PreTradeOrder(BaseModel):
    """The order as proposed, before the firewall authorizes it.

    Bounds are deliberately absent: quantity and price are claims until the
    fifteen checks below rule on them. A field that fails a check fails the
    order with that check's name rather than failing construction, so every
    refusal is attributable.
    """

    model_config = {"frozen": True}

    client_order_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    strategy_version: str = Field(..., min_length=1)
    instrument_id: str = Field(..., min_length=1)
    ticker: str = Field(..., min_length=1)
    mic: str = Field(..., min_length=1)
    quantity: float = Field(...)
    price: float = Field(...)
    venue: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)


class FirewallDecision(BaseModel):
    """The firewall's answer, with the evidence behind it.

    ``failed_checks`` names each check that failed; each entry of ``reasons``
    starts with its check name. A ``REDUCE`` verdict carries the feasible
    quantity and a narrowed envelope sealed for exactly that size.
    """

    model_config = {"frozen": True}

    decision: Literal["APPROVE", "REDUCE", "REJECT"]
    failed_checks: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    requested_quantity: float = Field(default=0.0)
    approved_quantity: float = Field(default=0.0)
    notional_usd: float = Field(default=0.0)
    reduced_envelope: AuthorizationEnvelope | None = None


def _reason(check: str, detail: str) -> str:
    return f"{check}: {detail}"


def _floor_to_lot(quantity: float, lot_size: Decimal) -> float:
    """Round ``quantity`` down to a whole multiple of ``lot_size``.

    Down only: rounding up would authorize size nobody approved, which is the
    direction the execution plane is forbidden from moving.
    """
    if lot_size <= 0:
        return quantity
    try:
        steps = int((Decimal(str(quantity)) / lot_size).to_integral_value(rounding="ROUND_FLOOR"))
    except (InvalidOperation, ValueError):
        return 0.0
    if steps <= 0:
        return 0.0
    return float(Decimal(steps) * lot_size)


def _is_lot_compliant(quantity: float, lot_size: Decimal | None) -> bool:
    if lot_size is None or lot_size <= 0:
        return True
    try:
        ratio = Decimal(str(quantity)) / lot_size
    except (InvalidOperation, ValueError):
        return False
    return ratio == ratio.to_integral_value()


def issue(
    *,
    strategy_id: str,
    strategy_version: str,
    client_order_id: str,
    instrument_id: str,
    max_quantity: float,
    max_notional_usd: float,
    issuer: str,
    secret: str,
    issued_at: datetime | None = None,
    ttl_seconds: float,
    envelope_id: str | None = None,
) -> AuthorizationEnvelope:
    """Mint a sealed authorization envelope. The firewall's only minting path.

    The secret arrives as an explicit argument and is never read from the
    environment here, so key custody stays with the caller and no
    agent-reachable path can mint by accident. Execution cannot call this
    without the secret, and without a valid signature an envelope never
    passes :data:`CHECK_ENVELOPE_SIGNATURE`.
    """
    if max_quantity <= 0:
        raise ValueError("max_quantity must be positive")
    if max_notional_usd <= 0:
        raise ValueError("max_notional_usd must be positive")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    if not secret:
        raise ValueError("a secret is required to seal the envelope")
    moment = issued_at if issued_at is not None else datetime.now(UTC)
    candidate = AuthorizationEnvelope(
        envelope_id=envelope_id or f"env-{uuid.uuid4().hex[:12]}",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        client_order_id=client_order_id,
        instrument_id=instrument_id,
        max_quantity=max_quantity,
        max_notional_usd=max_notional_usd,
        issued_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
        issuer=issuer,
        signature="placeholder",
    )
    sealed = candidate.model_copy(
        update={"signature": AuthorizationEnvelope._sign(candidate.canonical_payload(), secret)}
    )
    return sealed


class CapitalFirewall:
    """Fifteen named pre-trade checks with APPROVE / REDUCE / REJECT verdicts."""

    def __init__(
        self,
        *,
        master: SecurityMasterReader,
        oracle: CertificationOracle,
        venue_allowlist: Collection[str] = frozenset({"paper"}),
        actor_allowlist: Collection[str] = frozenset({"c5-execution"}),
        daily_loss_limit_pct: float = 3.0,
        max_exposure_usd: float = 100.0,
    ) -> None:
        self._master = master
        self._oracle = oracle
        self._venues = set(venue_allowlist)
        self._actors = set(actor_allowlist)
        self._daily_loss_limit_pct = daily_loss_limit_pct
        self._max_exposure_usd = max_exposure_usd

    def evaluate(
        self,
        *,
        order: PreTradeOrder,
        envelope: AuthorizationEnvelope | None,
        secret: str,
        now: datetime,
        timings: Sequence[ObservationTiming] = (),
        survivorship: SurvivorshipReport | None = None,
        daily_loss_pct: float = 0.0,
        current_exposure_usd: float = 0.0,
        seen_order_ids: Collection[str] = frozenset(),
    ) -> FirewallDecision:
        """Run the fifteen checks and return the verdict.

        ``now`` is an explicit argument rather than a clock read so the
        verdict is a pure function of its inputs. ``seen_order_ids`` is read,
        never mutated: the caller records an approved id after acting on it.
        """
        hard: list[str] = []
        sizing: list[str] = []

        def fail(check: str, detail: str, to: list[str]) -> None:
            to.append(_reason(check, detail))

        # ── 1. envelope present and signature valid ──────────────────────
        envelope_ok = False
        if envelope is None:
            fail(
                CHECK_ENVELOPE_SIGNATURE,
                "no authorization envelope accompanied the order",
                hard,
            )
        elif not secret:
            fail(CHECK_ENVELOPE_SIGNATURE, "no HMAC secret supplied for verification", hard)
        elif not envelope.verify(secret):
            fail(
                CHECK_ENVELOPE_SIGNATURE,
                f"envelope {envelope.envelope_id!r} signature does not verify",
                hard,
            )
        else:
            envelope_ok = True

        # ── 2. envelope unexpired ────────────────────────────────────────
        if envelope is None:
            fail(CHECK_ENVELOPE_EXPIRY, "no envelope to check expiry against", hard)
        else:
            try:
                expired = now > envelope.expires_at
            except TypeError:
                fail(
                    CHECK_ENVELOPE_EXPIRY,
                    "envelope expiry is not comparable to the decision time",
                    hard,
                )
                expired = True
            if expired:
                fail(
                    CHECK_ENVELOPE_EXPIRY,
                    f"envelope {envelope.envelope_id!r} expired at "
                    f"{envelope.expires_at.isoformat()}",
                    hard,
                )

        # ── 6. instrument resolves (before scope: scope needs the identity) ─
        resolved: InstrumentIdentity | None = None
        try:
            resolved = self._master.resolve(order.ticker, order.mic)
        except Exception as exc:  # noqa: BLE001 - unreadable identity fails closed
            fail(
                CHECK_INSTRUMENT_RESOLVES,
                f"security master read failed for {order.ticker!r} on {order.mic!r}: {exc}",
                hard,
            )
        if resolved is None and not any(r.startswith(CHECK_INSTRUMENT_RESOLVES) for r in hard):
            fail(
                CHECK_INSTRUMENT_RESOLVES,
                f"{order.ticker!r} on {order.mic!r} resolves to nothing",
                hard,
            )
        elif resolved is not None and resolved.instrument_id != order.instrument_id:
            fail(
                CHECK_INSTRUMENT_RESOLVES,
                f"order claims {order.instrument_id!r} but {order.ticker!r} on "
                f"{order.mic!r} currently resolves to {resolved.instrument_id!r}; "
                "a reused ticker must not splice two issuers into one series",
                hard,
            )

        # ── 7. instrument is_live at the decision time ───────────────────
        live: InstrumentIdentity | None = None
        try:
            live = self._master.as_of(order.instrument_id, now)
        except Exception as exc:  # noqa: BLE001 - unreadable identity fails closed
            fail(
                CHECK_INSTRUMENT_LIVE,
                f"point-in-time read failed for {order.instrument_id!r}: {exc}",
                hard,
            )
        if live is None and not any(r.startswith(CHECK_INSTRUMENT_LIVE) for r in hard):
            fail(
                CHECK_INSTRUMENT_LIVE,
                f"{order.instrument_id!r} has no point-in-time identity at the decision time",
                hard,
            )
        elif live is not None and not live.is_live:
            fail(
                CHECK_INSTRUMENT_LIVE,
                f"{order.instrument_id!r} is {live.status} at the decision time; "
                "only ACTIVE instruments trade",
                hard,
            )

        # ── 3. envelope scope matches the order ──────────────────────────
        if envelope is not None:
            if (
                envelope.instrument_id != order.instrument_id
                or envelope.strategy_id != order.strategy_id
                or envelope.strategy_version != order.strategy_version
                or envelope.client_order_id != order.client_order_id
            ):
                fail(
                    CHECK_ENVELOPE_SCOPE,
                    f"envelope {envelope.envelope_id!r} authorizes "
                    f"{envelope.strategy_id}:{envelope.strategy_version} "
                    f"{envelope.instrument_id}/{envelope.client_order_id}, not "
                    f"{order.strategy_id}:{order.strategy_version} "
                    f"{order.instrument_id}/{order.client_order_id}",
                    hard,
                )
            else:
                if order.quantity > envelope.max_quantity:
                    fail(
                        CHECK_ENVELOPE_SCOPE,
                        f"quantity {order.quantity:g} exceeds authorized "
                        f"{envelope.max_quantity:g}",
                        sizing,
                    )
                if order.price > 0 and order.quantity * order.price > envelope.max_notional_usd:
                    fail(
                        CHECK_ENVELOPE_SCOPE,
                        f"notional {order.quantity * order.price:.2f} exceeds authorized "
                        f"{envelope.max_notional_usd:.2f}",
                        sizing,
                    )

        # ── 4. constitutional micro-live notional cap ────────────────────
        price_ok = order.price > 0
        if not price_ok:
            fail(
                CHECK_NOTIONAL_CAP,
                f"price {order.price!r} is not positive, so the notional cannot be valued",
                hard,
            )
        requested_notional = order.quantity * order.price if price_ok else 0.0
        if price_ok and requested_notional > MICRO_LIVE_NOTIONAL_CAP_USD:
            fail(
                CHECK_NOTIONAL_CAP,
                f"notional {requested_notional:.2f} exceeds the constitutional "
                f"micro-live cap {MICRO_LIVE_NOTIONAL_CAP_USD:.2f}",
                sizing,
            )

        # ── 5. quantity positive and lot-size compliant (down only) ──────
        lot_size = resolved.lot_size if resolved is not None else None
        if order.quantity <= 0:
            fail(
                CHECK_QUANTITY_LOT,
                f"quantity {order.quantity!r} is not positive",
                hard,
            )
        elif lot_size is not None and not _is_lot_compliant(order.quantity, lot_size):
            floored = _floor_to_lot(order.quantity, lot_size)
            fail(
                CHECK_QUANTITY_LOT,
                f"quantity {order.quantity:g} is not a whole multiple of lot size "
                f"{lot_size}; the largest compliant size below it is {floored:g}",
                sizing,
            )

        # ── 8. strategy verdict certified, asked live ────────────────────
        try:
            certified = self._oracle.is_certified(order.strategy_id, order.strategy_version)
        except Exception as exc:  # noqa: BLE001 - unreadable verdict fails closed
            fail(
                CHECK_STRATEGY_CERTIFIED,
                f"certification read failed for "
                f"{order.strategy_id}:{order.strategy_version}: {exc}",
                hard,
            )
            certified = False
        if not certified and not any(r.startswith(CHECK_STRATEGY_CERTIFIED) for r in hard):
            fail(
                CHECK_STRATEGY_CERTIFIED,
                f"{order.strategy_id}:{order.strategy_version} is not certified right now",
                hard,
            )

        # ── 9. no look-ahead in the decision's inputs ────────────────────
        contaminated = [t for t in timings if t.is_contaminated()]
        if contaminated:
            first = contaminated[0]
            fail(
                CHECK_NO_LOOK_AHEAD,
                f"{len(contaminated)} input(s) were not knowable at decision time; "
                f"first: {first.observation_id!r}",
                hard,
            )

        # ── 10. universe survivorship (precomputed report, never recomputed) ─
        if survivorship is None:
            fail(
                CHECK_SURVIVORSHIP_CLEAN,
                "no survivorship report was supplied; a detector that never ran "
                "is not a detector that found nothing",
                hard,
            )
        elif not survivorship.clean:
            fail(
                CHECK_SURVIVORSHIP_CLEAN,
                f"universe excludes {survivorship.excluded_from_universe} of "
                f"{survivorship.disappeared_in_window} instrument(s) that left "
                "during the window; the result was produced on survivors",
                hard,
            )

        # ── 11. daily loss limit halts, it does not scale down ───────────
        if daily_loss_pct >= self._daily_loss_limit_pct:
            fail(
                CHECK_DAILY_LOSS_LIMIT,
                f"daily loss {daily_loss_pct:.2f}% reached the "
                f"{self._daily_loss_limit_pct:.2f}% halt",
                hard,
            )

        # ── 12. per-strategy exposure limit ──────────────────────────────
        if price_ok and current_exposure_usd + requested_notional > self._max_exposure_usd:
            remaining = self._max_exposure_usd - current_exposure_usd
            fail(
                CHECK_STRATEGY_EXPOSURE,
                f"exposure {current_exposure_usd:.2f} plus notional "
                f"{requested_notional:.2f} exceeds the {self._max_exposure_usd:.2f} "
                f"strategy limit; {remaining:.2f} remains",
                sizing,
            )

        # ── 13. venue allowlist ──────────────────────────────────────────
        if order.venue not in self._venues:
            fail(
                CHECK_VENUE_ALLOWLIST,
                f"venue {order.venue!r} is not in the allowlist {sorted(self._venues)}",
                hard,
            )

        # ── 14. client-order-id uniqueness ───────────────────────────────
        if order.client_order_id in seen_order_ids:
            fail(
                CHECK_ORDER_UNIQUENESS,
                f"client order id {order.client_order_id!r} was already seen; "
                "a replay is not a new order",
                hard,
            )

        # ── 15. actor authorized ─────────────────────────────────────────
        if order.actor not in self._actors:
            fail(
                CHECK_ACTOR_AUTHORIZED,
                f"actor {order.actor!r} is not in the allowlist {sorted(self._actors)}",
                hard,
            )

        if hard:
            return FirewallDecision(
                decision="REJECT",
                failed_checks=sorted({r.split(":")[0] for r in hard}),
                reasons=hard + sizing,
                requested_quantity=order.quantity,
                approved_quantity=0.0,
                notional_usd=round(requested_notional, 2),
                reduced_envelope=None,
            )

        if sizing and price_ok:
            feasible = order.quantity
            if envelope is not None and envelope_ok:
                feasible = min(feasible, envelope.max_quantity)
                feasible = min(feasible, envelope.max_notional_usd / order.price)
            feasible = min(feasible, MICRO_LIVE_NOTIONAL_CAP_USD / order.price)
            remaining_exposure = self._max_exposure_usd - current_exposure_usd
            feasible = min(feasible, remaining_exposure / order.price)
            if lot_size is not None:
                feasible = _floor_to_lot(feasible, lot_size)
            feasible = round(feasible, 10)
            if feasible <= 0:
                return FirewallDecision(
                    decision="REJECT",
                    failed_checks=sorted({r.split(":")[0] for r in sizing}),
                    reasons=sizing,
                    requested_quantity=order.quantity,
                    approved_quantity=0.0,
                    notional_usd=round(requested_notional, 2),
                    reduced_envelope=None,
                )
            if feasible < order.quantity:
                narrowed: AuthorizationEnvelope | None = None
                if envelope is not None and envelope_ok:
                    narrowed = envelope.apply_reduction(
                        max_quantity=feasible,
                        max_notional_usd=min(feasible * order.price, envelope.max_notional_usd),
                        secret=secret,
                    )
                return FirewallDecision(
                    decision="REDUCE",
                    failed_checks=sorted({r.split(":")[0] for r in sizing}),
                    reasons=sizing,
                    requested_quantity=order.quantity,
                    approved_quantity=feasible,
                    notional_usd=round(feasible * order.price, 2),
                    reduced_envelope=narrowed,
                )

        if sizing:
            return FirewallDecision(
                decision="REJECT",
                failed_checks=sorted({r.split(":")[0] for r in sizing}),
                reasons=sizing,
                requested_quantity=order.quantity,
                approved_quantity=0.0,
                notional_usd=round(requested_notional, 2),
                reduced_envelope=None,
            )

        return FirewallDecision(
            decision="APPROVE",
            failed_checks=[],
            reasons=[],
            requested_quantity=order.quantity,
            approved_quantity=order.quantity,
            notional_usd=round(requested_notional, 2),
            reduced_envelope=None,
        )
