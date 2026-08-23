# AIOS-0X Data Model
Version 1.0.0 | Covers: contracts today, required extensions, storage mapping

## 1. Current Contracts (schemas/contracts.py - verified)
- PriceData (OHLCV, gt=0), NewsSentiment (-1..1, source)
- MarketDataPayload {timestamp, symbol, timeframe, price_data, news_sentiment?, metadata}
- CandidateHypothesis {hypothesis_id, created_at, symbol, thesis, supporting[], counter[], timeframe, expected_risk_reward_ratio}
- VerificationReport {report_id, hypothesis_id, confidence_score 0-100, is_verified(auto >=70), verified_claims, flagged_hallucinations, verification_notes}
- StrategySpecification {strategy_id, hypothesis_id, symbol, action BUY|SELL|HOLD, entry/stop/take_profit, position_size_pct; direction validators}
- TradeExecutionReceipt {execution_id, strategy_id, symbol, fill_price, filled_quantity, slippage, fees, executed_at}
- ObservationReport {observation_id, execution_id, actual_pnl, predicted_vs_actual_deviation, lessons_learned}

## 2. Required Contract Extensions (ADR-002 scope)

### 2.1 Provenance & Quality (every payload gains)
```
provenance: DataProvenance {
  source_id, source_type(MARKET|NEWS|MACRO|ONCHAIN|SIM),
  retrieved_at: datetime(UTC), data_timestamp: datetime(UTC),
  license, quality_state(LIVE|FRESH|AGING|STALE|EXPIRED|UNKNOWN|CORRUPTED),
  quality_score: float 0-100, content_hash
}
is_simulated: bool = False          # constitutional tag
lineage_parent_ids: list[str]        # audit-graph edges
decision_snapshot_ref: str | None    # info-state at decision time (Directive 76)
```

### 2.2 New Payloads
- EventPayload (C10): event_id, type, severity, source, confidence, affected_entities/assets, expected_duration, estimated_impact, verification_state
- ExpectationSnapshot: consensus, options_implied?, positioning?, actual, surprise_magnitude, price_reaction
- ScenarioSet: scenarios[] {name, probability, impact, horizon, invalidation_condition}
- OpportunityScore: expected_return, probability, costs, liquidity, alpha_decay_halflife, correlation_flags, tail_risk, composite_rank
- PortfolioAllocationPlan (per Doc 15): allocations[], portfolio_status HEALTHY|WARNING|CAUTION|CRITICAL_HALT
- RiskDecision: approved, reasons[], adjusted_size, emergency_flag, governor_version, rule_eval_trace[]
- OrderRequest/OrderUpdate/FillRecord (C5): full order lifecycle incl. partial fills, client_order_id idempotency
- LedgerEntry (C11): double-entry posting {account_debit, account_credit, amount_cents(int!), currency, tax_lot_refs[]}
- TaxLot / TaxComputation (C11): lot_id, acquisition/disposal, cost_basis method, holding_period, jurisdiction_rule{law_citation, effective_date}, output, confidence
- PredictionRecord (ledger): prediction, probability, confidence, horizon, asset, regime, evidence_refs, agents, model+prompt versions, market_state_ref -> later scored (Brier/calibration)

## 3. Storage Mapping (polyglot per Doc 09/Directive 55)

| Store | Local Phase | Scale Phase | Contents |
|---|---|---|---|
| Relational | SQLite aios_local.db | PostgreSQL 16 | ledgers, registries, experiment records, audit graph nodes, tax tables |
| Time-series | SQLite + parquet | TimescaleDB hypertables | price ticks/bars, indicators, slippage_log, pnl_series |
| Vector | embedded (e.g. sqlite-vec/lancedb) | Qdrant | research_theses, debate_transcripts, postmortem_lessons, market_regimes |
| Object/files | parquet on disk | S3-compatible | raw immutable history, benchmark datasets |
| Cache | dict | Redis 7 | session state, rate counters, hot features (<5ms serving) |
| Event log | InMemoryEventBus + file sink | NATS JetStream | append-only all topics, replayable |

## 4. Integrity Rules
1. Money amounts as integer minor units internally (floats only at presentation) to prevent drift.
2. All timestamps timezone-aware UTC ISO 8601.
3. Raw memory immutable; corrections are new records with lineage pointers (never overwrite).
4. Every derived number traceable to inputs via lineage ids (Directive 92).
5. No look-ahead: replay/sim loaders enforce as-of semantics at fetch boundary.

## 5. Symbol & Timeframe Conventions
Unified `<BASE>/<QUOTE>` normalization per Doc 02 (BTCUSDT -> BTC/USD); timeframes enum: 1m,5m,15m,1h,4h,1d.
