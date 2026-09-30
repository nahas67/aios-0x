"""Bitemporal instrument identity and corporate actions (vNext goal G020).

Every other layer in the system treats a symbol as a string. That is the
weakest link in the whole architecture, and it is weak in a specific way: a
ticker is not an identity. ``ABC`` was American Bancorp and is now a different
company on a different exchange with a different currency. ``ES`` is a futures
contract in one venue and an index in another. A symbol reused after a
delisting silently splices two issuers into one price series, and every
backtest built on that series is wrong in a way no downstream check can see.

This module is the answer, and it is bitemporal for a reason. There are two
independent questions a financial system asks about identity:

``as_of(t)``
    What did this instrument look like at time ``t``? A *valid-time* question.
    Answers: was the ticker ``ABC`` listed in 1998, and under which exchange?

``as_known(t)``
    What did *we believe* about this instrument at time ``t``? A *transaction-
    time* question. Answers: when did we first learn about the 2003 reverse
    split, and what did our database claim before we learned it?

Storing only the first is the classic bitemporal mistake. It is enough to
answer a research query and not enough to answer an audit one, and the audit
question is the one that has to survive a regulator. Both intervals are
therefore stored, and both query paths are first-class.

The CorporateActionEngine exists for the same reason from the other direction.
A price series without action adjustment is wrong at every split boundary, and
the error is invisible in a chart because the chart is drawn on the same
unadjusted series. The adjustment factors are replayable from stored events
rather than baked in, so a corrected ratio produces a corrected history instead
of an unexplainable one.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

__all__ = [
    "ActionType",
    "AssetClass",
    "CorporateAction",
    "CorporateActionEngine",
    "IdentityConflict",
    "InstrumentIdentity",
    "InstrumentStatus",
    "SecurityMaster",
    "SecurityMasterStore",
]


class AssetClass(StrEnum):
    """The coarse instrument taxonomy.

    Deliberately small. A taxonomy with one member per exotic derivative is a
    taxonomy nobody maintains, and an unmaintained taxonomy eventually admits
    a fixture that silently mismatches.
    """

    EQUITY = "EQUITY"
    ETF = "ETF"
    INDEX = "INDEX"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    FX = "FX"
    CRYPTO = "CRYPTO"
    BOND = "BOND"
    FUND = "FUND"


class InstrumentStatus(StrEnum):
    """Lifecycle state at a point in time.

    ``DELISTED`` and ``SUSPENDED`` are distinct because they mean opposite
    things operationally: a delisted instrument can never trade again, while a
    suspended one resumes. Collapsing them loses the ability to distinguish a
    permanently dead position from a temporarily frozen one.
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"
    PENDING = "PENDING"


class ActionType(StrEnum):
    """Corporate actions the engine can replay."""

    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    MERGER = "MERGER"
    SPINOFF = "SPINOFF"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    DELISTING = "DELISTING"
    FUTURES_ADJUSTMENT = "FUTURES_ADJUSTMENT"
    OPTIONS_ADJUSTMENT = "OPTIONS_ADJUSTMENT"


