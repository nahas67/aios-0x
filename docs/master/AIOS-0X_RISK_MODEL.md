# AIOS-0X Risk Model
Version 1.0.0 | Current: position-level firewall (verified, tested). Target: independent Risk Governor.

## 1. Current State (verified)
core/risk_firewall.py RiskConfig: max_position_size_pct=5.0, max_stop_loss_pct=5.0,
min_risk_reward_ratio=1.5, max_daily_drawdown_pct=3.0 (breach -> emergency_shutdown_triggered).
Deterministic, non-LLM - correct foundation per Constitution Law 2.
Defects: ignores current_portfolio_value param; no portfolio/correlation/liquidity controls; no kill-switch
implementation; drawdown state is passed in by callers rather than owned.

## 2. Two-Layer Risk Authority (target)
Layer 1 - StrategyGate (exists): per-trade checks at C4 proposal time (stop distance, R:R, size cap, drawdown).
Layer 2 - RiskGovernor (build): independent service owning:
- Portfolio state: exposures by asset/class/correlation cluster; realized+unrealized PnL; drawdown tracker
- Pre-trade approval of every OrderRequest (records RiskDecision to audit log)
- Kill-switch executor: 3-step cancel-all -> flatten -> EMERGENCY_LOCKOUT until human review (Doc 07)
- Emergency state machine: NORMAL | CAUTION | HIGH_ALERT | MARKET_SHOCK | DATA_FAILURE | MODEL_FAILURE |
  EXECUTION_FAILURE | SECURITY_INCIDENT | EMERGENCY_HALT
- No strategy agent can write risk state; bus ACL enforces.

## 3. Control Set (complete list to implement)
| Control | Source | Notes |
|---|---|---|
| Position cap 5% | Doc 05/11 | exists |
| Daily drawdown 3% -> halt | Doc 05/11 | exists at gate; governor owns truth |
| Stop distance max 5% | Doc 11 | exists |
| Min R:R 1.5 | Doc 04/05 | exists |
| Max 5 open positions / class | Doc 11 | build |
| Correlated exposure cap 15% (e.g., BTC+ETH) | Doc 11 | build |
| Pair rho>0.80 cap 10%; class cap 35% | Doc 15 | build |
| Drawdown tiers 1.5%/2.5%/3.0% scale-down | Doc 15 | build |
| Liquidity floor: notional < x% of ADV | Directive 39 | build |
| Volatility circuit: halt entries when realized vol > k sigma | Directive 39 | build |
| Data-quality gate: STALE symbol = frozen | Event Model | build |
| Model-confidence gate: min verification score to trade | Doc 04 | exists via is_verified |
| Leverage limit (constitution) | Directive 48 | config |
| Loss limits per strategy/day | Doc 10 alpha-decay rules | build with strategy registry |

## 4. Emergency Procedures (implement as code, not docs)
Trigger sources: firewall flag, WS heartbeat loss (Doc 07), reconciliation failure, data corruption event,
security anomaly, manual human command.
Kill-switch sequence (deterministic): cancel all open orders -> flatten positions (aggressive market) ->
EMERGENCY_LOCKOUT flag persisted -> notify observation/memory/human channels. Lockout clears ONLY by
human action (Directive 47).

## 5. Risk Telemetry (feeds observability)
approval_rate, rejection_reason_histogram, current_drawdown, exposure_by_cluster, open_positions,
kill_switch_state, time_to_risk_decision_p95. Alert thresholds wired to SYSTEM_HEALTH_ALERT.

## 6. Testing Requirements
Property tests: no order path bypasses governor (bus ACL tests). Scenario tests: each emergency trigger ->
assert lockout + zero residual orders. Determinism test: same inputs -> same decision (no LLM in path).
