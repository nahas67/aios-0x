"""Community 6: Postmortem engine - structured, evidence-bound trade reviews.

Builds PostmortemRecord payloads strictly from recorded artifacts (hypothesis,
strategy, receipt, observation). Decision quality is separated from outcome
luck; no claim is made beyond what the data supports.
"""

from schemas.contracts import (
    CandidateHypothesis,
    ObservationReport,
    PostmortemRecord,
    StrategySpecification,
    TradeExecutionReceipt,
)

_NOISE_FEE_MULTIPLE = 3.0


class PostmortemEngine:
    """Deterministic post-mortem builder for closed trades."""

    def build(
        self,
        hypothesis: CandidateHypothesis,
        strategy: StrategySpecification,
        receipt: TradeExecutionReceipt,
        observation: ObservationReport,
        exit_price: float,
        exit_reason: str,
        prediction_id: str | None = None,
    ) -> PostmortemRecord:
        """Compose a post-mortem from recorded decision and outcome artifacts."""
        direction_correct = observation.direction_correct
        pnl = observation.actual_pnl
        fees_ratio = abs(pnl) / receipt.fees if receipt.fees > 0 else float("inf")

        got_right: list[str] = []
        got_wrong: list[str] = []

        if direction_correct:
            got_right.append(
                f"Directional call ({strategy.action}) matched realized price movement."
            )
            if exit_reason == "TARGET_HIT":
                got_right.append("Take-profit level reached as the thesis anticipated.")
        else:
            got_wrong.append(
                f"Directional call ({strategy.action}) contradicted realized movement; "
                "stop-level invalidation triggered."
                if exit_reason == "STOP_HIT"
                else f"Position closed at market with adverse PnL ({exit_reason})."
            )

        if exit_reason == "HORIZON_END":
            got_wrong.append(
                "Data horizon ended before the thesis could resolve; exit forced at last close."
            )

        unknowable: list[str] = [
            "Future bars after the decision timestamp were (correctly) unavailable.",
            "No news/sentiment feed existed in this replay slice.",
        ]

        if fees_ratio <= _NOISE_FEE_MULTIPLE:
            luck_assessment = (
                f"|PnL| within {_NOISE_FEE_MULTIPLE:.0f}x of fees (${receipt.fees:.2f}); "
                "outcome is inside cost noise - do not update beliefs from this trade alone."
            )
        elif direction_correct:
            luck_assessment = (
                "Outcome consistent with the stated edge; single trade remains weak evidence "
                "(variance dominates small samples)."
            )
        else:
            luck_assessment = (
                "Loss exceeded cost noise: the invalidation condition fired on its merits."
            )

        should_change: list[str] = []
        if exit_reason == "STOP_HIT" and not direction_correct:
            should_change.append(
                "Review entry criteria for this regime; stop was hit before target."
            )
        if exit_reason == "TARGET_HIT":
            should_change.append(
                "Log setup features for reinforcement; do not loosen risk limits on one win."
            )
        if strategy.position_size_pct >= 5.0:
            should_change.append(
                "Position sized at the cap; consider volatility-scaled sizing in C4/C9."
            )

        return PostmortemRecord(
            execution_id=receipt.execution_id,
            prediction_id=prediction_id,
            hypothesis_id=hypothesis.hypothesis_id,
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            what_we_thought=hypothesis.thesis,
            what_we_knew=list(hypothesis.supporting_arguments)
            + [f"Counterpoint held: {c}" for c in hypothesis.counter_arguments],
            what_we_did=(
                f"{strategy.action} {strategy.symbol} at entry ref {strategy.entry_price:.4f} "
                f"(fill {receipt.fill_price:.4f}), stop {strategy.stop_loss_price:.4f}, "
                f"target {strategy.take_profit_price:.4f}, size {strategy.position_size_pct:.2f}% "
                f"of portfolio, R:R {hypothesis.expected_risk_reward_ratio:.2f}."
            ),
            what_happened=(
                f"Exited at {exit_price:.4f} ({exit_reason}); realized PnL {pnl:+.2f}; "
                f"slippage {receipt.slippage:.4f}; fees ${receipt.fees:.2f}."
            ),
            got_right=got_right,
            got_wrong=got_wrong,
            unknowable=unknowable,
            luck_assessment=luck_assessment,
            should_change=should_change,
        )
