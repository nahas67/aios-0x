# ADR-003: Risk/Reward Threshold Staging

## Context

Frozen specifications state two different R:R minimums without documenting the relationship:

- Doc 03 (C2 Research): hypotheses target **R:R ≥ 2.0**.
- Docs 04/05/11 (C3 rubric, C4 structuring, deterministic Risk Firewall): hard floor **R:R ≥ 1.5**.

Phase 0 discovery flagged this as undocumented inconsistency (GAP_ANALYSIS §2 item 5).
Ambiguity in risk thresholds is unacceptable for a system whose firewall must be
deterministic and non-negotiable (Constitution Law 2).

## Decision

Ratify the two values as an intentional **staging funnel**, not a conflict:

1. **Research stage (C2) — soft target R:R ≥ 2.0.** Hypothesis generation aims for
   asymmetric setups; the ResearchAgent template uses `expected_risk_reward_ratio = 2.0`
   as its default proposal. LLM-driven research (Phase 2) inherits this as guidance, not law.

2. **Hard floor (C3 gate + C4 + Risk Firewall) — R:R ≥ 1.5.** The verification rubric
   awards the full 30 math points at ≥ 1.5, and `RiskFirewall.min_risk_reward_ratio = 1.5`
   remains the immutable execution boundary. Nothing below 1.5 may ever be structured,
   approved, or executed regardless of upstream enthusiasm.

3. **Pass-through binding**: C4 derives take-profit distance from the hypothesis's own
   `expected_risk_reward_ratio` (validated ≥ 1.5 upstream and re-enforced by the firewall),
   replacing the previous hardcoded ×2 geometry. The hypothesis's stated asymmetry thus
   flows through to order structure instead of being silently discarded.

4. Any future change to either number requires a new ADR plus updates to:
   `core/risk_firewall.py`, `communities/c3_verification/verification_agent.py`,
   `docs/03`, `docs/04`, `docs/05`, `docs/11` (frozen docs amended by reference).

## Status

- State: ACCEPTED
- Date: 2026-08-23
- Authors: AIOS System Architecture Team

## Consequences

Positive:
- Removes documentation ambiguity flagged in Phase 0 discovery.
- Strategy geometry now honors per-hypothesis asymmetry (information preserved).
- Firewall remains single source of truth for the executable floor.

Negative:
- Hypotheses between 1.5–2.0 are now structurable where the old code effectively forced
  ×2; mitigated by C2 continuing to propose ≥ 2.0 by default.

## Compliance & Verification

- `tests/test_strategy_and_paper_engine.py::test_strategy_agent_generates_buy_with_volatility_scaled_levels`
  proves hypothesis R:R drives target distance (rr=2.0 → target = 2× stop distance).
- `tests/test_risk_firewall.py::test_rejection_low_risk_reward_ratio` pins the 1.5 floor.
