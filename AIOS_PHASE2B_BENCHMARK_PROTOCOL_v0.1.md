# AIOS Phase 2B — Benchmark Protocol Specification (v0.1)

**Document Version**: 0.1.0  
**Status**: Authoritative Benchmark Protocol Specification (Pre-Execution / Pre-Selection — FORMAL SELECTION = 0)  
**Created**: 2026-08-19  
**Authoritative References**: Frozen Phase 1 Architecture (ADR-001) & Frozen Phase 2 Research Artifacts  

---

## 1. Governance & Authoritative Inputs

This Benchmark Protocol Specification establishes the rigorous, reproducible, and objective methodology for generating empirical performance, quality, security, and architectural evidence prior to formal technology selection for the AIOS platform.

### 1.1 Authoritative Inputs
This protocol is derived strictly from and constrained by the following frozen baseline artifacts:
1. **Frozen Phase 1 Architecture Baseline** (`ADR-001`)
2. **Frozen Phase 2 Capability Matrix** (`AIOS_PHASE2_CAPABILITY_MATRIX.md`)
3. **Frozen Phase 2 Selection Ledger** (`AIOS_PHASE2_SELECTION_LEDGER.md`)
4. **Frozen Phase 2 Candidate Technology Stack** (`AIOS_PHASE2_CANDIDATE_TECHNOLOGY_STACK.md`)
5. **Frozen Phase 2 Reconciliation Report** (`AIOS_PHASE2_RECONCILIATION_REPORT.md`)
6. **Frozen Phase 2 Audit Summary** (`AIOS_PHASE2_AUDIT_SUMMARY.md`)

### 1.2 Mandatory Scope & Governance Boundaries
- **Phase 2 Freeze Authoritative**: Phase 2 research is frozen. No new open-source candidates shall be added, removed, or modified during protocol design or benchmark execution.
- **73-Candidate Ledger Immutable**: The 73-candidate research universe, single primary dispositions, scores, and capability mappings are fixed.
- **FORMAL SELECTION = 0**: This protocol defines *how evidence is generated*. It does **NOT** select technologies, declare winners, or modify candidate dispositions. Formal technology selection remains strictly reserved for post-benchmark Architecture Decision Records (ADRs).
- **Phase 3 Hold**: No Phase 3 production implementation or actual benchmark execution occurs within this protocol specification phase.

---

## 2. Core Benchmark Principles

All evaluations conducted under this protocol must adhere to ten mandatory benchmark principles:

1. **FAIRNESS**: Competing candidates receive identical, normalized workloads, hardware, and runtime environments.
2. **REPRODUCIBILITY**: Every benchmark run must be fully reproducible by independent engineers using stored datasets, lockfiles, configuration manifests, and random seeds.
3. **SAME INPUT**: Where comparison is intended, candidates execute against identical historical or synthetic datasets.
4. **SAME ENVIRONMENT**: Host hardware, OS, CPU pinning, memory, kernel configuration, runtime versions, and background load must be documented and controlled.
5. **MEASURED EVIDENCE**: Decisions are driven solely by empirical, machine-readable telemetry and automated assertions, never subjective opinions.
6. **MULTI-DIMENSIONAL EVALUATION**: Throughput alone is insufficient. Candidates are evaluated across latency distributions, memory overhead, correctness, security, and operational complexity.
7. **ARCHITECTURAL FIT**: Benchmark performance cannot override frozen Phase 1 architectural rules, safety invariants, or authority boundaries.
8. **REPLACEABILITY**: Benchmarks must evaluate candidates through standardized AIOS Abstract Base Class (ABC) interfaces, without rewarding pre-existing wrapper code.
9. **NO BENCHMARK MANIPULATION**: Candidates must not receive proprietary, undocumented, or unstandardized tuning. Any vendor-recommended optimization must be documented and made available equally where applicable.
10. **VALIDITY OF NEGATIVE RESULTS**: Benchmark failures, latency spikes, state corruptions, and security gaps are high-value empirical evidence and must be fully documented.

---

## 3. Evaluation Classification Taxonomy

Evaluations are explicitly categorized into seven distinct evaluation types:

