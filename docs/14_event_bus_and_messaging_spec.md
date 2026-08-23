# AIOS Specification 1.14: Event Bus & Messaging Architecture Specification

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification (Frozen)
- **Target System**: AIOS - Inter-Community Messaging Architecture
- **Author**: AIOS System Architecture Team

---

## 1. System Overview & Messaging Paradigm

The AIOS Event Bus serves as the primary asynchronous communication backbone connecting all 9 specialized communities and supporting systems. To maintain absolute decoupling, communities NEVER invoke each other via direct synchronous method calls. All inter-community state transitions occur through strongly-typed event publications on the Event Bus.

---

## 2. Event Topics Taxonomy & Priorities

Event topics follow a standardized namespace convention: `aios.<community_id>.<event_name>`.

```
+-----------------------------------------------------------------------------------+
|                        AIOS EVENT BUS TOPIC TAXONOMY                              |
+-----------------------------------------------------------------------------------+
  Topic Namespace                       Priority Tier   Payload Contract
  ----------------------------------------------------------------------------------
  aios.c1.market_data                   HIGH (Tier 1)   MarketDataPayload
  aios.c2.hypothesis_generated          MEDIUM (Tier 2) CandidateHypothesis
  aios.c3.verification_completed        HIGH (Tier 1)   VerificationReport
  aios.c4.strategy_generated            HIGH (Tier 1)   StrategySpecification
  aios.c9.portfolio_allocation          CRITICAL (Tier 0) PortfolioAllocationPlan
  aios.c5.trade_executed                CRITICAL (Tier 0) TradeExecutionReceipt
  aios.c6.observation_completed         MEDIUM (Tier 2) ObservationReport
  aios.c7.memory_stored                 LOW (Tier 3)    MemoryStoredEvent
  aios.c8.evolution_triggered           LOW (Tier 3)    EvolutionSignal
+-----------------------------------------------------------------------------------+
```

### 2.1 Topic Priority Tiers
- **Tier 0: Critical (Real-Time Execution & Risk)** — Handled with zero-queue buffering. Dedicated worker threads.
- **Tier 1: High (Market Data & Verified Strategy)** — High throughput, sub-10ms target latency.
- **Tier 2: Medium (Research & Observation)** — Standard queue processing.
- **Tier 3: Low (Memory Indexing & Evolution)** — Batch-processed background events.

---

## 3. Message Queue Guarantees, Retries, & Dead Letter Queue (DLQ)

### 3.1 Delivery Guarantees
- **At-Least-Once Delivery**: Subscribers must explicitly acknowledge (`ACK`) message processing upon successful validation and execution.
- **Idempotent Handling**: All message consumers enforce idempotency using the message payload's unique UUID (`hypothesis_id`, `report_id`, `strategy_id`, `execution_id`, `observation_id`). Duplicate messages are safely ignored.

### 3.2 Retry Policy & Exponential Backoff
When a subscriber handler encounters an unhandled exception or processing failure, the Event Bus executes an automated retry policy:

```
[Failed Processing] -> Retry 1 (100ms delay) -> Retry 2 (500ms delay) -> Retry 3 (2000ms delay)
                                                                               |
                                                                        [All Retries Fail]
                                                                               v
                                                                    [Route to Dead Letter Queue]
```

- **Max Retry Attempts**: 3 attempts.
- **Backoff Formula**: Delay $T_{retry} = T_{base} \cdot 2^{attempt} + \text{jitter}$ (where $T_{base} = 100\text{ms}$).
- **Timeout per Handler**: 10.0 seconds. Handlers exceeding this limit are cancelled and re-queued.

### 3.3 Dead Letter Queue (DLQ) Handling
Messages that fail all retry attempts are diverted to `aios.system.dlq` for isolated auditing:
- **DLQ Payload Wrapping**: The original payload is wrapped with exception stack trace, subscriber handler identity, timestamp, and retry count.
- **DLQ Alarm Trigger**: Publishing to the DLQ emits an immediate system alert and increments the `dlq_message_count` metric on Prometheus dashboard.
- **Manual/Automated Replay**: DLQ entries can be inspected via Community 7 (Memory) and manually replayed once the underlying issue is resolved.

---

## 4. Operational Modes: Local vs. Enterprise

```
+-----------------------------------------------------------------------------------+
|                     EVENT BUS DUAL OPERATIONAL MODES                              |
+-----------------------------------------------------------------------------------+
| OPERATIONAL MODE | UNDERLYING ENGINE      | PERSISTENCE  | THROUGHPUT TARGET  |
| ---------------- | ---------------------- | ------------ | ------------------ |
| Local Prototype  | InMemoryEventBus       | Python Queue | 10,000+ msgs/sec   |
|                  | (asyncio.Queue)        | (In-Memory)  | (In-Process)       |
| ---------------- | ---------------------- | ------------ | ------------------ |
| Enterprise Prod  | NATS JetStream /       | Disk-Backed  | 100,000+ msgs/sec  |
|                  | Redis Streams          | Stream Store | (Distributed Pods) |
+-----------------------------------------------------------------------------------+
```

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](CHECKPOINT.md) under **Doc 1.14: Event Bus & Messaging Architecture Specification**. Implementation abstraction resides in [event_bus.py](core/event_bus.py).
