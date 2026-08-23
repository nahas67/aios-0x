"""Community 4: Opportunity engine - ranking strategy candidates (Directive 30/31).

Owned by C4 per the canonical topic namespace (aios.c4.opportunity_ranked).
Score = (confidence - breakeven_probability) x risk_reward x alpha_decay.
"""

from schemas.contracts import OpportunityScore, StrategySpecification

_DECAY_HALFLIFE_BARS = {
    "1m": 60.0,
    "5m": 30.0,
    "15m": 20.0,
    "1h": 12.0,
    "4h": 8.0,
    "1d": 5.0,
}


def alpha_decay_multiplier(timeframe: str, bars_since_signal: int) -> float:
    """Exponential decay of edge by elapsed bars vs timeframe half-life."""
    halflife = _DECAY_HALFLIFE_BARS.get(timeframe, 10.0)
    return float(0.5 ** (max(0, bars_since_signal) / halflife))


def score_candidate(
    strategy: StrategySpecification,
    family: str,
    confidence_pct: float,
    timeframe: str = "1d",
    bars_since_signal: int = 0,
) -> OpportunityScore:
    rr = max(strategy.risk_reward_ratio(), 0.01)
    breakeven_p = 1.0 / (1.0 + rr)
    edge = max(-1.0, min(1.0, confidence_pct / 100.0 - breakeven_p))
    decay = alpha_decay_multiplier(timeframe, bars_since_signal)
    return OpportunityScore(
        strategy_id=strategy.strategy_id,
        symbol=strategy.symbol,
        family=family,
        edge_proxy=round(edge, 6),
        expected_rr=round(rr, 4),
        alpha_decay_multiplier=round(decay, 6),
        composite_rank=round(edge * rr * decay, 6),
        is_simulated=True,
    )


def rank(candidates: list[OpportunityScore]) -> list[OpportunityScore]:
    return sorted(candidates, key=lambda s: s.composite_rank, reverse=True)