| Evaluation Type Code | Evaluation Type Name | Primary Objective & Scope |
|----------------------|----------------------|---------------------------|
| **PERF** | **Performance Benchmark** | Empirical measurement of throughput, latency distributions ($p_{50}, p_{95}, p_{99}$), CPU utilization, memory footprint, startup time, and recovery rate under synthetic or historical load. |
| **FUNC** | **Functional Compatibility Test** | Automated verification that candidate software satisfies mandatory functional invariants, deterministic execution rules, state consistency, and API contracts. |
| **INTG** | **Integration Test** | Assessment of candidate connectivity, adapter overhead, type conversion latency, and clean encapsulation behind AIOS Abstract Base Class (ABC) boundaries. |
| **SECU** | **Security Evaluation** | Empirical and architectural audit of isolation boundaries, policy enforcement latency, authorization bypass resistance, secret handling, and failure-mode safety. |
| **LEGL** | **License / Legal Review** | Legal compliance audit of license obligations (LGPL-3, AGPL-3, GPL-3, BSL), copyleft contamination risks, dynamic linking boundaries, and commercial deployment terms. |
| **ARCH** | **Architectural Evaluation** | Qualitative and structural review of operational complexity, deployment overhead, dependency tree weight, replaceability, and maintenance burden. |
| **QUAL** | **Quality Evaluation** | Quantitative measurement of output precision, recall, retrieval relevance, chunking fidelity, test-case generation quality, and hallucination detection accuracy. |

Every test executed within a benchmark group must explicitly specify its primary Evaluation Type Code.

---

## 4. Benchmark Group Specifications

Evaluations are structured into the 11 frozen Phase 2 benchmark groups across 3 operational tiers.

### Tier 1 — Architecture-Critical Competitive Benchmarks

#### GROUP A — Multi-Agent Orchestration Architecture
- **Evaluation Types**: `PERF`, `FUNC`, `INTG`, `ARCH`
- **Baseline Candidate**: **LangGraph**
- **Competing Candidates**: **CrewAI**, **Microsoft Agent Framework**, **OpenGeni**
- **Evaluation Question**: Can competing frameworks execute cyclic $C_8 \rightarrow C_2$ agent feedback loops and non-linear multi-agent debate DAGs without state corruption, memory leaks, or unhandled latency spikes compared to LangGraph?
- **Workload / Test Focus**: Cyclic DAG execution (Bull/Bear debate loop), state checkpointer latency, concurrent agent session scaling (10 to 1,000 sessions), fault recovery upon node failure.

#### GROUP B — Backtesting & Simulation Architecture
- **Evaluation Types**: `PERF`, `FUNC`, `ARCH`, `LEGL`
- **Primary Backtest Competition**: **NautilusTrader** (Baseline) vs **LEAN (QuantConnect)** vs **VectorBT**
- **Simulation / Digital-Twin Reference**: **ABIDES**
- **Evaluation Question**: 
  1. *Primary Competition*: Which backtest engine delivers the optimal balance of historical event processing throughput, transaction-cost/fee fidelity, slippage modelling, walk-forward validation (90/30 window), and memory efficiency?
  2. *Simulation Reference*: Does ABIDES materially enhance AIOS digital-twin / market-microstructure simulation capabilities beyond standard historical backtesters?
- **Critical Architectural Rule**: ABIDES is evaluated strictly as a *Simulation Reference* for synthetic market generation and agent-based microstructure modeling. It is **NOT** treated as a direct winner/loser against NautilusTrader, LEAN, or VectorBT.
- **Workload / Test Focus**: 50,000,000 tick processing throughput, multi-asset order matching (equities & crypto), walk-forward parameter optimization sweep, memory consumption profiling, LGPL-3 dynamic linking legal assessment (NautilusTrader).

#### GROUP C — Event Bus & Async Messaging Architecture
- **Evaluation Types**: `PERF`, `FUNC`, `INTG`, `SECU`
- **Baseline Candidate**: **NATS JetStream**
- **Competing Candidates**: **RedPanda**, **Redis Streams**
- **Evaluation Question**: Does RedPanda or Redis Streams offer superior $p_{99}$ latency, subject-based routing efficiency, and dead-letter queue (DLQ) handling compared to NATS JetStream under institutional market feed loads?
- **Workload / Test Focus**: High-throughput pub/sub load test (10,000 to 100,000 msg/sec), payload size variations (512B to 64KB), subject wildcard routing, node crash recovery, backpressure handling, disk persistence throughput.

---

### Tier 2 — Candidate-Specific Comparative Evaluations

