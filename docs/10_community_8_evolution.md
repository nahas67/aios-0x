# AIOS Specification 1.10: Community 8 Specification (Evolution Mechanisms)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 8 (Evolution Mechanisms)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 8 (C8) acts as the continuous self-adaptation, meta-learning, and strategy evolution engine of AIOS. Its primary objective is to autonomously analyze system-wide performance records, detect strategy alpha decay, optimize LLM prompts and verification rubrics, adjust system-wide risk parameters, and manage agent lifecycles (spawning and retirement) without manual human intervention.

### 1.2 Core Responsibilities
- **Continuous System Performance Evaluation**: Monitor multi-week rolling win rates, Sharpe ratios, maximum drawdowns, and prediction accuracy metrics across all active strategies.
- **Dynamic Prompt & Rubric Optimization**: Adjust system prompt instructions for research agents (Community 2) and tune verification scoring weights/thresholds (Community 3) based on post-mortem insights from Community 7.
- **Strategy Decay & Lifecycle Governance**: Detect strategy alpha decay and regime mismatch, triggering automatic strategy pausing, re-evaluation, or retirement.
- **Autonomous Agent Creation & Retirement**: Spawn specialized agent prompt variants tailored to emerging market regimes or underperforming asset classes, while retiring obsolete agent variants.
- **Evolution Signal Dispatching**: Package meta-learning recommendations into `EvolutionSignal` payloads and publish to `evolution.triggered` (`EventTopic.EVOLUTION_TRIGGERED`).

---

## 2. Agent Hierarchy & Roles

Community 8 features a multi-tiered meta-learning agent hierarchy:

```
+-----------------------------------------------------------------------------------+
|                     MEMORY STORED EVENT / PERIODIC CRON                           |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     SYSTEM PERFORMANCE EVALUATOR AGENT                            |
|             (Calculates rolling win rates, Sharpe, drawdowns, drift)             |
+-----------------------------------------------------------------------------------+
                                          |
     +-------------------+----------------+-------------------+
     |                   |                                    |
     v                   v                                    v
[Prompt & Rubric     [Strategy Retirement                 [Autonomous Agent
 Optimization Agent]  Agent]                              Creation Agent]
     |                   |                                    |
     +-------------------+----------------+-------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                          EVOLUTION SIGNAL DISPATCHER                              |
|          (Emits EvolutionSignal to EVOLUTION_TRIGGERED topic)                     |
+-----------------------------------------------------------------------------------+
```

### 2.1 System Performance Evaluator Agent
- **Role**: Computes aggregate metrics over rolling multi-week evaluation horizons using Community 7's historical records.
- **Focus**:
  - Tracks rolling win rate (e.g. over 20+ trades).
  - Evaluates cumulative drawdown and Sharpe ratio trends.
  - Monitors prediction-vs-actual deviation scores from Community 6 (Observation).

### 2.2 Prompt & Rubric Optimization Agent
- **Role**: Fine-tunes LLM system prompts and verification weights based on post-mortem lessons stored in Community 7 (Memory).
- **Focus**:
  - Extracts recurring failure patterns from vector memory (`post_mortem_lessons`).
  - Injects anti-patterns into Community 2's research prompts (e.g. "Avoid buying breakouts during high-volatility CPI announcements").
  - Dynamically increases Community 3's minimum verification confidence threshold (e.g. from 70% to 75% or 80%) when system win rate degrades.

### 2.3 Strategy Retirement Agent
- **Role**: Monitors active strategies for performance degradation, alpha decay, or structural market regime shifts.
- **Focus**:
  - Applies deterministic strategy decay triggers (e.g. 3 consecutive stop-out losses or rolling Sharpe < 1.0).
  - Issues pause/retirement commands for decaying strategies.
  - Archives retired strategy parameters to Community 7 for historical post-mortem analysis.

