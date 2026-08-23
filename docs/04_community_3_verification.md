# AIOS Specification 1.4: Community 3 Specification (Verification Firewall)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 3 (Verification Firewall)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 3 (C3) acts as the unyielding Quality Firewall for AIOS. Its primary objective is to audit every `CandidateHypothesis` issued by Community 2, eliminate hallucinations, verify underlying empirical evidence against raw data, re-calculate mathematical metrics, and assign a quantitative confidence score before permitting any hypothesis to proceed to strategy synthesis.

### 1.2 Core Responsibilities
- **Adversarial Fact-Checking**: Verify price levels, technical indicators, and news citations in the hypothesis against raw `MarketDataPayload` records.
- **Hallucination Detection**: Flag unsubstantiated LLM claims, phantom news events, or invalid price assertions.
- **Source & Data Integrity Validation**: Check data freshness, source reliability scores, and multi-feed confirmation.
- **Mathematical Audit**: Independently re-calculate stop distances, target levels, and expected risk-to-reward ratios.
- **Quantitative Confidence Scoring**: Assign a normalized confidence score from `0.0` to `100.0`.
- **Pass/Fail Gatekeeping**: Enforce a strict minimum confidence threshold ($\ge 70.0$). Only hypotheses meeting or exceeding this score earn `is_verified = True` and are dispatched to `verification.completed`. Failed hypotheses are rejected and archived to Community 7 (Memory Architecture) for post-mortem analysis.

---

## 2. Agent Hierarchy & Roles

Community 3 operates a multi-tiered verification hierarchy led by the Confidence Scoring & Gatekeeper Agent:

```
                               +-----------------------------+
                               |    CONFIDENCE SCORING &     |
                               |      GATEKEEPER AGENT       |
                               | (Assigns Score & Pass/Fail) |
                               +-----------------------------+
                                              ^
               +------------------------------+------------------------------+
               |                              |                              |
               v                              v                              v
+-----------------------------+ +-----------------------------+ +-----------------------------+
|     FACT CHECKER AGENT      | |    SOURCE VALIDATOR AGENT   | | MATH & STATISTICAL AGENT    |
| (Verifies Claims vs Data)   | | (Data Freshness & Integrity)| | (Recalculates R:R & Math)   |
+-----------------------------+ +-----------------------------+ +-----------------------------+
```

### 2.1 Fact Checker Agent
- **Role**: Audits text thesis and supporting arguments against underlying raw data feeds.
- **Focus**: Verifies price points, price change percentages, technical indicators (e.g. RSI, EMA crossovers), and news headline citations.

### 2.2 Source Validator Agent
- **Role**: Validates feed integrity, timestamp freshness, and publisher credibility scores.
- **Focus**: Checks that market data is not stale (e.g. timestamp $\le 5$ minutes old) and that news sources meet minimum reliability standards.

### 2.3 Math & Statistical Validator Agent
- **Role**: Performs independent mathematical validation of proposed risk parameters.
- **Focus**: Re-computes risk-to-reward ratios, validates stop-loss distance relative to average true range (ATR), and checks for logical numeric errors.

### 2.4 Confidence Scoring & Gatekeeper Agent (`VerificationAgent`)
- **Role**: Aggregates component scores, calculates the final confidence score (0.0 to 100.0), evaluates threshold compliance ($\ge 70.0$), updates `is_verified`, and routes reports.

---

## 3. Quantitative Audit Rubrics & Hallucination Defense

Community 3 evaluates every hypothesis using a strict 100-point quantitative rubric:

| Rubric Component | Max Points | Evaluation Criteria & Scoring Rules |
| :--- | :---: | :--- |
| **1. Fact & Data Verification** | **+40 pts** | Awarded if supporting arguments are fully verified against raw data records. Deductions/flagging applied for hallucinated claims, non-existent patterns, or incorrect price levels. |
| **2. Balanced Reasoning Check** | **+30 pts** | Awarded if the hypothesis includes explicit counter-arguments and risk factors. Hypotheses lacking risk evaluation are penalized for one-sided bias. |
| **3. Mathematical & Risk Validity** | **+30 pts** | Awarded if expected risk-to-reward ratio meets standards ($R:R \ge 1.5$) and price level logic is consistent. |
| **Total Max Score** | **100 pts** | Normalized range from `0.0` to `100.0`. |

### 3.1 Gatekeeping Threshold Rule
- **Minimum Passing Score**: `70.0 / 100.0`.
- **Verified Status**: If `confidence_score >= 70.0`, `is_verified` is automatically set to `True`.
- **Rejection Handling**: If `confidence_score < 70.0`, `is_verified` is set to `False`. The report is NOT published to `verification.completed`. Instead, an audit record containing `flagged_hallucinations` is stored in Community 7 (Memory Architecture) to inform Community 8 (Evolution) of research failure patterns.

---

## 4. Output Schema & Event Bus Routing

### 4.1 Output Schema Definition
Community 3 outputs instances of `VerificationReport` defined in `schemas/contracts.py`:

```python
class VerificationReport(BaseModel):
    report_id: str = Field(
        default_factory=generate_uuid,
        description="Unique UUID string representing this verification report",
    )
    hypothesis_id: str = Field(
        ..., min_length=1, description="The target CandidateHypothesis ID being verified"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=100.0, description="Verification confidence score from 0.0 to 100.0"
    )
    is_verified: bool = Field(
        default=False, description="Indicates if verified (True if confidence_score >= 70.0)"
    )
    verified_claims: list[str] = Field(
        ..., description="List of claims from the hypothesis successfully verified"
    )
    flagged_hallucinations: list[str] = Field(
        ..., description="List of assumptions or claims flagged as hallucinated or incorrect"
    )
    verification_notes: str = Field(
        ..., description="Detailed notes and findings from the verification process"
    )

    @model_validator(mode="after")
    def determine_is_verified(self) -> "VerificationReport":
        """Compute is_verified status based on confidence score threshold."""
        threshold = 70.0
        self.is_verified = self.confidence_score >= threshold
        return self
```

### 4.2 Event Bus Routing
- **Subscription Topic**: `research.hypothesis_generated` (`EventTopic.HYPOTHESIS_GENERATED`) via `on_hypothesis_generated()` callback.
- **Publication Topic (Passed Only)**: `verification.completed` (`EventTopic.VERIFICATION_COMPLETED`).
- **Target Subscriber**: Community 4 (Strategy Generation).

---

## 5. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](CHECKPOINT.md) under **Doc 1.4: Community 3 Specification (Verification Firewall)**. Implementation code resides in `communities/c3_verification/` and unit tests in `tests/test_c3_verification.py`.