#### GROUP D — Portfolio Intelligence & Risk Optimization
- **Evaluation Types**: `PERF`, `FUNC`, `QUAL`
- **Baseline Candidate**: **PyPortfolioOpt**
- **Competing Candidates**: **Riskfolio-Lib**, **Open Source Risk Engine (ORE)**
- **Evaluation Question**: Does Riskfolio-Lib or ORE provide numerical stability, CVaR accuracy, and risk-budgeting performance superior to PyPortfolioOpt under illiquid asset regimes and market crash scenarios?
- **Workload / Test Focus**: Fractional Kelly criterion sizing, Mean-Variance Optimization (MVO), Hierarchical Risk Parity (HRP), CVaR matrix calculations across 500-asset correlation matrices.

#### GROUP E — Experiment & Model Registry Substrate
- **Evaluation Types**: `PERF`, `INTG`, `ARCH`
- **Baseline Candidate**: **MLflow**
- **Competing Candidates**: **ClearML**
- **Evaluation Question**: Does ClearML offer materially lower model resolution latency and artifact versioning overhead than MLflow for `litellm` model routing and `ExperimentRecord` lineage tracking?
- **Workload / Test Focus**: Concurrent metadata log writing (100 parallel workers), artifact upload/download throughput, model version resolution latency, lineage graph query overhead.

#### GROUP F — Decision Provenance & Audit Graph
- **Evaluation Types**: `PERF`, `FUNC`, `ARCH`, `LEGL`
- **Baseline Architecture**: **PostgreSQL Recursive CTE Graph**
- **Competing Candidates**: **Neo4j**, **NebulaGraph**
- **Evaluation Question**: Can native PostgreSQL recursive CTE queries satisfy line-of-sight decision provenance queries ($C_5 \rightarrow C_2 \rightarrow C_1$) within sub-50ms latency without requiring the operational overhead and license risk of a dedicated graph database?
- **Workload / Test Focus**: Provenance DAG depth traversal (1 to 10 hops), 1,000 concurrent lineage lookup requests, write transaction latency during continuous market ingestion, Neo4j GPL-3 legal risk review.

#### GROUP I — Memory & Retrieval Architecture
- **Evaluation Types**: `QUAL`, `PERF`, `ARCH`
- **Baseline Architecture**: **Direct Qdrant Integration** (Vector Storage Layer)
- **Alternative Architecture**: **Qdrant + LlamaIndex** (Retrieval Abstraction Layer)
- **Evaluation Question**: Does adding LlamaIndex as an abstraction layer on top of raw Qdrant vector storage materially improve context retrieval precision, hybrid search quality, metadata payload filtering, and developer productivity enough to justify the additional abstraction complexity, dependency weight, and latency overhead?
- **Critical Architectural Rule**: Qdrant and LlamaIndex are **NOT** direct substitutes. Qdrant serves as the underlying vector storage engine. LlamaIndex is evaluated strictly as an optional indexing and retrieval abstraction layer over Qdrant.
- **Workload / Test Focus**: 768-dimensional dense vector insertion (100,000 vectors), metadata payload filter query latency, hybrid dense/sparse retrieval recall ($R@10$), chunking flexibility, context assembly latency.

#### GROUP J — Durable Workflow Execution Substrate
- **Evaluation Types**: `FUNC`, `PERF`, `ARCH`
- **Baseline Architecture**: **LangGraph Checkpointers / NATS JetStream State**
- **Alternative Candidate**: **Temporal**
- **Evaluation Question**: Does Temporal provide long-running state durability, step replayability, and execution safety for multi-day $C_8$ agent evolution loops superior to lightweight LangGraph checkpointers with NATS persistence?
- **Workload / Test Focus**: Multi-day simulated workflow state retention, worker process force-kill and resumption, execution replay determinism, cluster operation overhead.

#### GROUP K — LLM Quality, Validation & Safety Architecture
- **Evaluation Types**: `QUAL`, `FUNC`, `SECU`
- **AIOS Authoritative Baseline**: **Pydantic Schemas** + **AIOS Deterministic Risk/Safety Firewall**
- **Optional Supporting Technologies**: **DeepEval**, **Guardrails AI**
- **Evaluation Question**: Can DeepEval or Guardrails AI materially improve LLM evaluation, test-case generation, or output validation quality without weakening, delaying, or overriding the authoritative deterministic AIOS Risk Firewall?
- **Critical Architectural Rule**: DeepEval and Guardrails AI **MUST NEVER** replace or override the deterministic AIOS Risk Firewall. The AIOS deterministic firewall (`core/risk_firewall.py`) remains authoritative for risk limits, trade authorization, execution policies, and governance rules. Supporting tools may only provide offline evaluation, validation evidence, or quality auditing.
- **Workload / Test Focus**: Hallucination detection precision/recall, structured output schema validation latency, policy violation assertion rate, false positive/negative trade rejection rates.

