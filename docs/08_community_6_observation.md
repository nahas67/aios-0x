# AIOS Specification 1.8: Community 6 Specification (Observation & Audit)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 6 (Observation & Audit)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 6 (C6) serves as the post-execution observation layer for AIOS. Its primary objective is to observe market reality after every trading decision, evaluate realized performance against predicted outcomes, measure execution variance, detect unexpected market anomalies or model drift, and produce comprehensive post-mortem audit reports that feed institutional learning.

### 1.2 Core Responsibilities
- **Realized PnL Calculation**: Compute actual profit and loss for every closed position, inclusive of fees and slippage.
- **Slippage & Market Impact Measurement**: Quantify the gap between expected fill prices (from `StrategySpecification`) and actual fill prices (from `TradeExecutionReceipt`).
- **Prediction Accuracy Auditing**: Compare the directional thesis and magnitude predictions from Community 2 against post-trade price action to score research agent accuracy.
- **Unexpected Event Detection**: Identify macro news shocks, flash crashes, exchange outages, or liquidity anomalies that occurred during the trade lifecycle.
- **Post-Mortem Trade Reporting**: Synthesize findings into structured `ObservationReport` payloads containing PnL, deviation metrics, and lessons learned for downstream consumption by Community 7 (Memory) and Community 8 (Evolution).

---

## 2. Agent Hierarchy & Roles

Community 6 operates a parallel analysis pipeline triggered by every incoming `TradeExecutionReceipt`:

```
+-----------------------------------------------------------------------------------+
|              TRADE EXECUTION RECEIPT INPUT (from C5 or Training Env)              |
|                          [TradeExecutionReceipt]                                  |
+-----------------------------------------------------------------------------------+
                                          |
     +-------------------+---------------+---------------+-------------------+
     |                   |                               |                   |
     v                   v                               v                   v
[Performance         [Slippage &              [Prediction Deviation   [Anomaly &
 Measurement          Execution Impact         & Model Drift           Volatility
 Agent]               Agent]                   Agent]                  Detector Agent]
     |                   |                               |                   |
     +-------------------+---------------+---------------+-------------------+
                                          |
                                          v
                              +---------------------------+
                              |   OBSERVATION SYNTHESIZER |
                              | (Aggregates into Report)  |
                              +---------------------------+
                                          |
                                          v
                              [ObservationReport]
                                          |
                                          v
                              Publish to Event Bus
```

### 2.1 Performance Measurement Agent
- **Role**: Calculates the financial outcome of each completed trade.
- **Metrics Computed**:
  - **Realized PnL**: `(Fill Price × Quantity) - (Entry Cost) - Fees - Slippage`
  - **Return on Capital (ROC)**: `PnL / Capital Allocated × 100`
  - **Commission & Fee Overhead**: Total fees as a percentage of gross trade value.
  - **Holding Duration**: Time elapsed between order submission and position close (`executed_at` delta).

### 2.2 Slippage & Execution Impact Agent
- **Role**: Measures how closely actual execution matched the strategy's intended price levels.
- **Metrics Computed**:
  - **Entry Slippage**: Deviation between `StrategySpecification.entry_price` and `TradeExecutionReceipt.fill_price`.
  - **Execution Impact Score**: Normalized impact as a percentage of the expected price.
  - **Fill Quality Rating**: Categorized as `EXCELLENT` (< 0.02%), `ACCEPTABLE` (0.02–0.10%), `POOR` (0.10–0.50%), or `SEVERE` (> 0.50%).

### 2.3 Prediction Deviation & Model Drift Agent
- **Role**: Audits Community 2's research predictions against actual post-trade market behavior.
- **Metrics Computed**:
  - **Directional Accuracy**: Did the market move in the predicted direction (Bull/Bear)?
  - **Target Price Accuracy**: How close did the actual price come to the thesis target price?
  - **Predicted vs. Actual Deviation**: $\frac{|\text{Predicted Outcome} - \text{Actual Outcome}|}{|\text{Predicted Outcome}|} \times 100$
  - **Model Drift Detection**: If rolling directional accuracy over the last 20 trades falls below 50%, a model drift alert is raised to Community 8 (Evolution).

