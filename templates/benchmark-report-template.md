# AIOS Benchmark Report — [Benchmark ID]

**Group ID**: `GROUP_[A-K]`  
**Candidate Package**: `[Candidate Name]` (`[Version]`)  
**Evaluation Types**: `PERF`, `FUNC`, `QUAL`, `SECU`  
**Date Executed**: `YYYY-MM-DD`  
**Execution Outcome**: `PASS | FAIL | INCONCLUSIVE`  

---

## 1. Executive Summary
Brief summary of the benchmark execution, core findings, and outcome.

---

## 2. Benchmark Configuration & Environment
- **Hardware**: [CPU, RAM, Storage]
- **OS / Runtime**: [OS Name, Kernel, Python Version]
- **Dataset**: [Dataset ID, Record Count, SHA-256 Hash]
- **Workload**: [Class: SMALL/MEDIUM/LARGE, Seed: 42]

---

## 3. Functional Correctness Assertions
| Gate ID | Assertion Description | Expected Result | Actual Result | Gate Status |
|---------|-----------------------|-----------------|---------------|-------------|
| GATE-01 | Delivery Invariance  | 0 dropped msgs  | 0 dropped msgs | PASS        |
| GATE-02 | Determinism Check     | Seed match = 1.0| 1.0           | PASS        |

---

## 4. Performance & Telemetry Results
| Metric Name | Mean ($\mu$) | Median ($p_{50}$) | $p_{95}$ Latency | $p_{99}$ Latency | Std Dev ($\sigma$) |
|-------------|--------------|-------------------|------------------|------------------|--------------------|
| Throughput  | 0 ops/sec    | 0 ops/sec         | N/A              | N/A              | 0.0                |
| Latency     | 0.0 ms       | 0.0 ms            | 0.0 ms           | 0.0 ms           | 0.0 ms             |

---

## 5. Security & Legal Audit Track
- **License Compliance**: [License Type, Risk Level, Legal Actions Required]
- **Security Assertions**: [Auth isolation, fail-closed verification]

---

## 6. Architectural Fit & Limitations
Notes on ABC wrapper integration, replaceability, operational complexity, and limitations.

---

## 7. Evidence Package Handoff
Raw telemetry files saved at `research/benchmarks/[group_id]/[candidate]/`.
*Formally submitted for post-benchmark ADR evaluation.*
