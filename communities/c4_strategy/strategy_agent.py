"""Community 4: Strategy Agent - multi-family candidate generation.

Families propose raw candidates; each is validated into a StrategySpecification
and published on STRATEGY_GENERATED. The C9 PortfolioGovernor gates every
candidate before execution (nothing executes without an allocation plan).
Opportunity scores are computed and published for observability/ranking.
NO TRADE remains a valid outcome at multiple stages.
"""

import logging
from collections import OrderedDict, deque
from typing import TypeVar

from communities.c4_strategy.families import (
    DEFAULT_FAMILIES,
    FamilyCandidate,
    MomentumFamily,
    StrategyFamily,
)
from communities.c4_strategy.opportunity import rank, score_candidate
from core.data_quality import _FREEZING_STATES
from core.event_bus import BaseEventBus, EventTopic
from core.risk_firewall import RiskFirewall
from schemas.contracts import (
    CandidateHypothesis,
    DataAnomalyAlert,
    MarketDataPayload,
    RegimeState,
    StrategySpecification,
    VerificationReport,
    VolRegime,
)

logger = logging.getLogger(__name__)

_DEFAULT_PROPOSED_POSITION_SIZE_PCT = 5.0
_CACHE_MAX_ENTRIES = 512

# Volatility-regime scaling of proposed size (Directive 37 conditioning)
_VOL_SIZE_SCALAR = {
    VolRegime.HIGH: 0.5,
    VolRegime.NORMAL: 1.0,
    VolRegime.LOW: 1.0,
}

T = TypeVar("T")


def _bounded_put(cache: OrderedDict[str, T], key: str, value: T) -> None:
    """Insert into cache with FIFO eviction beyond _CACHE_MAX_ENTRIES (defect D6)."""
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


