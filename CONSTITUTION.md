# AIOS-0X SYSTEM CONSTITUTION

**Status: RATIFIED v1.0.0 (2026-08-23) — amendment requires ADR + pin update + human sign-off**

This document is the supreme authority for the AIOS-0X investment institution.
No agent, prompt, model, or automated process may violate it. Self-evolving
components cannot rewrite this file: its SHA-256 hash is pinned in
`core/constitution.py`, verified at every runner boot. A mismatch halts the
system until a human resolves it.

## 1. Capital & Risk Limits

| Limit | Value | Enforced by |
|---|---|---|
| Leverage / margin | **None (1x cash only)** | PaperEngine & adapters reject margin |
| Max position size (% equity) | **5%** proposal cap | RiskFirewall.max_position_size_pct |
| Max class exposure (% equity) | **35%** | PortfolioGovernor |
| Daily drawdown halt | **3.0%** → flatten + lockout | Governor tiers + RiskGovernor |
| Drawdown scaling tiers | 1.5% → ×0.75, 2.5% → ×0.50 | PortfolioGovernor |
| Correlated pair cap (ρ>0.80) | 10% of portfolio | Doc 15 (activation pending C9 correlation matrix) |
| Micro-live order notional cap | **$100** per order | CcxtExecutionAdapter.MAX_ORDER_NOTIONAL_USD |
| Live routing | **FORBIDDEN** until (a) `approve_live_capital` control action recorded, (b) broker testnet integration validated in shadow, (c) constitution amended via ADR to lift §1 live gate | This file |

## 2. Authority Boundaries (non-negotiable)

1. The deterministic Risk Firewall and RiskGovernor outrank every LLM and agent.
2. Kill-switch sequence (cancel→flatten→EMERGENCY_HALT) may be triggered by
   any guard; only a **human reset with operator id** clears the lockout.
3. Tax computations are advisory; filings require a licensed professional's
   approval through the CA review workflow (`APPROVED_BY_CA`).
4. Challenger promotions require an EVALUATED trial plus explicit human action.
5. Simulated artifacts MUST carry `is_simulated=true` end-to-end (Law 1.3).
6. No component may bypass the event bus to place orders.

## 3. Honesty Laws

1. Never fabricate prices, fills, news, profit, or capability.
2. Missing data ⇒ NO TRADE / UNKNOWN - never a default value.
3. Exits originate from market events only.
4. Unverified hypotheses never reach execution.

## 4. Amendment Procedure

1. Draft ADR describing the change, evidence, and risk analysis.
2. Human principal approves the ADR.
3. Edit this file; recompute SHA-256; update `_PINNED_SHA256` in
   `core/constitution.py` in the SAME commit as the ADR file.
4. Boot verification enforces the new pin thereafter.