---

### Tier 3 — Security & Data Provider Evaluations

#### GROUP G — Security & Policy Enforcement Architecture
- **Evaluation Types**: `SECU`, `PERF`, `ARCH`
- **Baseline Architecture**: **OpenBao (Vault)** + **Open Policy Agent (OPA)** Sidecar
- **Alternative Architecture**: **Embedded Custom Python Security Middleware**
- **Evaluation Question**: Does sidecar security isolation (OpenBao/OPA) justify its deployment complexity and network latency compared to an embedded Python security wrapper across secret management, policy enforcement, and auditability?
- **Workload / Test Focus**: Secret retrieval latency under 5,000 req/sec, Rego policy enforcement overhead per trade order, failure recovery behavior (fail-closed validation), emergency bypass audit logging.

#### GROUP H — Supplementary Market Data Provider Evaluation
- **Evaluation Types**: `FUNC`, `INTG`, `QUAL`
- **Baseline Interfaces**: **CCXT** (Crypto) + **Alpaca SDK** (Equities)
- **Supplementary Candidates**: **Twelve Data**, **Finnhub**, **Polygon.io (client-python)**, **Alpha Vantage**
- **Evaluation Question**: Do supplementary data providers materially enhance market feed coverage, tick reliability, corporate action data, or news/sentiment velocity beyond the core feeds provided by CCXT and Alpaca?
- **Critical Architectural Rule**: CCXT and Alpaca are frozen Phase 1 primary execution and data interfaces. Supplementary providers are evaluated only as additive data source adapters for Community 1.
- **Workload / Test Focus**: WebSocket feed stability over 24-hour continuous stream, rate-limit resilience, REST tick/bar historical backfill completeness, news sentiment payload latency.

---

## 5. Standard Test Environment Policy

To guarantee strict reproducibility, all benchmark executions must record and lock the environment parameters prior to running tests.

### 5.1 Environment Specification Form
If the physical execution environment is not finalized at protocol creation, the benchmark harness must output the standard environment block upon execution:

```yaml
environment_recording:
  status: "RECORDED_AT_BENCHMARK_EXECUTION"
  hardware:
    cpu_model: "RECORD_AT_RUNTIME"
    cpu_architecture: "x86_64 / arm64"
    physical_cores: 0
    logical_threads: 0
    ram_gb: 0.0
    storage_type: "NVMe SSD / Enterprise SAN"
    gpu_model: "N/A or GPU_MODEL"
  software:
    os_name: "Windows / Linux"
    os_kernel: "RECORD_AT_RUNTIME"
    python_version: "3.11.x"
    docker_version: "RECORD_AT_RUNTIME"
  dependencies:
    lockfile_sha256: "RECORD_AT_RUNTIME"
  configuration:
    concurrency_workers: 0
    cpu_affinity_mask: "RECORD_AT_RUNTIME"
```

### 5.2 Environmental Control Rules
1. **Isolation**: Benchmarks must run on dedicated physical or virtual nodes with background processes disabled.
2. **CPU Pinning**: Multi-threaded performance benchmarks must use explicit CPU core affinity pinning.
3. **Power Plan**: Host systems must execute under high-performance power profiles (no CPU frequency scaling during measurement).

---

## 6. Dataset Policy & Workload Generation

### 6.1 Historical Market Data Standards
Where historical market data is required (Groups B, H), all competing candidates must execute against identical dataset snapshots.

- **Storage Format**: Apache Parquet files or TimescaleDB hypertable dumps.
- **Timestamp Standard**: UTC nanosecond timestamps (`int64`).
- **Asset Universe**:
  - *Crypto Universe*: `BTC/USDT`, `ETH/USDT`, `SOL/USDT` (1-sec ticks, 1-min bars).
  - *Equities Universe*: `AAPL`, `MSFT`, `SPY`, `QQQ` (1-sec ticks, 1-min bars).
- **Time Window**: Standardized 2-year rolling window (e.g., `2024-01-01T00:00:00Z` to `2025-12-31T23:59:59Z`).
- **Data Integrity & Normalization**:
  - Missing tick policy: Forward-fill zero-volume bid/ask for backtest engines.
  - Corporate action policy: Split- and dividend-adjusted prices applied identically.
  - Dataset Checksum: Mandatory SHA-256 hash recorded in test metadata.

