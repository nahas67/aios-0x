# AIOS-0X Prompt Registry
Version 0.1.0 | Status: EMPTY - no LLM integration exists yet; this registry is established before first prompt ships.

## 1. Current State (verified)
Zero prompts exist in the codebase. All agents are deterministic templates. This document defines
the governance that must exist BEFORE any prompt enters production.

## 2. Prompt Record Schema
```
PromptRecord:
  prompt_id: str (kebab-case)
  version: semver
  owner_agent_family: str
  task: str
  template: str (with typed variables)
  input_contract: Pydantic model ref
  output_contract: Pydantic model ref      # structured output REQUIRED, never free text parsing
  evaluation:
    dataset_ref: str                        # golden set id
    metrics: [accuracy, hallucination_rate, tool_error_rate, latency_p95, cost_per_call]
    gate: pass thresholds (regression = block)
  status: DRAFT|EVALUATED|CANARY|ACTIVE|RETIRED
  lineage: parent_prompt_id (for evolution)
  notes / changelog
```

## 3. Initial Prompt Backlog (to create with Slice 2 - LLM Gateway)

| prompt_id | Agent | Purpose | Output contract |
|---|---|---|---|
| research-bull-thesis-v1 | C2 bull | Bull case from market snapshot + memory context | ThesisSection |
| research-bear-thesis-v1 | C2 bear | Steelman bear case; MUST find 3+ counterarguments | ThesisSection |
| research-quant-alpha-v1 | C2 quant | Statistical significance review of claimed patterns | QuantReview |
| verification-factcheck-v1 | C3 fact-checker | Claim-by-claim verification vs evidence pack | FactCheckReport |
| verification-hallucination-v1 | C3 hunter | Detect unsupported claims, invented numbers/sources | HallucinationReport |
| strategy-parameterizer-v1 | C4 | Entry/stop/target from verified thesis + volatility state | StrategyParams |
| event-classifier-v1 | C10 event | Classify world events, severity, affected entities | EventClassification |
| expectation-analyzer-v1 | C10 | Expected-vs-actual-vs-priced-in reasoning | ExpectationAnalysis |
| scenario-builder-v1 | C10 | Base/bull/bear/unexpected/extreme with probabilities + invalidation conditions | ScenarioSet |
| postmortem-writer-v1 | C6 | Structured what-we-thought/what-happened/what-changes | Postmortem |

## 4. Rules (binding)
1. Every prompt has an output contract enforced by structured decoding; parse failure = retry/fallback.
2. Prompts never contain secrets or unrestricted trading authority language.
3. Prompt changes go through Prompt Lab: mutate -> evaluate on golden set -> compare -> canary -> promote.
   No direct production edit (Directive 61).
4. Anti-pattern lessons from postmortems are injected as data blocks, not hand-edits.
5. Model binding recorded per call for reproducibility (model version + prompt version + temperature).

## 5. Evaluation Harness (to build)
Golden sets per prompt family; regression suite runs in CI when prompts change;
DeepEval/Guardrails candidates benchmarked later (Group K) against Pydantic-first baseline.