### 2.4 Anomaly & Volatility Detector Agent
- **Role**: Identifies external events or market structure anomalies that occurred during the trade lifecycle.
- **Detection Targets**:
  - Macro news releases (CPI, FOMC, NFP) coinciding with trade execution window.
  - Flash crash or extreme volatility events (price movement > 3× ATR within a single bar).
  - Exchange outage or degraded connectivity periods overlapping with order submission.
  - Liquidity anomalies (abnormally thin order book depth during fill).

---

## 3. Post-Mortem Audit Methodology & Metrics

### 3.1 Execution Variance Formula
For every executed trade, the Slippage & Execution Impact Agent computes:

$$\text{Slippage Variance (\%)} = \frac{\text{Actual Fill Price} - \text{Expected Entry Price}}{\text{Expected Entry Price}} \times 100$$

| Slippage Variance | Classification | Action |
| :--- | :--- | :--- |
| $< 0.02\%$ | **Excellent** | No action required. |
| $0.02\% - 0.10\%$ | **Acceptable** | Log for trend monitoring. |
| $0.10\% - 0.50\%$ | **Poor** | Flag for execution review. Alert C8. |
| $> 0.50\%$ | **Severe** | Mandatory post-mortem. Review venue selection and order type. |

### 3.2 Prediction Accuracy Scoring
The Prediction Deviation Agent scores each trade's research quality:

| Metric | Scoring Method | Weight |
| :--- | :--- | :---: |
| **Directional Accuracy** | Binary: 1.0 if correct direction, 0.0 if wrong. | 50% |
| **Target Price Accuracy** | $1.0 - \min\left(1.0,\ \frac{|\text{Target} - \text{Actual}|}{|\text{Target} - \text{Entry}|}\right)$ | 30% |
| **Timing Accuracy** | $1.0 - \min\left(1.0,\ \frac{|\text{Expected Duration} - \text{Actual Duration}|}{\text{Expected Duration}}\right)$ | 20% |
| **Composite Prediction Score** | Weighted sum of above (0.0 to 1.0). | 100% |

### 3.3 Post-Mortem Report Structure
Every `ObservationReport` synthesizes findings into a structured record:

```
POST-MORTEM REPORT STRUCTURE
=================================
1. TRADE IDENTITY
   - execution_id, strategy_id, symbol, timeframe

2. INITIAL THESIS SUMMARY
   - Original hypothesis direction, supporting arguments, counter-arguments
   - Expected entry, stop-loss, take-profit from StrategySpecification

3. ACTUAL OUTCOME
   - Realized PnL (actual_pnl)
   - Fill price, slippage, fees from TradeExecutionReceipt

4. DEVIATION ANALYSIS
   - predicted_vs_actual_deviation score
   - Directional accuracy (correct / incorrect)
   - Slippage variance classification

5. EXTERNAL FACTORS
   - Anomalous events detected during trade lifecycle
   - Market regime classification at time of execution

6. LESSONS LEARNED
   - Actionable insights for Community 8 (Evolution)
   - Recommendations for agent prompt tuning or strategy parameter adjustment
```

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
Community 6 outputs instances of `ObservationReport` defined in `schemas/contracts.py`:

```python
class ObservationReport(BaseModel):
    observation_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this observation report"
    )
    execution_id: str = Field(
        ...,
        min_length=1,
        description="The execution receipt ID associated with this observation"
    )
    actual_pnl: float = Field(
        ...,
        description="The actual realized profit and loss of the trade"
    )
    predicted_vs_actual_deviation: float = Field(
        ...,
        description="Deviation measure between expected strategy outcome and actual results"
    )
    lessons_learned: list[str] = Field(
        ...,
        description="Key takeaways, insights, or updates extracted from the observation"
    )
```

### 4.2 Event Bus Routing
- **Subscription Topic**: `trade.executed` (`EventTopic.TRADE_EXECUTED`).
- **Publication Topic**: `observation.completed` (`EventTopic.OBSERVATION_COMPLETED`).
- **Target Subscribers**: Community 7 (Memory Architecture) for permanent indexing, Community 8 (Evolution Mechanisms) for agent optimization feedback.

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/CHECKPOINT.md) under **Doc 1.8: Community 6 Specification (Observation & Audit)**. Output payloads align with the `ObservationReport` schema in [contracts.py](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/schemas/contracts.py). Event topics are defined in [event_bus.py](file:///c:/Users/nahas/OneDrive/Desktop/AIOS/core/event_bus.py).