### 6.2 Synthetic Workload Standards
For messaging, vector memory, LLM quality, and graph benchmarks (Groups A, C, D, E, F, I, J, K), synthetic workloads must be generated deterministically.

- **Random Number Generation**: Pseudo-Random Number Generators (PRNG) must use fixed integer seeds (e.g., `SEED = 42`).
- **Data Distribution**: Event sizes, inter-arrival times, and payload characteristics must follow documented distributions (e.g., Poisson arrival process for messaging, Gaussian vector embeddings for memory).

---

## 7. Multi-Dimensional Metric Framework

Candidate metrics are divided by Evaluation Type:

### 7.1 Performance Metrics (`PERF`)
- **Throughput**: Operations per second ($\text{ops/sec}$), Messages per second ($\text{msg/sec}$), Ticks processed per second ($\text{ticks/sec}$).
- **Latency Distribution**: $p_{50}$ (Median), $p_{95}$ (95th Percentile), $p_{99}$ (99th Percentile), and Worst-Case Latency in milliseconds ($\text{ms}$) or microseconds ($\mu\text{s}$).
- **Resource Utilization**: Peak RAM ($\text{MB}/\text{GB}$), Average CPU Utilization ($\%$), I/O wait time ($\text{ms}$).
- **Initialization & Recovery**: Cold startup time ($\text{ms}$), Failure recovery / failover time ($\text{ms}$).

### 7.2 Functional & Data Correctness Metrics (`FUNC`)
- **Delivery Invariants**: Zero message loss ($\text{Loss} = 0$), Zero unhandled duplicates ($\text{Dup} = 0$), In-order event delivery confirmation.
- **Determinism**: Identical execution output across 10 repeated runs given identical seed ($\text{Determinism Ratio} = 1.0$).
- **Fidelity**: Fee and slippage calculation error relative to reference math ($\le 10^{-6}$).

### 7.3 Retrieval & Quality Metrics (`QUAL`)
- **Retrieval Accuracy**: Recall at 10 ($R@10$), Precision at 10 ($P@10$), Mean Reciprocal Rank ($\text{MRR}$).
- **Evaluation Accuracy**: Hallucination Detection F1-Score, False Positive Rate ($\text{FPR}$), False Negative Rate ($\text{FNR}$).

### 7.4 Security & Governance Metrics (`SECU`)
- **Isolation Verification**: 100% rejection of unauthorized cross-tenant data requests.
- **Enforcement Overhead**: Security policy evaluation latency added per transaction ($\mu\text{s}$).
- **Failure Safety**: Fail-closed assertion verification upon sidecar network partition.

---

## 8. Functional Correctness Gates

Performance without functional correctness is invalid. A candidate that demonstrates superior throughput but fails functional correctness **MUST BE DISQUALIFIED**.

### 8.1 Mandatory Functional Gates by Group
- **Messaging (Group C)**: Must prove zero message drop under target load and exact subject routing correctness.
- **Backtesting (Group B)**: Must produce identical trade log execution output across 10 identical runs and match reference PnL within $10^{-5}$ tolerance.
- **Vector Memory & Retrieval (Group I)**: Must correctly enforce strict metadata tenant filtering (`tenant_id == X`) without leaking cross-tenant vector results.
- **Security (Group G)**: Must block 100% of invalid secret retrieval attempts and fail closed upon security sidecar crash.
- **LLM Quality & Firewall (Group K)**: Supporting validation tools must not alter or bypass deterministic risk firewall decisions (`core/risk_firewall.py`).

---

## 9. Test Workload Sizing Standard

Every performance and functional benchmark must execute across three standardized workload classes:

| Workload Class | Target Scale / Duration | Primary Purpose |
|----------------|-------------------------|-----------------|
| **SMALL** | $10^4$ events / 100 queries / 1 min run | Functional verification, test harness debugging, contract validation. |
| **MEDIUM** | $10^6$ events / 10,000 queries / 15 min run | Normal AIOS operating conditions, baseline performance measurement. |
| **LARGE** | $5 \times 10^7$ events / 100,000 queries / 2 hour run | Scalability limits, memory leak detection, $p_{99}$ tail latency profiling under stress. |

---

## 10. Repeatability & Statistical Rigor

To eliminate transient hardware noise and ensure statistical validity:

