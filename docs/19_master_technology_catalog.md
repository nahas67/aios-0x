# AIOS Specification 1.19: Master Technology Catalog & Evaluation Matrix

## Document Control
- **Document Version**: 1.0.0
- **Status**: Active Catalog (Phase 2.0 Evaluation Matrix)
- **Target System**: AIOS - Open-Source Technology Selection
- **Author**: AIOS System Architecture Team

---

## 1. Catalog Purpose & Governance

The Master Technology Catalog records all open-source candidate tools, frameworks, databases, message brokers, and quantitative libraries evaluated for integration into AIOS during **Phase 2.0 (Technology Acquisition & Validation)**.

Every project candidate is scored against the 100-point evaluation rubric defined in [docs/16_technology_acquisition_framework.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/docs/16_technology_acquisition_framework.md) before receiving a status tag of `SELECTED`, `EVALUATING`, or `REJECTED`.

---

## 2. Evaluation Record Schema

Each entry in the catalog adheres to the following structured metadata format:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| **Candidate Name** | `string` | Name of the open-source project or repository. |
| **Category** | `enum` | Multi-Agent / Message Bus / Database & Vector / Ingestion / Backtest & Simulation. |
| **Status** | `enum` | `SELECTED` / `EVALUATING` / `REJECTED`. |
| **License** | `string` | Open-source license type (e.g. Apache 2.0, MIT, BSD-3, AGPL). |
| **Maturity** | `string` | Production readiness rating (e.g. Enterprise Ready, Battle-Tested, Emerging). |
| **AIOS Compatibility**| `score` | Rubric score (0–100) based on Python 3.11+ async support and ABC fit. |
| **Replace Later?** | `boolean` | Indicates if the dependency can be cleanly swapped via ABC wrappers. |
| **Notes / Verdict** | `string` | Qualitative summary of evaluation findings and decision rationale. |

---

## 3. Initial Phase 2.0 Technology Evaluation Matrix

```
+---------------------------------------------------------------------------------------------------------------------------------------------+
|                                                  AIOS OPEN-SOURCE EVALUATION MATRIX                                                         |
+---------------------------------------------------------------------------------------------------------------------------------------------+
| Candidate Name     | Category             | Status     | License    | Maturity     | Score | Replace Later? | Notes / Rationale             |
| ------------------ | -------------------- | ---------- | ---------- | ------------ | ----- | -------------- | ----------------------------- |
| LangGraph          | Multi-Agent Orchestr.| EVALUATING | MIT        | High         | 88    | Yes            | Strong DAG & state graph fit. |
| LlamaIndex         | Multi-Agent / RAG    | EVALUATING | MIT        | High         | 84    | Yes            | Excellent memory & indexing.  |
| CrewAI             | Multi-Agent Orchestr.| EVALUATING | MIT        | Medium       | 78    | Yes            | Role-based agent simulation.  |
| AutoGen            | Multi-Agent Orchestr.| EVALUATING | MIT        | Medium-High  | 76    | Yes            | Conversation patterns.        |
| ------------------ | -------------------- | ---------- | ---------- | ------------ | ----- | -------------- | ----------------------------- |
| NATS JetStream     | Message Bus & Stream | EVALUATING | Apache 2.0  | Enterprise   | 94    | Yes            | Sub-ms latency, streaming persistence. |
| Redis Streams      | Message Bus & Cache  | EVALUATING | RSALv2/SSPL | Enterprise   | 90    | Yes            | High-speed transient pub/sub. |
| Apache Kafka       | Message Bus & Stream | EVALUATING | Apache 2.0  | Enterprise   | 82    | Yes            | High throughput, heavy infra. |
| ------------------ | -------------------- | ---------- | ---------- | ------------ | ----- | -------------- | ----------------------------- |
| PostgreSQL/Timescale| Relational & Time-Ser| EVALUATING | PostgreSQL  | Enterprise   | 96    | Yes            | Essential relational & ticks. |
| Qdrant             | Vector Database      | EVALUATING | Apache 2.0  | High         | 92    | Yes            | Rust core, high perf vectors. |
| Milvus             | Vector Database      | EVALUATING | Apache 2.0  | Enterprise   | 86    | Yes            | Distributed enterprise scale. |
| ------------------ | -------------------- | ---------- | ---------- | ------------ | ----- | -------------- | ----------------------------- |
| CCXT               | Market Ingestion     | EVALUATING | MIT        | Battle-Tested| 95    | Yes            | Standard crypto gateway.      |
| Alpaca SDK         | Market Ingestion     | EVALUATING | Apache 2.0  | High         | 88    | Yes            | US Equities & Paper REST API. |
| Polygon.io         | Market Ingestion     | EVALUATING | Commercial | High         | 86    | Yes            | High quality ticks & bars.    |
| ------------------ | -------------------- | ---------- | ---------- | ------------ | ----- | -------------- | ----------------------------- |
| NautilusTrader     | Backtest & Execution | EVALUATING | LGPL-3.0   | High         | 92    | Yes            | High-performance Rust core.   |
| LEAN (QuantConnect)| Backtest & Execution | EVALUATING | Apache 2.0  | Battle-Tested| 88    | Yes            | Multi-asset C# backtester.    |
| VectorBT           | Backtest & Simulation| EVALUATING | Apache 2.0  | Medium-High  | 85    | Yes            | NumPy/Numba vectorized testing|
+---------------------------------------------------------------------------------------------------------------------------------------------+
```

---

## 4. Document Verification & Compliance

This catalog is updated dynamically throughout **Phase 2.0 (Technology Acquisition & Validation)** as candidate benchmarks are finalized. Decisions are recorded in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md).
