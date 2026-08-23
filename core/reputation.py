"""Agent reputation v0: conditional, evidence-based, never outcome-luck.

Per family (momentum / mean_reversion / ...):
- accuracy + Brier from the scored prediction ledger (joined via executions)
- hallucination penalty from C3 verification flags on that family's hypotheses

Reputation is UNKNOWN below a minimum sample gate - honest ignorance instead
of a fake score. Regime-conditionality is recorded as a caveat until regime-
bucketed samples exist.
"""

import statistics
from collections import defaultdict
from typing import Any

from core.persistence import BaseMemoryStore

K_EXECUTION = "aios.c5.order_executed"
K_STRATEGY = "aios.c4.strategy_generated"
K_VERIFICATION = "aios.c3.verification_completed"

_MIN_SAMPLES = 10
_HALLUCINATION_PENALTY_PER_FLAG = 8.0
_PENALTY_CAP = 30.0


def _family_by_strategy(store: BaseMemoryStore) -> dict[str, str]:
    out: dict[str, str] = {}
    for payload in store.iter_event_payloads(K_STRATEGY):
        sid = payload.get("strategy_id")
        if sid:
            out[sid] = payload.get("family", "unknown")
    return out


def _hallucination_counts(store: BaseMemoryStore) -> dict[str, int]:
    """Flag counts keyed by hypothesis id."""
    counts: dict[str, int] = {}
    for payload in store.iter_event_payloads(K_VERIFICATION):
        hid = payload.get("hypothesis_id")
        flagged = payload.get("flagged_hallucinations") or []
        if hid:
            counts[hid] = counts.get(hid, 0) + len(flagged)
    return counts


def compute_reputations(store: BaseMemoryStore) -> dict[str, Any]:
    """Return per-family reputation payloads (UNKNOWN when samples < gate)."""
    strategy_family = _family_by_strategy(store)

    # execution_id -> strategy_id, then prediction rows by strategy_id
    exec_to_strategy: dict[str, str] = {}
    for payload in store.iter_event_payloads(K_EXECUTION):
        eid = payload.get("execution_id")
        sid = payload.get("strategy_id")
        if eid and sid:
            exec_to_strategy[eid] = sid

    per_family_outcomes: dict[str, list[tuple[float, float]]] = defaultdict(list)
    conn = getattr(store, "_conn", None)
    if conn is not None:
        rows = conn.execute(
            "SELECT strategy_id, confidence_score, direction_correct, status "
            "FROM predictions WHERE status='SCORED' AND direction_correct IS NOT NULL"
        ).fetchall()
        for row in rows:
            sid = row["strategy_id"]
            family = strategy_family.get(sid)
            if not family:
                continue
            p = max(0.01, min(0.99, float(row["confidence_score"]) / 100.0))
            outcome = 1.0 if bool(row["direction_correct"]) else 0.0
            brier = (p - outcome) ** 2
            per_family_outcomes[family].append((outcome, brier))

    hypothesis_family: dict[str, str] = {}
    for payload in store.iter_event_payloads(K_STRATEGY):
        hyp = payload.get("hypothesis_id")
        fam = payload.get("family", "unknown")
        if hyp and hyp not in hypothesis_family:
            hypothesis_family[hyp] = fam
    flag_counts = _hallucination_counts(store)

    reputations: dict[str, Any] = {}
    all_families = set(per_family_outcomes) | set(f for f in hypothesis_family.values() if f)
    for family in sorted(all_families):
        outcomes = per_family_outcomes.get(family, [])
        penalty = min(
            _PENALTY_CAP,
            sum(count for hid, count in flag_counts.items() if hypothesis_family.get(hid) == family)
            * _HALLUCINATION_PENALTY_PER_FLAG,
        )

        if len(outcomes) < _MIN_SAMPLES:
            reputations[family] = {
                "reputation": None,
                "state": "INSUFFICIENT_SAMPLES",
                "scored_predictions": len(outcomes),
                "hallucination_penalty": round(penalty, 1),
                "caveat": "no conviction below sample gate; regime conditioning pending",
            }
            continue

        accuracy = statistics.fmean(o for o, _ in outcomes)
        mean_brier = statistics.fmean(b for _, b in outcomes)
        raw = 100.0 * (0.6 * accuracy + 0.4 * max(0.0, 1.0 - mean_brier))
        reputation = max(0.0, min(100.0, raw - penalty))
        reputations[family] = {
            "reputation": round(reputation, 2),
            "state": "ACTIVE",
            "scored_predictions": len(outcomes),
            "accuracy_pct": round(accuracy * 100.0, 2),
            "mean_brier": round(mean_brier, 4),
            "hallucination_penalty": round(penalty, 1),
            "caveat": "regime conditioning pending bucketed samples",
        }
    return {
        "families": reputations,
        "min_samples_gate": _MIN_SAMPLES,
        "formula": "R = clamp(100*(0.6*acc + 0.4*(1-brier)) - hallucination_penalty)",
    }