1. **Warm-up Protocol**: A minimum of 3 warm-up runs must execute and be discarded prior to recording measured metrics.
2. **Repetition Requirement**: Every benchmark metric must be measured across a minimum of **10 independent executions**.
3. **Statistical Summary**: Benchmarks must report the complete statistical summary block:
   - Arithmetic Mean ($\mu$)
   - Median ($p_{50}$)
   - 95th Percentile ($p_{95}$)
   - 99th Percentile ($p_{99}$)
   - Minimum & Maximum values
   - Standard Deviation ($\sigma$)
   - 95% Confidence Interval ($\text{CI}_{95}$)
4. **No Cherry-Picking**: Selecting the "best" single run is strictly prohibited. The full distribution must be retained.

---

## 11. Benchmark Outcome Classification Rules

Benchmark results for a candidate package or architecture are classified into three official outcomes:

```
+-------------------------------------------------------------------------------------------------------------------+
|                                      BENCHMARK OUTCOME CLASSIFICATION MATRIX                                      |
+-------------------------------------------------------------------------------------------------------------------+
| OUTCOME      | MANDATORY CONDITIONS                                                                               |
+--------------+----------------------------------------------------------------------------------------------------+
| **PASS**     | 1. Satisfies 100% of Mandatory Functional Correctness Gates.                                        |
|              | 2. Satisfies all Mandatory Safety and Security Requirements.                                       |
|              | 3. Meets or exceeds Minimum Acceptable Performance Floor ($p_{95}$ latency & throughput thresholds). |
|              | 4. Complies fully with Phase 1 Architectural Constraints.                                         |
+--------------+----------------------------------------------------------------------------------------------------+
| **FAIL**     | 1. Fails any Mandatory Functional Correctness Gate (e.g. data loss, state corruption).              |
|              | 2. Causes a Security Violation or fails to fail-closed.                                            |
|              | 3. Breaches Minimum Acceptable Performance Floor.                                                 |
|              | 4. Violates Phase 1 Architectural Invariants or Safety Constraints.                                |
+--------------+----------------------------------------------------------------------------------------------------+
| **INCONCLUSIVE** | 1. Statistical confidence intervals of competing candidates overlap significantly.            |
|              | 2. Environmental noise ($\sigma / \mu > 0.15$) invalidates execution telemetry.                     |
|              | 3. Test harness execution encounters unhandled infrastructure errors.                             |
|              | 4. Workload scale is insufficient to differentiate candidate behavior.                             |
+-------------------------------------------------------------------------------------------------------------------+
```

---

## 12. Multi-Dimensional Weighted Decision Model

While benchmarks generate raw empirical evidence, formal ADR technology selection utilizes a 10-dimensional decision framework. Benchmark performance metrics serve as inputs into this framework:

$$\text{Total Score} = \sum_{i=1}^{10} w_i \cdot S_i$$

Where dimensions ($S_i$) are evaluated on a 0–100 scale:
1. **Functional Fit ($S_1$)**: Coverage of required capability invariants.
2. **Architecture Fit ($S_2$)**: Alignment with Phase 1 frozen architecture.
3. **Performance & Latency ($S_3$)**: Benchmark $p_{95}/p_{99}$ latency and throughput.
4. **Reliability & Determinism ($S_4$)**: Failure recovery, zero data loss, determinism.
5. **Security & Safety ($S_5$)**: Isolation, fail-closed behavior, policy compliance.
6. **Operational Complexity ($S_6$)**: Deployment weight, monitoring overhead, cluster requirements.
7. **License & Legal Compliance ($S_7$)**: Permissive licensing, copyleft risk mitigation.
8. **Ecosystem & Maturity ($S_8$)**: Community activity, documentation quality, release cadences.
9. **Replaceability ($S_9$)**: Ease of replacement via AIOS Abstract Base Class (ABC).
10. **Integration Effort ($S_{10}$)**: Developer effort required to build and maintain adapters.

*Note: Dimensional weights ($w_i$) are formally assigned during post-benchmark ADR authoring based on domain criticality.*

---

## 13. Benchmark Evidence Package Specification

Every executed benchmark must produce a complete, machine-readable **Benchmark Evidence Package** stored in `research/benchmarks/<group_id>/<candidate>/`.

### 13.1 Mandatory Evidence Package Artifacts
A complete package must contain:
1. `metadata.json`: Run metadata, git commit hash, dataset hash, seed.
2. `environment.yaml`: Complete recorded environment snapshot.
3. `config.yaml`: Complete candidate configuration file.
4. `test_script.py`: Standardized benchmark harness execution script.
5. `raw_telemetry.jsonl`: Unaggregated per-operation latency and resource logs.
6. `summary_results.json`: Computed statistical summary block.
7. `functional_audit.log`: Log output of functional correctness assertions.
8. `report.md`: Human-readable summary report.

