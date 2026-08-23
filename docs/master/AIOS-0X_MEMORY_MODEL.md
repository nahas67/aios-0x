# AIOS-0X Memory Model
Version 1.0.0 | Current: RAM lists only. Target: tiered, verifiable, poisoning-resistant fabric.

## 1. Current State (verified)
MemoryAgent holds trade_receipts + observation_reports in Python lists; get_performance_summary() computes
win rate in-memory. Everything lost on restart. No vector store, no raw archive, no prediction ledger.

## 2. Target Memory Layers (Directive 22)

| Layer | Content | Store | Mutability |
|---|---|---|---|
| RAW | Every event payload exactly as received (all topics) | append-only event log (file sink -> JetStream) | IMMUTABLE |
| EPISODIC | Decision episodes: snapshot + participants + outcome links | PostgreSQL | append-only |
| SEMANTIC | Verified beliefs w/ source refs: lessons, regime notes | PG + Qdrant vectors | versioned (new version supersedes, old retained) |
| PROCEDURAL | How-to: playbooks, strategy specs, tool recipes | PG registries | versioned |
| STRATEGY | Per-strategy lifecycle history + performance windows | PG/Timescale | append-only |
| AGENT | Per-agent history: calls, outputs, scores, reputation events | PG | append-only |
| EVENT | Normalized world/market events w/ verification state | PG + Qdrant | append-only + state updates |
| REGIME | Market regime labels + transitions + per-regime stats | Timescale/PG | append-only |
| COUNTERFACTUAL | Alternatives considered vs realized outcomes | PG | append-only |
| ORGANIZATIONAL | ADRs, constitution versions, postmortem synthesis | git + PG | immutable via VCS |

## 3. Write Pipeline (poisoning defense - Directive 24)
```
RAW event -> VALIDATION (schema+quality) -> VERIFICATION (C3 for claims)
   -> BELIEF (confidence-tagged, sourced) -> SUMMARY (references evidence ids; never deletes raw)
```
Rules:
1. Summaries MUST store evidence_refs[]; a summary without lineage is rejected at write time.
2. Contradicted beliefs are superseded with pointer to contradiction, not erased.
3. Retrieval returns confidence + verification_state with every hit.
4. Periodic integrity job: recompute hashes of raw log; detect tampering.

## 4. Prediction Ledger (Directive 25) - FIRST-CLASS from Slice 1
Write BEFORE outcomes: prediction, probability, horizon, asset, regime, evidence_refs, agent_ids,
model_version, prompt_version, market_snapshot_ref.
Score AFTER: outcome, correct, brier_score, pnl_contribution, regime_bucket. Feeds agent reputation
and C8 calibration tuning.

## 5. Storage Tiers & Retention
Hot: cache (session, last quotes, hot features) - TTL hours/days.
Warm: current-year tables + vectors - full fidelity.
Cold: parquet-compressed history by year.
Archive: raw event log segments, checksummed, WORM-style.
Local SSD budget respected via downsampling policy (ticks->1m bars after 90d per Doc 09).

## 6. Interfaces (ABCs to add under core/)
BaseRawEventStore {append, tail, replay}
BaseVectorMemory {upsert, search_similar}          # Qdrant adapter later
BaseLedgerDB {insert_record, query_lineage}
BaseCache {get,set,ttl}
Retrieval API used by C2/C10/C8: search_similar_setups(), get_lessons(), get_regime_stats(),
get_prediction_history(agent_id|strategy_id).

## 7. Migration Steps
1. Slice 1: SQLite persistence of observations/predictions/postmortems + parquet market data. Raw file sink on bus.
2. Slice 2: embedded vector index for thesis/lesson similarity; retrieval wired into C2 debate context.
3. Scale phase: swap adapters to Postgres/Qdrant/Redis/NATS without contract changes (Doc 16 ABC rule).
