"""Prompt Lab v0: golden-set evaluation harness with regression gates.

Implements AIOS-0X_PROMPT_REGISTRY.md section 5: prompts are evaluated against
golden cases before promotion; parse-rate below the gate blocks the version.
Works against ANY BaseModelGateway - production gateways when credentials
exist, ScriptedModel in CI (deterministic, zero-cost).
"""

import statistics

from pydantic import BaseModel, Field

from core.config import Settings
from core.model_gateway import (
    BaseModelGateway,
    ChatMessage,
    DecodeError,
    GatewayHTTPError,
    ModelUnavailableError,
    complete_structured,
)
from core.prompts import PromptRegistry

DEFAULT_PARSE_GATE = 0.9


class EvalCase(BaseModel):
    name: str
    variables: dict[str, str]


class PromptEvalResult(BaseModel):
    prompt_id: str
    version: str
    cases_run: int
    parsed_ok: int
    parse_rate: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: float
    total_cost_usd: float
    gate: float
    passed: bool


async def evaluate_prompt(
    registry: PromptRegistry,
    gateway: BaseModelGateway,
    contract: type[BaseModel],
    prompt_id: str,
    cases: list[EvalCase],
    settings: Settings,
    tier_model: str | None = None,
    gate: float = DEFAULT_PARSE_GATE,
) -> PromptEvalResult:
    """Render each case, call the gateway, decode against ``contract``."""
    spec = registry.get(prompt_id)
    parsed_ok = 0
    latencies: list[float] = []
    total_cost = 0.0

    for case in cases:
        try:
            rendered = spec.render(**case.variables)
            _, response = await complete_structured(
                gateway=gateway,
                contract=contract,
                messages=[ChatMessage(role="user", content=rendered)],
                settings=settings,
                model_hint=tier_model,
            )
            parsed_ok += 1
            latencies.append(float(response.latency_ms))
            total_cost = round(total_cost + response.cost_usd, 8)
        except (
            DecodeError,
            GatewayHTTPError,
            ModelUnavailableError,
            ValueError,
        ) as exc:
            print(f"[prompt-lab] case {case.name} failed: {exc}")

    rate = parsed_ok / len(cases) if cases else 0.0
    avg_latency = statistics.fmean(latencies) if latencies else 0.0
    return PromptEvalResult(
        prompt_id=prompt_id,
        version=spec.version,
        cases_run=len(cases),
        parsed_ok=parsed_ok,
        parse_rate=round(rate, 4),
        avg_latency_ms=round(avg_latency, 2),
        total_cost_usd=total_cost,
        gate=gate,
        passed=rate >= gate,
    )