---

## 14. Standard Machine-Readable Result Schema

Raw benchmark summaries must validate against the standard `AIOS Benchmark Result v0.1` YAML schema:

```yaml
schema_version: "0.1.0"
benchmark_id: "BMK-GRP-B-001"
group_id: "GROUP_B"
candidate_name: "NautilusTrader"
candidate_version: "1.190.0"
repository_commit: "a1b2c3d4e5f6"
timestamp_utc: "2026-08-19T14:30:00Z"
operator: "AIOS Automated Benchmark Runner"

environment:
  os: "Linux 6.6.0-x86_64"
  python_version: "3.11.9"
  cpu_model: "AMD EPYC 7763"
  cores_allocated: 16
  ram_gb_allocated: 64.0

dataset:
  dataset_id: "MKT-EQUITIES-TICK-2024-2025"
  dataset_hash_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  record_count: 50000000

workload:
  class: "LARGE"
  random_seed: 42
  duration_seconds: 7200

functional_correctness:
  all_gates_passed: true
  failed_gate_count: 0
  determinism_score: 1.0

performance_summary:
  throughput_ops_sec:
    mean: 145200.5
    median: 145100.0
    std_dev: 1200.3
  latency_ms:
    p50: 0.12
    p95: 0.45
    p99: 0.89
    max: 2.10
  resources:
    peak_memory_mb: 2450.0
    avg_cpu_percent: 85.4

outcome: "PASS"
```

---

## 15. Baseline Management Policy

Every benchmark group designates an authoritative **Baseline**:

1. **Reference Purpose**: The baseline represents the frozen Phase 1 default technology or simplest direct implementation (e.g., PostgreSQL CTE for Group F, direct Qdrant SDK for Group I, Pydantic + AIOS Firewall for Group K).
2. **No Automatic Selection**: The baseline does **NOT** automatically win the competition group. It serves as the quantitative standard against which alternatives are measured.
3. **Baseline Failure Protocol**: If the baseline candidate fails mandatory functional gates or performance floors, this failure must be explicitly documented in the benchmark report, triggering priority ADR evaluation of alternative candidates.

---

## 16. Standardization & Tuning Fairness Policy

To ensure absolute evaluation fairness:

1. **Equal Resource Allocation**: Competing candidates must execute on identical CPU cores, memory limits, and disk I/O channels.
2. **Default vs Tuned Profiles**: Candidates are initially tested using standard production configurations.
3. **Vendor-Recommended Tuning Rules**:
   - If vendor-recommended tuning parameters are applied to one candidate, equivalent documented tuning must be applied to all competitors.
   - All custom configuration flags, buffer sizes, and thread pool settings must be explicitly committed in `config.yaml`.
   - Undocumented source-code modifications or unfair micro-optimizations are prohibited.

---

## 17. License & Legal Risk Audit Track

Benchmark evidence packages must incorporate legal status tracking derived from Phase 2 findings:

```
+-------------------------------------------------------------------------------------------------------------------+
|                                      LICENSE & LEGAL RISK TRACKING SUMMARY                                        |
+-------------------------------------------------------------------------------------------------------------------+
| PACKAGE          | LICENSE     | RISK LEVEL | MANDATORY LEGAL REVIEW ACTION                                       |
+------------------+-------------+------------+---------------------------------------------------------------------+
| **NautilusTrader**| LGPL-3     | **HIGH**   | Conduct formal legal review of dynamic linking in Python to verify  |
|                  |             |            | proprietary strategy source code protection prior to production.     |
+------------------+-------------+------------+---------------------------------------------------------------------+
| **Neo4j**        | GPL-3       | **HIGH**   | Verify network socket isolation boundaries to prevent copyleft      |
|                  |             |            | contamination of core AIOS modules.                                 |
+------------------+-------------+------------+---------------------------------------------------------------------+
| **Grafana**      | AGPL-3      | **MEDIUM** | Audit network-use copyleft implications for hosted dashboard service.|
+------------------+-------------+------------+---------------------------------------------------------------------+
| **RedPanda**     | BSL 1.1     | **MEDIUM** | Review commercial node volume limits under Business Source License. |
+------------------+-------------+------------+---------------------------------------------------------------------+
| **OpenBao**      | MPL-2.0     | **LOW**    | Confirm file-level copyleft isolation behind Python wrappers.       |
+-------------------------------------------------------------------------------------------------------------------+
```

