# AIOS Specification 1.17: Registries & Feature Store Specification

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification (Frozen)
- **Target System**: AIOS - Infrastructure, Model & Data Registries
- **Author**: AIOS System Architecture Team

---

## 1. System Overview & Purpose

To maintain deterministic repeatability, model governance, and efficient feature sharing across communities, AIOS establishes three core infrastructure services:

1. **Experiment Registry**: Tracks all research experiments, strategy backtests, and paper trading runs with full configuration lineage.
2. **Model Registry**: Governs LLM and quantitative model versions, latency SLAs, token pricing, provider routing, and deployment statuses.
3. **Feature Store**: Centralized, low-latency repository for engineered financial, macro, and sentiment features shared across Communities C1–C9.

---

## 2. Experiment Registry Specification

The Experiment Registry records every hypothesis evaluation, backtest run, and paper trading experiment to prevent duplicated effort and track research progress.

```python
class ExperimentRecord(BaseModel):
    experiment_id: str = Field(default_factory=generate_uuid)
    hypothesis_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=generate_utc_now)
    creator_agent_id: str = Field(..., min_length=1)
    configuration: dict[str, Any] = Field(
        ...,
        description="Strategy parameters, indicators used, asset symbols, and timeframes"
    )
    backtest_results: dict[str, float] = Field(
        ...,
        description="Sharpe ratio, max drawdown, win rate, profit factor, total PnL"
    )
    decision: Literal["APPROVED_FOR_PAPER", "REJECTED_VERIFICATION", "REJECTED_RISK", "RETIRED"] = Field(...)
    memory_links: dict[str, str] = Field(
        ...,
        description="Links to PostgreSQL audit ID, TimescaleDB run ID, and Qdrant embedding ID"
    )
```

### 2.1 Storage & Querying
- **Database Table**: `experiment_registry` in PostgreSQL (relational store).
- **Index Fields**: `hypothesis_id`, `creator_agent_id`, `decision`, `timestamp`.
- **Integration**: Community 2 (Research) queries the registry via Community 7 (Memory) before formulating new hypotheses to avoid re-testing failed configurations.

---

## 3. Model Registry Specification

The Model Registry manages all large language models (LLMs) and quantitative ML models deployed across AIOS communities.

```python
class ModelRecord(BaseModel):
    model_id: str = Field(..., description="Unique model string, e.g., 'gpt-4o', 'claude-3-5-sonnet'")
    provider: Literal["openai", "anthropic", "google", "ollama", "vllm"] = Field(...)
    version: str = Field(..., description="Model version tag or API snapshot ID")
    supported_tasks: list[Literal["research_debate", "fact_checking", "code_gen", "summarization", "embedding"]] = Field(...)
    avg_latency_ms: float = Field(..., ge=0.0)
    input_token_cost_per_1k: float = Field(..., ge=0.0)
    output_token_cost_per_1k: float = Field(..., ge=0.0)
    max_context_window: int = Field(..., gt=0)
    deployment_status: Literal["ACTIVE_PRIMARY", "ACTIVE_FALLBACK", "EVALUATION", "DEPRECATED"] = Field(...)
```

### 3.1 Model Governance Rules
- **Primary vs. Fallback Routing**: The AI Model Gateway (`litellm` interface in Section 4.1 of `11_supporting_systems.md`) queries the Model Registry to resolve active provider endpoints.
- **Cost & Latency Tracking**: Real-time token usage and latency metrics are updated in the registry to auto-route tasks to cost-effective models without breaching community SLAs.
- **Deprecated Model Isolation**: Deprecated models are immediately disabled in the registry, forcing all traffic to fallback providers.

---

## 4. Centralized Feature Store Specification

The Feature Store provides a single source of truth for engineered quantitative features, eliminating redundant computation across communities.

```
+-----------------------------------------------------------------------------------+
|                        CENTRALIZED FEATURE STORE ARCHITECTURE                     |
+-----------------------------------------------------------------------------------+
  [Ingestion / Compute Engine] --> Writes Features --> [TimescaleDB / Redis]
                                                               |
     +-----------------------+-----------------------+---------+
     |                       |                       |
     v                       v                       v
Community 1 (Data)     Community 2 (Research)   Community 4 (Strategy)
```

### 4.1 Feature Categories & Schema Definitions

| Feature Group | Entity | Examples | Storage Engine | Update Frequency |
| :--- | :--- | :--- | :--- | :---: |
| **Technical Indicators** | Symbol/Timeframe | RSI(14), EMA(20/50/200), MACD, ATR(14), Bollinger %B | TimescaleDB | Per Bar/Tick |
| **Macro Indicators** | Global/Currency | CPI YoY, Fed Funds Rate, Yield Curve Spread, NFP Delta | PostgreSQL | Daily/Monthly |
| **Sentiment Velocity** | Symbol | Sentiment Score (-1 to 1), Post Volume Velocity, Headline Impact | Redis / Timescale | 5-Minute Window |
| **Volatility Ratios** | Symbol | Realized Vol, Implied Vol Rank, Volatility Z-Score | TimescaleDB | 1-Minute Window |

### 4.2 Feature Serving API
Community agents access features via standard non-blocking queries:
- `get_historical_features(symbol, feature_names, start_time, end_time)` — Returns time-series DataFrame from TimescaleDB.
- `get_latest_features(symbol, feature_names)` — Returns low-latency (<5ms) feature vector from Redis cache.

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.17: Registries & Feature Store Specification**. It forms an integral part of **Phase 1.0 – Architecture Baseline (Frozen)**.
