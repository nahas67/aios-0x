# ADR-002: Canonical Event Topics, Provenance Fields & Honesty Invariants

## Context

Phase 0 discovery (2026-08-23) verified defects that block trustworthy operation:

1. **Topic naming drift** — code used short dotted topics (`data.acquired`) while frozen
   Docs 01/14 specify `aios.<community>.<event>`.
2. **No provenance** — payloads carried no source/quality/simulation metadata, making it
   impossible to enforce freshness gates or Constitution Law 1.3 (simulated-must-be-tagged).
3. **Fabricated outcomes (D1)** — `ObservationAgent.on_trade_executed` invented exits at
   `fill_price * 1.03`, guaranteeing fictitious profits in every closed-loop run.
4. **Cross-community import (D2)** — `EvolutionAgent` imported `MemoryAgent` from c7,
   violating `.cursorrules` isolation and Doc 01 state-isolation rules.
5. **Silent override (D7)** — `VerificationReport` validator discarded explicitly provided
   `is_verified` values.
6. **Invented market state (D3)** — `StrategyAgent` defaulted missing prices to `100.0`.

## Decision

1. **Canonical topics**: `EventTopic` values adopt `aios.<community>.<event>` (member names
   unchanged). `EventTopic` becomes a `StrEnum`. Mapping:
   - DATA_ACQUIRED → `aios.c1.data_acquired`
   - HYPOTHESIS_GENERATED → `aios.c2.hypothesis_generated`
   - VERIFICATION_COMPLETED → `aios.c3.verification_completed`
   - STRATEGY_GENERATED → `aios.c4.strategy_generated`
   - TRADE_EXECUTED → `aios.c5.order_executed`
   - OBSERVATION_COMPLETED → `aios.c6.observation_completed`
   - MEMORY_STORED → `aios.c7.memory_stored`
   - EVOLUTION_TRIGGERED → `aios.c8.evolution_triggered`
   New topics must extend this scheme (see docs/master/AIOS-0X_EVENT_MODEL.md).

2. **Provenance & lineage on data-bearing payloads**: new `DataProvenance` contract
   (source_id, source_type MARKET|NEWS|MACRO|ONCHAIN|SIM, retrieved_at, data_timestamp,
   quality_state LIVE|FRESH|AGING|STALE|EXPIRED|UNKNOWN|CORRUPTED, quality_score, license,
   content_hash). `MarketDataPayload` and `TradeExecutionReceipt` gain optional `provenance`,
   required-default `is_simulated: bool = False`, and `lineage_parent_ids: list[str]`.
   Rollout to remaining payloads follows the same pattern in later phases.

3. **Typed cross-community dependency contract**: new `PerformanceSummary` payload.
   Communities exchange contracts only; C8 receives performance via an injected
   `Callable[[], PerformanceSummary]` provider, never by importing another community's class.

4. **Honesty invariants (enforced by tests)**:
   - Exit prices originate exclusively from caller-supplied market prices
     (`on_market_price_update` / explicit `observe_trade_outcome`). Fabricating an exit is a
     constitutional violation; the fabrication detector canary in CI encodes this.
   - Missing market state ⇒ NO TRADE (None), never a default price.
   - Paper fills debit cash; insufficient funds reject the order without publishing;
     settlement occurs at actual market prices (`PaperEngine.on_market_price`).
   - `is_verified` respects explicitly supplied values; auto-computation applies only when
     the field is absent.

## Status

- State: ACCEPTED
- Date: 2026-08-23
- Authors: AIOS System Architecture Team

## Consequences

Positive:
- Wire format matches frozen Docs 01/14; durable-bus migration unblocked.
- Quality/freshness gating and Law 1.3 tagging become mechanically enforceable.
- Closed-loop results reflect reality (deterministic sim now yields honest negative PnL
  when slippage exceeds movement), restoring integrity of all future learning loops.

Negative:
- Breaking change for any consumer of old topic strings or `get_performance_summary()`
  dict returns (all internal call sites updated; no external consumers exist).
- Provenance obligations now apply to every future adapter (documented cost of integrity).

## Compliance & Verification

- `tests/test_event_bus.py::test_event_topic_enum_values` pins canonical values.
- `tests/test_contracts.py` pins provenance defaults and D7 behavior.
- `tests/test_closed_loop_feedback.py::test_master_closed_loop_8_community_pipeline`
  proves observations require real price input and PnL matches computed values.
- `grep` guard: no `communities.cX` import appears inside another community package.