def _dec(value: Any) -> Decimal | None:
    """Coerce to Decimal without going through binary float.

    Prices and share ratios are exact quantities. Routing them through float
    introduces error that compounds across a chain of splits, so every
    monetary and ratio field in this module is Decimal from ingestion onward.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class InstrumentIdentity(BaseModel):
    """One bitemporal version of one instrument on one venue.

    ``valid_from``/``valid_to`` bracket *when this description was true of the
    world*. ``recorded_from``/``recorded_to`` bracket *when this description was
    true of our database*. A record that has been superseded is not deleted: its
    ``recorded_to`` is set and it remains queryable, because an audit needs to
    see what the system believed at the time, not only what it believes now.

    ``instrument_id`` is the stable identity and never a ticker. ``listing_id``
    is the venue-specific listing, so one issuer traded on four venues has four
    listings and one identity.
    """

    model_config = {"frozen": True}

    instrument_id: str = Field(..., min_length=1, description="Stable identity, never a ticker")
    listing_id: str = Field(..., min_length=1, description="Venue-specific listing identity")
    ticker: str = Field(..., min_length=1)
    mic: str = Field(..., min_length=1, description="ISO 10383 Market Identifier Code")
    venue: str = Field(..., min_length=1)
    asset_class: AssetClass
    security_type: str = Field(default="COMMON", description="COMMON, ETF, FUTURE, CALL, ...")
    currency: str = Field(..., min_length=3, max_length=3, description="Trading currency")
    quote_currency: str | None = Field(
        default=None, min_length=3, max_length=3, description="Currency of the quoted price"
    )
    account_currency: str | None = Field(
        default=None, min_length=3, max_length=3, description="Currency the book is held in"
    )
    tick_size: Decimal | None = Field(default=None, gt=Decimal(0))
    lot_size: Decimal | None = Field(default=None, gt=Decimal(0))
    multiplier: Decimal | None = Field(default=None, gt=Decimal(0))
    expiry: date | None = None
    strike: Decimal | None = Field(default=None, gt=Decimal(0))
    underlying_instrument_id: str | None = None
    figi: str | None = None
    isin: str | None = None
    cik: str | None = None
    status: InstrumentStatus = InstrumentStatus.ACTIVE

    valid_from: datetime = Field(..., description="When this description became true in the world")
    valid_to: datetime | None = Field(
        default=None, description="When it stopped being true in the world; None = still true"
    )
    recorded_from: datetime = Field(..., description="When we learned this")
    recorded_to: datetime | None = Field(
        default=None, description="When we stopped believing this; None = current belief"
    )
    source: str = Field(..., min_length=1)
    source_priority: int = Field(
        default=100, ge=0, le=1000, description="Lower wins when two sources disagree"
    )
    revision: int = Field(default=1, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _coerce_decimals(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field in ("tick_size", "lot_size", "multiplier", "strike"):
            if field in data and data[field] is not None:
                coerced = _dec(data[field])
                if coerced is None:
                    raise ValueError(f"{field} is not a valid number: {data[field]!r}")
                data[field] = coerced
        return data

    @model_validator(mode="after")
    def _check_intervals(self) -> InstrumentIdentity:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        # Equality is allowed: a belief learned and superseded within one
        # batch (a backfill asserting a full history with one recorded
        # timestamp) covers no recorded time, which is an empty truth rather
        # than a contradiction. Strict inversion is still refused — a belief
        # closed before it was held is a contradiction, not a revision. The
        # asymmetry with valid time is deliberate: a zero-duration *valid*
        # interval would claim something was true for no time, while a
        # zero-duration *recorded* interval merely records that the system
        # moved on immediately.
        if self.recorded_to is not None and self.recorded_to < self.recorded_from:
            raise ValueError("recorded_to must not precede recorded_from")
        return self

    @property
    def is_current(self) -> bool:
        """True when this is the version AIOS currently believes."""
        return self.recorded_to is None

    @property
    def is_live(self) -> bool:
        """True when this description is still true in the world."""
        return self.valid_to is None and self.status is InstrumentStatus.ACTIVE

    def covers_valid_time(self, moment: datetime) -> bool:
        """Whether this version was true of the world at ``moment``."""
        if moment < self.valid_from:
            return False
        return self.valid_to is None or moment < self.valid_to

    def covers_recorded_time(self, moment: datetime) -> bool:
        """Whether AIOS believed this version at ``moment``."""
        if moment < self.recorded_from:
            return False
        return self.recorded_to is None or moment < self.recorded_to

    def identity_digest(self) -> str:
        """Stable digest of the *content* that varies between revisions.

        Excludes the temporal columns on purpose: two revisions that assert the
        same thing at the same valid time are the same assertion, and the store
        refuses the second as a no-op rather than churning the history.
        """
        payload = "|".join(
            str(value)
            for value in (
                self.instrument_id,
                self.listing_id,
                self.ticker,
                self.mic,
                self.venue,
                str(self.asset_class),
                self.security_type,
                self.currency,
                self.quote_currency,
                self.account_currency,
                self.tick_size,
                self.lot_size,
                self.multiplier,
                self.expiry,
                self.strike,
                self.underlying_instrument_id,
                self.figi,
                self.isin,
                self.cik,
                str(self.status),
            )
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def resolve_currency(self) -> str:
        """The currency a position in this instrument is accounted in.

        Falls back through quote then trading currency. An instrument that
        cannot name its accounting currency cannot be valued into the book, so
        this is a total function rather than an Optional one.
        """
        return self.account_currency or self.quote_currency or self.currency


class IdentityConflict(BaseModel):
    """Two sources assert different content for the same listing and time."""

    model_config = {"frozen": True}

    listing_id: str
    valid_from: datetime
    existing_source: str
    incoming_source: str
    existing_digest: str
    incoming_digest: str
    winner: str = Field(..., description="Source whose claim was accepted")
    reason: str = Field(..., min_length=1)


class CorporateAction(BaseModel):
    """One announced event affecting an instrument's identity or economics."""

    model_config = {"frozen": True}

    action_id: str = Field(..., min_length=1)
    instrument_id: str = Field(..., min_length=1)
    listing_id: str | None = None
    action_type: ActionType
    announced_at: datetime
    effective_at: datetime = Field(..., description="When the economics change")
    record_date: date | None = Field(
        default=None, description="Holder-of-record cutoff; precedes ex-date"
    )
    ex_date: date | None = Field(default=None, description="First date trading ex-action")
    ratio_old: Decimal | None = Field(default=None, gt=Decimal(0))
    ratio_new: Decimal | None = Field(default=None, gt=Decimal(0))
    cash_amount: Decimal | None = Field(default=None)
    new_ticker: str | None = None
    successor_instrument_id: str | None = None
    source: str = Field(..., min_length=1)
    source_hash: str | None = Field(
        default=None, description="Content hash of the announcement that produced this record"
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_decimals(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for field in ("ratio_old", "ratio_new", "cash_amount"):
            if field in data and data[field] is not None:
                coerced = _dec(data[field])
                if coerced is None:
                    raise ValueError(f"{field} is not a valid number: {data[field]!r}")
                data[field] = coerced
        return data

    @model_validator(mode="after")
    def _check(self) -> CorporateAction:
        if self.effective_at < self.announced_at:
            raise ValueError("an action cannot take effect before it is announced")
        if self.ex_date is not None and self.record_date is not None:
            if self.ex_date < self.record_date:
                raise ValueError("ex_date cannot precede record_date")
        if self.action_type in {ActionType.SPLIT, ActionType.REVERSE_SPLIT}:
            if self.ratio_old is None or self.ratio_new is None:
                raise ValueError(f"{self.action_type} requires ratio_old and ratio_new")
            if self.ratio_old <= 0 or self.ratio_new <= 0:
                raise ValueError("split ratios must be positive")
        if self.action_type is ActionType.SYMBOL_CHANGE and not self.new_ticker:
            raise ValueError("SYMBOL_CHANGE requires new_ticker")
        return self

    @property
    def split_factor(self) -> Decimal | None:
        """Multiplier that makes a pre-action price comparable to post-action.

        A 4-for-1 split (``ratio_old=1``, ``ratio_new=4``) yields ``0.25``: a
        pre-split price of 400 adjusts to 100, which is what one share is worth
        after the split. Share quantities move the other way, by the reciprocal,
        which is why :class:`PriceAdjustment` carries both factors rather than
        one shared scale.
        """
        if self.ratio_old is None or self.ratio_new is None:
            return None
        if self.ratio_old == 0:
            return None
        return self.ratio_old / self.ratio_new


# ────────────────────────────────────────────────────────────────────────────
# Store boundary
#
# The mixin is dialect-portable: every statement below is parameter-free and
# understood by both SQLite (>= 3.23) and PostgreSQL, mirroring the approach
# core/financial_invariants.py takes. Each concrete store supplies only a row
# reader and a writer.
# ────────────────────────────────────────────────────────────────────────────


class SecurityMasterStore(ABC):
    """Persistence boundary for instrument identity and corporate actions."""

    @abstractmethod
    def record_identity(self, record: InstrumentIdentity) -> InstrumentIdentity:
        """Persist one bitemporal version, superseding any prior belief."""

    @abstractmethod
    def identity_versions(self, instrument_id: str) -> list[InstrumentIdentity]:
        """Every version ever held for an identity, oldest belief first."""

    @abstractmethod
    def record_action(self, action: CorporateAction) -> CorporateAction:
        """Persist one corporate action. Same action_id is a no-op, not an update."""

    @abstractmethod
    def actions_for(self, instrument_id: str) -> list[CorporateAction]:
        """Every action for an identity, in effective-time order."""

    @abstractmethod
    def _identity_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        """Run a portable read and return rows keyed by column."""

    @abstractmethod
    def _action_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        """Run a portable read against corporate actions."""


def _row_to_identity(row: dict[str, Any]) -> InstrumentIdentity:
    def when(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def day(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value)[:10])

    return InstrumentIdentity(
        instrument_id=str(row["instrument_id"]),
        listing_id=str(row["listing_id"]),
        ticker=str(row["ticker"]),
        mic=str(row["mic"]),
        venue=str(row["venue"]),
        asset_class=AssetClass(str(row["asset_class"])),
        security_type=str(row["security_type"] or "COMMON"),
        currency=str(row["currency"]),
        quote_currency=row["quote_currency"],
        account_currency=row["account_currency"],
        tick_size=row["tick_size"],
        lot_size=row["lot_size"],
        multiplier=row["multiplier"],
        expiry=day(row["expiry"]),
        strike=row["strike"],
        underlying_instrument_id=row["underlying_instrument_id"],
        figi=row["figi"],
        isin=row["isin"],
        cik=row["cik"],
        status=InstrumentStatus(str(row["status"])),
        valid_from=when(row["valid_from"]),  # type: ignore[arg-type]
        valid_to=when(row["valid_to"]),
        recorded_from=when(row["recorded_from"]),  # type: ignore[arg-type]
        recorded_to=when(row["recorded_to"]),
        source=str(row["source"]),
        source_priority=int(row["source_priority"]),
        revision=int(row["revision"]),
    )


def _row_to_action(row: dict[str, Any]) -> CorporateAction:
    def when(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def day(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value)[:10])

    return CorporateAction(
        action_id=str(row["action_id"]),
        instrument_id=str(row["instrument_id"]),
        listing_id=row["listing_id"],
        action_type=ActionType(str(row["action_type"])),
        announced_at=when(row["announced_at"]),
        effective_at=when(row["effective_at"]),
        record_date=day(row["record_date"]),
        ex_date=day(row["ex_date"]),
        ratio_old=row["ratio_old"],
        ratio_new=row["ratio_new"],
        cash_amount=row["cash_amount"],
        new_ticker=row["new_ticker"],
        successor_instrument_id=row["successor_instrument_id"],
        source=str(row["source"]),
        source_hash=row["source_hash"],
    )


class SecurityMaster:
    """Query layer over the identity store.

    Answers the two temporal questions separately because conflating them is
    the failure this class exists to prevent. ``resolve`` is what a trading path
    wants: the instrument as we currently believe it. ``as_of`` and
    ``as_known`` are what a research or audit path wants.
    """

    def __init__(self, store: SecurityMasterStore) -> None:
        self._store = store

    # ------------------------------------------------------------------ writes

    def upsert(self, record: InstrumentIdentity) -> InstrumentIdentity:
        """Record a version, closing the prior belief when it changes.

        Refuses to churn history: re-recording identical content at the same
        valid time is a no-op, so a repeated feed load does not manufacture
        revisions that an auditor would then have to explain. The no-op covers
        superseded versions too, not just the current belief: a nightly feed
        re-asserts the whole history, and a re-assertion of an assertion
        already in the log is not new information — refusing it would make
        every reload crash on the first closed row.
        """
        existing = self._store.identity_versions(record.instrument_id)
        for version in existing:
            if (
                version.recorded_to is None
                and version.valid_from == record.valid_from
                and version.identity_digest() == record.identity_digest()
            ):
                return version
        for version in existing:
            if (
                version.valid_from == record.valid_from
                and version.identity_digest() == record.identity_digest()
            ):
                return version
        return self._store.record_identity(record)

    def conflicts_for(self, instrument_id: str) -> list[IdentityConflict]:
        """Places where two sources disagreed and one was rejected.

        Retained rather than discarded: a rejected assertion is evidence that
        the source was wrong, which is exactly the kind of fact a later dispute
        needs.
        """
        rows = self._store._identity_rows(
            "SELECT listing_id, valid_from, existing_source, incoming_source,"
            " existing_digest, incoming_digest, winner, reason FROM identity_conflicts"
            " WHERE instrument_id = ? ORDER BY valid_from",
            (instrument_id,),
        )
        return [
            IdentityConflict(
                listing_id=str(row["listing_id"]),
                valid_from=datetime.fromisoformat(str(row["valid_from"])),
                existing_source=str(row["existing_source"]),
                incoming_source=str(row["incoming_source"]),
                existing_digest=str(row["existing_digest"]),
                incoming_digest=str(row["incoming_digest"]),
                winner=str(row["winner"]),
                reason=str(row["reason"]),
            )
            for row in rows
        ]

    def record_action(self, action: CorporateAction) -> CorporateAction:
        return self._store.record_action(action)

    # ------------------------------------------------------------------- reads

    def versions(self, instrument_id: str) -> list[InstrumentIdentity]:
        return self._store.identity_versions(instrument_id)

    def current(self, instrument_id: str) -> InstrumentIdentity | None:
        """The version AIOS currently believes, or None if never recorded."""
        for version in reversed(self._store.identity_versions(instrument_id)):
            if version.is_current:
                return version
        return None

    def as_of(self, instrument_id: str, moment: datetime) -> InstrumentIdentity | None:
        """The instrument as it truly was at ``moment``.

        Uses valid time only, so it returns what was true even if AIOS learned
        it much later. This is what a point-in-time backtest must join against.
        """
        candidates = [
            version
            for version in self._store.identity_versions(instrument_id)
            if version.covers_valid_time(moment)
        ]
        if not candidates:
            return None
        # Latest valid_from wins; ties resolve to the highest-priority source.
        return max(candidates, key=lambda v: (v.valid_from, -v.source_priority, v.revision))

    def as_known(self, instrument_id: str, moment: datetime) -> InstrumentIdentity | None:
        """What AIOS believed about the instrument at ``moment``.

        Uses transaction time only. An audit asking "what did the system think
        on 3 March" needs this, and it is the question that makes a corrected
        record auditable rather than merely amended.
        """
        candidates = [
            version
            for version in self._store.identity_versions(instrument_id)
            if version.covers_recorded_time(moment)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda v: (v.recorded_from, v.revision))

    def resolve(self, ticker: str, mic: str) -> InstrumentIdentity | None:
        """Current identity for a ticker on a venue; the trading-path lookup."""
        rows = self._store._identity_rows(
            "SELECT * FROM instrument_identity"
            " WHERE ticker = ? AND mic = ? AND recorded_to IS NULL"
            " ORDER BY revision DESC",
            (ticker, mic),
        )
        return _row_to_identity(rows[0]) if rows else None

    def find_by_isin(self, isin: str) -> InstrumentIdentity | None:
        rows = self._store._identity_rows(
            "SELECT * FROM instrument_identity"
            " WHERE isin = ? AND recorded_to IS NULL ORDER BY revision DESC",
            (isin,),
        )
        return _row_to_identity(rows[0]) if rows else None

    def actions(self, instrument_id: str) -> list[CorporateAction]:
        return self._store.actions_for(instrument_id)


# ────────────────────────────────────────────────────────────────────────────
# Corporate action engine
# ────────────────────────────────────────────────────────────────────────────


#: Actions after which the listing no longer trades under this identity. A
#: merger and a spin-off are terminal for the acquired line in the same way a
#: delisting is: the security stops existing as a tradeable listing, and
#: recording only an explicit DELISTING would silently leave a dead listing
#: marked ACTIVE in the master.
_TERMINAL_ACTIONS = frozenset(
    {ActionType.DELISTING, ActionType.MERGER, ActionType.SPINOFF}
)


@dataclass(frozen=True)
class PriceAdjustment:
    """The transform mapping one raw observation into anchor terms.

    This is back-adjustment, and the direction matters. Given a 2-for-1 split, a
    raw feed shows 100 before the ex-date and 50 after, while the economically
    continuous value is 50 at both. The pre-split observation therefore has to be
    scaled by 1/2 and the post-split one left alone.

    That asymmetry is why an anchor is explicit. "Adjust to what?" has no answer
    on its own, and a default that silently picked the newest action would make
    the result depend on which rows happened to be loaded.
    """

    #: Multiply the raw price by this to express it in anchor terms.
    price_factor: Decimal
    #: Multiply the raw share quantity by this. A 2-for-1 split turns one
    #: pre-split share into two, so this is 2.
    quantity_factor: Decimal
    #: Cash per share paid out between the observation and the anchor. Kept
    #: separate because a dividend reduces price without changing share count,
    #: and folding it into a price factor loses that distinction.
    cash_per_share: Decimal
    #: Time of the observation being adjusted.
    as_of: datetime
    #: Time the observation is expressed in terms of.
    anchor: datetime
    #: How many actions contributed, so a reader can see the chain's depth.
    applied: int

    @property
    def is_identity(self) -> bool:
        return self.price_factor == Decimal(1) and self.quantity_factor == Decimal(1)


class CorporateActionEngine:
    """Replayable price and quantity adjustment from stored actions.

    Deliberately recomputes from the event list rather than storing a
    precomputed adjusted series. A precomputed series is a snapshot: correct the
    ratio for one historical split and every stored price becomes wrong with no
    way to tell which. Replay is cheap and self-correcting.

    Two properties are enforced by tests rather than assumed:

    * only an action with ``moment < effective_at <= anchor`` may alter an
      observation. An action after the anchor, or one already baked into the raw
      value, must not. This is the look-ahead property, and it is the one a
      naive "apply every split in the file" implementation gets wrong.
    * the transform is exactly invertible, so a re-fit cannot silently change
      the history it is re-fitting.
    """

    def __init__(self, actions: list[CorporateAction] | None = None) -> None:
        self._actions: list[CorporateAction] = list(actions or [])

    def add(self, action: CorporateAction) -> None:
        self._actions.append(action)

    def actions(self, instrument_id: str | None = None) -> list[CorporateAction]:
        """Actions in effective-time order, optionally for one instrument."""
        selected = [
            action
            for action in self._actions
            if instrument_id is None or action.instrument_id == instrument_id
        ]
        return sorted(selected, key=lambda a: (a.effective_at, a.action_id))

    def latest_effective_at(self, instrument_id: str) -> datetime | None:
        """Effective time of the newest action, the natural default anchor."""
        relevant = self.actions(instrument_id)
        return relevant[-1].effective_at if relevant else None

    def adjustment(
        self,
        instrument_id: str,
        moment: datetime,
        anchor: datetime | None = None,
    ) -> PriceAdjustment:
        """Adjustment mapping a raw observation at ``moment`` into anchor terms.

        Only actions with ``moment < effective_at <= anchor`` contribute. An
        action effective before the observation is already baked into the raw
        value, and an action after the anchor is outside the frame entirely.

        Args:
            instrument_id: Identity whose action chain to replay.
            moment: Effective time of the observation being adjusted.
            anchor: Time to express the observation in terms of. ``None`` means
                the latest known action for this instrument.
        """
        resolved = anchor if anchor is not None else self.latest_effective_at(instrument_id)
        if resolved is None:
            return PriceAdjustment(
                price_factor=Decimal(1),
                quantity_factor=Decimal(1),
                cash_per_share=Decimal(0),
                as_of=moment,
                anchor=moment,
                applied=0,
            )
        if moment > resolved:
            raise ValueError(
                f"observation at {moment.isoformat()} is after the requested anchor "
                f"{resolved.isoformat()}; anchor to at least the observation"
            )

        # Numerators and denominators are accumulated separately and divided
        # once at the end. Dividing at each step would round twice: 1/2 * 1/3
        # lands on a different value than 1/6, and a chained split history would
        # drift further from the exact ratio with every action.
        price_num = Decimal(1)
        price_den = Decimal(1)
        quantity_num = Decimal(1)
        quantity_den = Decimal(1)
        cash = Decimal(0)
        applied = 0
        for action in self.actions(instrument_id):
            if action.effective_at <= moment:
                # Already reflected in the raw observation.
                continue
            if action.effective_at > resolved:
                break
            if (
                action.ratio_old is not None
                and action.ratio_new is not None
                and action.ratio_old > 0
            ):
                price_num *= action.ratio_old
                price_den *= action.ratio_new
                quantity_num *= action.ratio_new
                quantity_den *= action.ratio_old
            if action.action_type is ActionType.DIVIDEND and action.cash_amount:
                cash += action.cash_amount
            applied += 1
        return PriceAdjustment(
            price_factor=price_num / price_den,
            quantity_factor=quantity_num / quantity_den,
            cash_per_share=cash,
            as_of=moment,
            anchor=resolved,
            applied=applied,
        )

    def adjust_price(
        self,
        instrument_id: str,
        moment: datetime,
        raw_price: Decimal,
        anchor: datetime | None = None,
    ) -> Decimal:
        """Express one raw price in anchor terms."""
        return raw_price * self.adjustment(instrument_id, moment, anchor).price_factor

    def adjust_quantity(
        self,
        instrument_id: str,
        moment: datetime,
        raw_quantity: Decimal,
        anchor: datetime | None = None,
    ) -> Decimal:
        """Express one raw share quantity in anchor terms."""
        return raw_quantity * self.adjustment(instrument_id, moment, anchor).quantity_factor

    def unadjust_price(
        self,
        instrument_id: str,
        moment: datetime,
        adjusted: Decimal,
        anchor: datetime | None = None,
    ) -> Decimal:
        """Invert the price transform, for comparing against a raw feed."""
        factor = self.adjustment(instrument_id, moment, anchor).price_factor
        if factor == 0:
            raise ValueError("cannot invert a zero adjustment factor")
        return adjusted / factor

    def identity_transitions(
        self, instrument_id: str
    ) -> list[tuple[datetime, InstrumentStatus, str | None]]:
        """Effective-time sequence of identity changes for a symbol.

        Returns ``(effective_at, status, successor)`` in order, so a caller can
        ask "was this tradeable on date X" without reconstructing the chain.
        """
        transitions: list[tuple[datetime, InstrumentStatus, str | None]] = []
        for action in self.actions(instrument_id):
            if action.action_type in _TERMINAL_ACTIONS:
                transitions.append(
                    (action.effective_at, InstrumentStatus.DELISTED, action.successor_instrument_id)
                )
            elif action.action_type is ActionType.SYMBOL_CHANGE and action.new_ticker:
                transitions.append(
                    (action.effective_at, InstrumentStatus.ACTIVE, action.new_ticker)
                )
        return transitions

    def ticker_at(self, instrument_id: str, moment: datetime) -> str | None:
        """The ticker this instrument traded under at ``moment``.

        Answers the question that silently corrupts a backtest: joining a
        2019 price series to a symbol that only adopted that ticker in 2023.
        """
        ticker: str | None = None
        for action in self.actions(instrument_id):
            if action.effective_at > moment:
                break
            if action.action_type is ActionType.SYMBOL_CHANGE and action.new_ticker:
                ticker = action.new_ticker
        return ticker
