# AIOS-0X Event Model
Version 1.0.0 | Reconciles code topics vs Doc 14 namespace; defines target topic map

## 1. Current State (verified)
- Code (core/event_bus.py EventTopic): data.acquired, research.hypothesis_generated, verification.completed,
  strategy.generated, trade.executed, observation.completed, memory.stored, evolution.triggered
- Docs 01/14 specify `aios.<c#>.<event>` namespace with 9 topics + DLQ - DRIFT confirmed.

## 2. Decision (requires ADR-002)
Adopt namespace `aios.<community>.<event>` as canonical; short enum names retained in code but mapped:
```
EventTopic enum value == canonical wire topic
DATA_ACQUIRED            -> aios.c1.data_acquired
EVENT_DETECTED           -> aios.c10.event_detected          (new)
EXPECTATION_UPDATED      -> aios.c10.expectation_updated     (new)
SCENARIOS_PUBLISHED      -> aios.c10.scenarios_published     (new)
REGIME_CHANGED           -> aios.c10.regime_changed          (new)
HYPOTHESIS_GENERATED     -> aios.c2.hypothesis_generated
VERIFICATION_COMPLETED   -> aios.c3.verification_completed
STRATEGY_GENERATED       -> aios.c4.strategy_generated
OPPORTUNITY_RANKED       -> aios.c4.opportunity_ranked       (new)
PORTFOLIO_ALLOCATED      -> aios.c9.portfolio_allocated      (new)
RISK_DECISION_RECORDED   -> aios.risk.decision               (new)
RISK_EMERGENCY           -> aios.risk.emergency              (new, Tier-0)
ORDER_PROPOSED           -> aios.c5.order_proposed           (new)
ORDER_EXECUTED           -> aios.c5.order_executed           (replaces trade.executed; keep alias)
RECONCILIATION_FAILED    -> aios.c5.reconciliation_failed    (new, Tier-0)
OBSERVATION_COMPLETED    -> aios.c6.observation_completed
POSTMORTEM_CREATED       -> aios.c6.postmortem_created       (new)
MEMORY_STORED            -> aios.c7.memory_stored
PREDICTION_RECORDED      -> aios.c7.prediction_recorded      (new)
EVOLUTION_TRIGGERED      -> aios.c8.evolution_triggered
CHALLENGER_PROMOTED      -> aios.c8.challenger_promoted      (new)
LEDGER_POSTED            -> aios.c11.ledger_posted           (new)
TAX_EVENT                -> aios.c11.tax_event               (new)
COMPLIANCE_ALERT         -> aios.c11.compliance_alert        (new, Tier-0)
SYSTEM_HEALTH_ALERT      -> aios.system.health_alert         (new)
DATA_ANOMALY             -> aios.c1.data_anomaly             (new)
SYSTEM_DLQ               -> aios.system.dlq                  (per Doc 14)
```

## 3. Delivery Semantics (from Doc 14, ratified)
- Priority tiers: T0 critical (risk/compliance/reconciliation) zero-queue; T1 market data <10ms target;
  T2 research/strategy standard; T3 memory/batch background.
- At-least-once + consumer idempotency by payload UUID; retries 100ms->500ms->2s max 3; handler timeout 10s;
  failures -> DLQ with stack trace + replay support; Prometheus alarm on dlq_message_count.
- Every publish includes provenance block + lineage_parent_ids (see Data Model).

## 4. Cross-System Reaction Requirements (Directive 6 - the mesh property)
The following reactions MUST be wired (not advisory):
- RISK_EMERGENCY -> execution cancels all orders, blocks new submissions; strategy publishing suspended.
- DATA_ANOMALY / quality_state >= STALE on a symbol -> that symbol frozen for new strategies until FRESH.
- RECONCILIATION_FAILED -> trading halt for affected account; compliance alert.
- TAX_EVENT -> accounting + portfolio + reporting consumers triggered.
- MODEL_FAILURE / hallucination spike from an agent family -> C8 probation flag + C2 fallback to deterministic mode.

## 5. Local Mode Note
InMemoryEventBus remains valid for tests/dev; durable adapter (NATS) implements same BaseEventBus ABC.
wait_until_idle() stays test-only API.