*Note: Legal status is tracked as an evaluation constraint. Benchmark throughput does not supersede legal or license risks.*

---

## 18. Security & Safety Evaluation Track

Security-critical candidates (Groups G, K, C, A) must undergo security evaluation regardless of performance metrics:

1. **Authentication & Authorization**: Verify token validation overhead and identity propagation across service boundaries.
2. **Isolation Integrity**: Verify process and memory isolation between distinct agent execution contexts.
3. **Fail-Safe Behavior**: Verify that sidecar crashes, network disconnects, or buffer overflows default to a **FAIL-CLOSED** state (blocking trade execution and securing secret vaults).
4. **Audit Trail Tamper-Resistance**: Verify that all security assertions emit append-only audit events to Community 7 relational stores.

---

## 19. Benchmark Execution Sequence Roadmap

Actual benchmark execution must follow a strict 9-step sequential roadmap:

```
+-------------------------------------------------------------------------------------------------------------------+
|                                     BENCHMARK EXECUTION SEQUENCE ROADMAP                                          |
+-------------------------------------------------------------------------------------------------------------------+
| STEP 1: Environment Validation  | Validate hardware isolation, OS configuration, and dependency lockfiles.         |
| STEP 2: Dataset Validation      | Verify SHA-256 checksums of historical market data and synthetic test vectors.   |
| STEP 3: Test Harness Validation | Execute SMALL workload dry-runs across all groups to verify telemetry capturing. |
| STEP 4: Tier 1 Benchmarks       | Execute Tier 1 benchmarks (Group A: Agents, Group B: Backtesting, Group C: Bus).|
| STEP 5: Tier 2 Evaluations      | Execute Tier 2 evaluations (Groups D, E, F, I, J, K).                             |
| STEP 6: Tier 3 Evaluations      | Execute Tier 3 evaluations (Group G: Security, Group H: Data Providers).          |
| STEP 7: Cross-Result Analysis   | Synthesize raw telemetry, generate statistical summaries and metric comparisons.  |
| STEP 8: ADR Evidence Packaging  | Compile machine-readable Evidence Packages (`research/benchmarks/`).             |
| STEP 9: Formal Technology ADRs  | Submit Evidence Packages to Architecture Board for formal technology selection.   |
+-------------------------------------------------------------------------------------------------------------------+
```

---

## 20. Early Termination & Stop Conditions

Benchmark execution for a specific candidate must immediately terminate if any of the following **Stop Conditions** are triggered:

1. **Critical Functional Failure**: Candidate crashes repeatedly ($\ge 3$ consecutive fatal exceptions) during SMALL workload contract validation.
2. **Security Disqualification**: Candidate leaks cross-tenant secrets or fails to block unauthorized authorization bypass attempts.
3. **License Blocker**: Formal legal counsel rejects license usage for commercial deployment.
4. **Architectural Incompatibility**: Candidate requires altering frozen Phase 1 architectural invariants or breaking ABC encapsulation rules.
5. **Catastrophic Performance Degradation**: Candidate latency exceeds minimum acceptable floor by $>1,000\%$ under MEDIUM workload.

Upon triggering a stop condition, benchmarking for that candidate halts, outcome is set to `FAIL`, and the root cause is logged in the evidence package.

---

## 21. Non-Selection Governance (FORMAL SELECTION = 0)

This protocol explicitly enforces non-selection governance:

- **Protocol Output**: Objective empirical telemetry, functional correctness logs, and statistical evidence packages.
- **Prohibited Declarations**: This document and any scripts executing this protocol **SHALL NOT** declare candidates as `SELECTED`, `WINNER`, or `APPROVED`.
- **Handoff to ADR**: Technology selection occurs strictly in Phase 2C/3 via formal Architecture Decision Records (ADRs) authored by human software architects reviewing the compiled Evidence Packages.

---

## 22. Supporting Protocol Templates

To facilitate execution, standard templates are provided in the `templates/` directory:

1. `templates/benchmark-result-template.yaml`: Machine-readable YAML telemetry summary schema.
2. `templates/benchmark-run-metadata.yaml`: Environment and execution metadata manifest.
3. `templates/benchmark-report-template.md`: Standardized human-readable benchmark report template.

---

*End of AIOS Phase 2B Benchmark Protocol Specification v0.1.*