class StrategyAgent:
    """Strategy Agent translating verified hypotheses into family candidates."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        risk_firewall: RiskFirewall,
        portfolio_value_estimate: float = 100000.0,
        families: list[StrategyFamily] | None = None,
        close_history_window: int = 30,
    ) -> None:
        if portfolio_value_estimate <= 0:
            raise ValueError("portfolio_value_estimate must be positive")
        self.event_bus = event_bus
        self.risk_firewall = risk_firewall
        self._portfolio_value_estimate = portfolio_value_estimate
        self.families: list[StrategyFamily] = (
            families if families is not None else list(DEFAULT_FAMILIES)
        )
        self._history_window = close_history_window

        self._hypotheses: OrderedDict[str, CandidateHypothesis] = OrderedDict()
        self._market_payloads: OrderedDict[str, MarketDataPayload] = OrderedDict()
        self._close_history: dict[str, deque[float]] = {}
        self._bar_counts: dict[str, int] = {}
        self._frozen_symbols: set[str] = set()
        self._regimes: dict[str, RegimeState] = {}

    # ------------------------------------------------------------ event sinks

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        """Cache market state (bounded); clean arrivals unfreeze symbols."""
        _bounded_put(self._market_payloads, payload.symbol, payload)
        history = self._close_history.setdefault(payload.symbol, deque(maxlen=self._history_window))
        history.append(payload.price_data.close)
        self._bar_counts[payload.symbol] = self._bar_counts.get(payload.symbol, 0) + 1

        quality = payload.provenance.quality_state if payload.provenance else "FRESH"
        if payload.is_simulated or quality not in _FREEZING_STATES:
            self._frozen_symbols.discard(payload.symbol)

    async def on_data_anomaly(self, alert: DataAnomalyAlert) -> None:
        """Directive 9 reaction: freeze the symbol when the alert demands it."""
        if alert.freezes_symbol:
            self._frozen_symbols.add(alert.symbol)
            logger.warning(
                "Symbol %s frozen for strategy generation: %s (%s)",
                alert.symbol,
                alert.anomaly_type,
                alert.detail,
            )

    async def on_regime_changed(self, state: RegimeState) -> None:
        """Track latest regime per symbol for volatility-scaled sizing."""
        self._regimes[state.symbol] = state

    # ----------------------------------------------------------- generation

    async def generate_strategy(
        self,
        verification_report: VerificationReport,
        hypothesis: CandidateHypothesis,
        daily_drawdown_pct: float = 0.0,
    ) -> list[StrategySpecification]:
        """Generate, validate and publish all viable family candidates.

        Returns the list of approved specifications (possibly empty - NO TRADE).
        """
        payload = self._market_payloads.get(hypothesis.symbol)
        if payload is None:
            logger.info(
                "NO TRADE for hypothesis %s: no market state cached for %s",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
            )
            return []

        if hypothesis.symbol in self._frozen_symbols:
            logger.info(
                "NO TRADE for hypothesis %s: %s frozen by data anomaly",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
            )
            return []

        sentiment_avg = 0.0
        if payload.news_sentiment:
            sentiment_avg = sum(s.sentiment_score for s in payload.news_sentiment) / len(
                payload.news_sentiment
            )
        history = self._close_history.get(hypothesis.symbol, deque())
        regime = self._regimes.get(hypothesis.symbol)
        vol_scalar = _VOL_SIZE_SCALAR.get(regime.vol_regime, 1.0) if regime else 1.0

        momentum_family = next((f for f in self.families if isinstance(f, MomentumFamily)), None)
        rr_override = max(hypothesis.expected_risk_reward_ratio, 1.5)
        candidates: list[FamilyCandidate] = []
        for family in self.families:
            if isinstance(family, MomentumFamily) and momentum_family is not None:
                candidate = family.evaluate(hypothesis.symbol, payload, history, sentiment_avg)
                if candidate is not None:
                    candidate = FamilyCandidate(
                        family=candidate.family,
                        action=candidate.action,
                        entry_price=candidate.entry_price,
                        stop_distance_pct=candidate.stop_distance_pct,
                        risk_reward_ratio=rr_override,
                    )
            else:
                candidate = family.evaluate(hypothesis.symbol, payload, history, sentiment_avg)
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            logger.info(
                "NO TRADE for hypothesis %s on %s: no family produced a candidate",
                hypothesis.hypothesis_id,
                hypothesis.symbol,
            )
            return []

        approved: list[StrategySpecification] = []
        scores = []
        for candidate in candidates:
            strategy = self._to_specification(hypothesis, candidate, vol_scalar)
            if strategy is None:
                continue
            risk_result = self.risk_firewall.evaluate_strategy(
                strategy=strategy,
                current_portfolio_value=self._portfolio_value_estimate,
                current_daily_drawdown_pct=daily_drawdown_pct,
            )
            if not risk_result.is_approved:
                logger.warning(
                    "%s candidate for %s rejected by firewall: %s",
                    candidate.family,
                    hypothesis.symbol,
                    risk_result.rejection_reasons,
                )
                continue
            strategy = strategy.model_copy(
                update={"position_size_pct": risk_result.adjusted_position_size_pct}
            )
            await self.event_bus.publish(EventTopic.STRATEGY_GENERATED, strategy)
            scores.append(
                score_candidate(
                    strategy,
                    candidate.family,
                    verification_report.confidence_score,
                    timeframe=hypothesis.timeframe,
                )
            )
            approved.append(strategy)

        if scores:
            for score in rank(scores):
                await self.event_bus.publish(EventTopic.OPPORTUNITY_RANKED, score)

        if not approved:
            logger.info(
                "NO TRADE for hypothesis %s: all candidates rejected", hypothesis.hypothesis_id
            )
        return approved

    async def on_hypothesis_generated(self, hypothesis: CandidateHypothesis) -> None:
        """Cache candidate hypothesis by hypothesis_id (bounded)."""
        _bounded_put(self._hypotheses, hypothesis.hypothesis_id, hypothesis)

    async def on_verification_completed(self, report: VerificationReport) -> None:
        """Event handler triggered when a hypothesis is verified."""
        if not report.is_verified:
            logger.debug("Ignoring unverified report %s", report.report_id)
            return
        hypothesis = self._hypotheses.get(report.hypothesis_id)
        if not hypothesis:
            logger.warning("Hypothesis %s not found in StrategyAgent cache", report.hypothesis_id)
            return
        await self.generate_strategy(verification_report=report, hypothesis=hypothesis)

    def _to_specification(
        self,
        hypothesis: CandidateHypothesis,
        candidate: FamilyCandidate,
        vol_scalar: float,
    ) -> StrategySpecification | None:
        try:
            return StrategySpecification(
                hypothesis_id=hypothesis.hypothesis_id,
                symbol=hypothesis.symbol,
                action=candidate.action,  # type: ignore[arg-type]
                entry_price=candidate.entry_price,
                stop_loss_price=candidate.stop_price(),
                take_profit_price=candidate.take_profit_price(),
                position_size_pct=round(_DEFAULT_PROPOSED_POSITION_SIZE_PCT * vol_scalar, 2),
                family=candidate.family,
            )
        except ValueError as exc:
            logger.warning(
                "Invalid geometry from %s family for %s: %s",
                candidate.family,
                hypothesis.symbol,
                exc,
            )
            return None