### 2.4 Autonomous Agent Creation Agent
- **Role**: Spawns specialized agent variants to address newly identified market regimes or asset-class gaps.
- **Focus**:
  - Creates specialized agent sub-prompts (e.g., "Crypto Volatility Specialist Agent", "Macro Rate Decision Agent").
  - Deploys new agent variants to Community 2 or Community 3 in shadow/paper mode for initial validation.
  - Retires underperforming agent variants whose conviction or accuracy falls below baseline.

---

## 3. Self-Tuning Algorithms & Strategy Decay Rules

### 3.1 Verification Threshold Auto-Tuning Rule
When rolling performance degrades, Community 8 automatically tightens the Quality Firewall (Community 3):

```
IF total_trades >= 3 AND rolling_win_rate < 50.0%:
    - Increase C3 min_confidence_threshold: 70.0 -> 80.0
    - Reduce default max_position_size_pct: 5.0% -> 3.0%
    - Flag system status: CONSERVATIVE_EVOLUTION_MODE

ELSE IF rolling_win_rate >= 65.0% AND rolling_sharpe >= 2.0:
    - Maintain / restore standard thresholds (70.0 min_confidence, 5.0% max_position)
    - Flag system status: OPTIMAL_PERFORMANCE_MODE
```

### 3.2 Strategy Alpha Decay Triggers
A strategy is automatically paused or retired when any of the following triggers occur:

| Decay Trigger | Threshold / Condition | Action Taken |
| :--- | :--- | :--- |
| **Consecutive Stop-Outs** | 3 consecutive trades hit stop-loss | Immediate strategy pause. Send to C2/C3 for re-evaluation. |
| **Sharpe Degradation** | Rolling Sharpe ratio $< 1.0$ over 20 trades | Pause strategy. Lower allocation weight. |
| **Max Drawdown Breach** | Strategy-level drawdown $> 8.0\%$ | Retire strategy candidate from live routing. |
| **Model Drift Flag** | Directional accuracy $< 45.0\%$ over 15 trades | Trigger prompt re-optimization in C2 research agents. |

### 3.3 Feedback Routing Loop
System adaptation recommendations are routed back to the appropriate communities:

```
+-----------------------------------------------------------------------------------+
|                        EVOLUTION FEEDBACK ROUTING LOOP                            |
+-----------------------------------------------------------------------------------+
   |                                  |                                   |
   v                                  v                                   v
[To Community 2 (Research)]     [To Community 3 (Verification)]     [To Community 4 (Strategy)]
 - Updated system prompts        - Adjusted confidence threshold     - Adjusted position size cap
 - New anti-pattern guidelines   - Weighted rubric updates           - Revised R:R requirements
```

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
Community 8 outputs instances of `EvolutionSignal` defined in `communities/c8_evolution/evolution_agent.py`:

```python
class EvolutionSignal(BaseModel):
    signal_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this evolution signal",
    )
    timestamp: datetime = Field(
        default_factory=generate_utc_now,
        description="UTC timestamp of the evolution trigger",
    )
    adjustment_needed: bool = Field(
        ...,
        description="Indicates if system parameter adjustment is recommended",
    )
    recommendations: list[str] = Field(
        ...,
        description="List of meta-learning system recommendations",
    )
    performance_summary: dict[str, Any] = Field(
        ...,
        description="Snapshot of performance analytics at evaluation time",
    )
```

### 4.2 Event Bus Routing
- **Subscription Topic**: `memory.stored` (`EventTopic.MEMORY_STORED`) via `on_memory_stored()` callback.
- **Publication Topic**: `evolution.triggered` (`EventTopic.EVOLUTION_TRIGGERED`).
- **Target Subscribers**: Community 2 (Research prompt updates), Community 3 (Verification threshold updates), Community 4/5 (Risk cap adjustments), Community 7 (Memory record).

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](CHECKPOINT.md) under **Doc 1.10: Community 8 Specification (Evolution Mechanisms)**. Implementation code resides in `communities/c8_evolution/evolution_agent.py` and unit tests in `tests/test_c8_evolution.py`.
