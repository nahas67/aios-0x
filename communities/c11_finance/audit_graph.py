"""Community 11: Decision audit graph - provenance walks over the hash-chained log.

Implements Doc 18's query API on top of the persisted event stream:
- decision_provenance(execution_id): execution -> strategy -> hypothesis -> verification
- hypothesis_impact(hypothesis_id): downstream executions + realized PnL
"""

from typing import Any

from core.persistence import BaseMemoryStore

# Canonical topic names double as event-log kinds (ADR-002 / Phase 3).
K_EXECUTION = "aios.c5.order_executed"
K_STRATEGY = "aios.c4.strategy_generated"
K_HYPOTHESIS = "aios.c2.hypothesis_generated"
K_VERIFICATION = "aios.c3.verification_completed"
K_OBSERVATION = "aios.c6.observation_completed"


def _find(store: BaseMemoryStore, kind: str, match: str) -> dict[str, Any] | None:
    for payload in reversed(store.iter_event_payloads(kind)):
        if payload.get("execution_id") == match or payload.get("hypothesis_id") == match:
            return payload
        if kind == K_STRATEGY and payload.get("strategy_id") == match:
            return payload
    return None


def decision_provenance(store: BaseMemoryStore, execution_id: str) -> dict[str, Any]:
    """Walk the lineage chain backwards from one executed trade."""
    execution = _find(store, K_EXECUTION, execution_id)
    if execution is None:
        raise KeyError(f"no execution found for {execution_id}")

    strategy_id = execution.get("strategy_id", "")
    strategy = _find(store, K_STRATEGY, strategy_id)
    hypothesis_id = (strategy or {}).get("hypothesis_id", "")
    hypothesis = _find(store, K_HYPOTHESIS, hypothesis_id) if hypothesis_id else None
    verification = _find(store, K_VERIFICATION, hypothesis_id) if hypothesis_id else None
    observation = None
    for payload in reversed(store.iter_event_payloads(K_OBSERVATION)):
        if payload.get("execution_id") == execution_id:
            observation = payload
            break

    return {
        "execution": execution,
        "strategy": strategy,
        "hypothesis": hypothesis,
        "verification": verification,
        "observation": observation,
        "chain_complete": all([strategy, hypothesis, verification]),
    }


def hypothesis_impact(store: BaseMemoryStore, hypothesis_id: str) -> dict[str, Any]:
    """All executions descending from a hypothesis with their realized PnL."""
    strategies = [
        p for p in store.iter_event_payloads(K_STRATEGY) if p.get("hypothesis_id") == hypothesis_id
    ]
    strategy_ids = {s.get("strategy_id") for s in strategies}

    executions: list[dict[str, Any]] = []
    observations_by_execution: dict[str, float] = {}
    for obs in store.iter_event_payloads(K_OBSERVATION):
        eid = obs.get("execution_id")
        if eid is not None:
            observations_by_execution[eid] = float(obs.get("actual_pnl", 0.0))

    for execution in store.iter_event_payloads(K_EXECUTION):
        if execution.get("strategy_id") in strategy_ids:
            eid = execution.get("execution_id", "")
            executions.append(
                {
                    "execution_id": eid,
                    "symbol": execution.get("symbol"),
                    "realized_pnl": observations_by_execution.get(eid),
                }
            )

    pnls = [e["realized_pnl"] for e in executions if e["realized_pnl"] is not None]
    return {
        "hypothesis_id": hypothesis_id,
        "strategies": len(strategies),
        "executions": executions,
        "total_realized_pnl": round(sum(pnls), 2) if pnls else None,
    }
