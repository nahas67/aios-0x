# AIOS-0X Test Strategy
Version 1.0.0 | Current baseline verified: 32/32 pytest passing (Python 3.14.4, 2026-08-23)

## 1. Current Tests (verified)
tests/: contracts (8), event_bus (5), c1_data (2), research+verification (4), risk_firewall (5),
strategy+paper_engine (3), closed_loop_feedback (4). All green.
Gaps: no tests for c5/c9 (absent code); no persistence tests; no failure-injection; no property tests;
closed-loop test asserts on fabricated +3% exits (must change with c6 fix).

## 2. Test Pyramid (target)
| Level | Scope | Tooling | Gate |
|---|---|---|---|
| Unit | every module incl. agents, firewall, memory | pytest + pytest-asyncio | CI required |
| Contract | Pydantic schema evolution: compat checks both directions | pytest snapshot | CI |
| Integration | bus+agents+memory+paper engine end-to-end loops | pytest fixtures | CI |
| Property | risk governor invariants; no-look-ahead loader; idempotent consumers | hypothesis | nightly |
| Failure injection | timeouts, API errors, partial fills, DLQ replay, kill-switch triggers | resiliency harness | nightly |
| Backtest integrity | look-ahead/survivorship/leakage detectors run on strategy lab outputs | custom linters + canary strategies | promotion gate |
| AI eval | prompt golden sets, hallucination rate, structured-output parse rate, tool-use success | eval harness (Prompt Registry) | prompt-change gate |
| Performance | bus throughput, retrieval latency p95, decision latency | benchmark scripts | release gate |
| Security | secret scanning, ACL bypass attempts, injection corpora | bandit/pip-audit + custom | CI |
| Financial realism | replay known crises (Doc 06 library): 2010 flash crash, 2020 covid, FTX, SVB | SIM lab | pre-paper gate |

## 3. Critical Invariants Under Continuous Test (from Architecture section 8)
1. No execution without recorded RiskDecision (bus ACL integration test).
2. Fabricated-price detector: any ObservationReport whose exit lacks market data ref fails CI canary.
   (This test would FAIL today - by design; it encodes defect fix.)
3. is_simulated propagation end-to-end when SimulatedDataFetcher in play.
4. Replay determinism: same dataset+seed -> identical decision sequence hashes.
5. Constitution hash check at boot.

## 4. Data Fixtures Strategy
Golden parquet datasets (fixed crypto BTC/ETH/SOL-USDT, equities AAPL/MSFT/SPY/QQQ per Phase 2B window
2024-01-01..2025-12-31) with SHA-256 pinned; synthetic generators seeded (seed=42) for stress shapes.
No live network in CI - all external APIs mocked at ABC boundary.

## 5. Quality Gates for Promotion (strategy or agent or prompt)
Unit+integration green -> backtest-integrity clean -> walk-forward consistent -> stress survived ->
shadow period complete -> human review record exists. Same ladder applies to code changes touching
risk/execution paths.

## 6. Tooling To Add (Slice 0)
pyproject with pytest config; ruff (lint+format); mypy strict per .cursorrules; coverage reporting
(target >=85% core paths before Slice 2); GitHub Actions or local runner script (no external CI dependency
required initially).
