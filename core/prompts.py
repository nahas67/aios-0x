"""Prompt registry: versioned prompts with typed variables and render checks.

Implements AIOS-0X_PROMPT_REGISTRY.md governance: prompts are code-reviewed
records, rendered deterministically, and evaluated by the Prompt Lab before a
version is promoted. Templates use ``{{var}}`` placeholders; rendering fails
loudly on missing or unexpected variables.
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

_VAR_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class PromptSpec(BaseModel):
    prompt_id: str = Field(min_length=1)
    version: str = Field(default="v1", min_length=1)
    description: str = ""
    template: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        found = sorted(set(_VAR_RE.findall(self.template)))
        declared = sorted(set(self.variables))
        if found != declared:
            raise ValueError(
                f"prompt {self.prompt_id}: template vars {found} != declared {declared}"
            )

    def render(self, **variables: str) -> str:
        provided = set(variables)
        expected = set(self.variables)
        missing = expected - provided
        extra = provided - expected
        if missing or extra:
            raise ValueError(
                f"render {self.prompt_id}: missing={sorted(missing)} unexpected={sorted(extra)}"
            )
        rendered = _VAR_RE.sub(lambda m: variables[m.group(1)], self.template)
        return rendered


class PromptRegistry:
    """In-memory registry seeded with built-ins; optionally loaded from JSON files."""

    def __init__(self) -> None:
        self._prompts: dict[tuple[str, str], PromptSpec] = {}
        for spec in BUILTIN_PROMPTS:
            self.register(spec)
        # Convenience aliases: latest version of each id
        self._latest: dict[str, PromptSpec] = {}
        for spec in self._prompts.values():
            current = self._latest.get(spec.prompt_id)
            if current is None or spec.version >= current.version:
                self._latest[spec.prompt_id] = spec

    def register(self, spec: PromptSpec) -> None:
        key = (spec.prompt_id, spec.version)
        self._prompts[key] = spec

    def get(self, prompt_id: str, version: str | None = None) -> PromptSpec:
        if version is None:
            spec = self._latest.get(prompt_id)
            if spec is None:
                raise KeyError(f"unknown prompt id: {prompt_id!r}")
            return spec
        key = (prompt_id, version)
        if key not in self._prompts:
            raise KeyError(f"unknown prompt: {key}")
        return self._prompts[key]

    def ids(self) -> list[str]:
        return sorted(self._latest)

    def load_dir(self, path: str | Path) -> int:
        """Load additional specs from JSON files; returns count loaded."""
        count = 0
        for file in sorted(Path(path).glob("*.json")):
            spec = PromptSpec.model_validate_json(file.read_text(encoding="utf-8"))
            self.register(spec)
            count += 1
        return count


BULL_THESIS_V1 = PromptSpec(
    prompt_id="research-bull-thesis",
    version="v1",
    description="Steelmanned bull case from a market snapshot.",
    variables=["symbol", "timeframe", "close", "momentum_pct", "range_pct", "sentiment"],
    template=(
        "You are the Bull Analyst in an investment research debate.\n"
        "Market snapshot for {{symbol}} ({{timeframe}}):\n"
        "- close={{close}}, momentum={{momentum_pct}}%, bar range={{range_pct}}%, "
        "avg news sentiment={{sentiment}}\n\n"
        "Argue the STRONGEST honest bull case. Rules:\n"
        "1. You may only cite numbers present in the snapshot.\n"
        "2. Include at least one falsifiable claim.\n"
        "3. Acknowledge the single biggest risk in one sentence.\n\n"
        'Respond with ONLY a JSON object: {"argument": string, "falsifiable_claim": string, '
        '"cited_numbers": [number...]}.'
    ),
)

BEAR_THESIS_V1 = PromptSpec(
    prompt_id="research-bear-thesis",
    version="v1",
    description="Steelmanned bear case from a market snapshot.",
    variables=["symbol", "timeframe", "close", "momentum_pct", "range_pct", "sentiment"],
    template=(
        "You are the Bear Analyst in an investment research debate.\n"
        "Market snapshot for {{symbol}} ({{timeframe}}):\n"
        "- close={{close}}, momentum={{momentum_pct}}%, bar range={{range_pct}}%, "
        "avg news sentiment={{sentiment}}\n\n"
        "Argue the STRONGEST honest bear case against the bull. Rules:\n"
        "1. You may only cite numbers present in the snapshot.\n"
        "2. Include at least one falsifiable claim.\n"
        "3. Concede the strongest bull point in one sentence.\n\n"
        'Respond with ONLY a JSON object: {"argument": string, "falsifiable_claim": string, '
        '"cited_numbers": [number...]}.'
    ),
)

QUANT_REVIEW_V1 = PromptSpec(
    prompt_id="research-quant-review",
    version="v1",
    description="Statistical sanity review of both debate cases.",
    variables=["bull_argument", "bear_argument"],
    template=(
        "You are the Quant Reviewer. Given two debate arguments:\n"
        "BULL: {{bull_argument}}\n"
        "BEAR: {{bear_argument}}\n\n"
        "Identify statistical weaknesses (sample size, regime dependence, base rates).\n"
        "Do NOT invent numbers. Reference only numbers contained in the arguments.\n\n"
        'Respond with ONLY: {"weaknesses": [string...], "verdict": "PROCEED"|"REJECT"}'
    ),
)

MODERATOR_SYNTHESIS_V1 = PromptSpec(
    prompt_id="research-moderator-synthesis",
    version="v1",
    description="Synthesize the debate into one balanced CandidateHypothesis payload.",
    variables=[
        "symbol",
        "timeframe",
        "bull_argument",
        "bear_argument",
        "quant_weaknesses",
        "rr_target",
    ],
    template=(
        "You are the Debate Moderator for {{symbol}} ({{timeframe}}).\n"
        "BULL: {{bull_argument}}\n"
        "BEAR: {{bear_argument}}\n"
        "QUANT WEAKNESSES: {{quant_weaknesses}}\n\n"
        "Synthesize ONE balanced hypothesis with:\n"
        "- 2-4 supporting_arguments (from bull + evidence)\n"
        "- 2-4 counter_arguments (from bear + quant weaknesses)\n"
        "- expected_risk_reward_ratio >= {{rr_target}} (a number)\n\n"
        "Respond with ONLY JSON:\n"
        '{"supporting_arguments": [string...], "counter_arguments": [string...], '
        '"expected_risk_reward_ratio": number}'
    ),
)


BUILTIN_PROMPTS: tuple[PromptSpec, ...] = (
    BULL_THESIS_V1,
    BEAR_THESIS_V1,
    QUANT_REVIEW_V1,
    MODERATOR_SYNTHESIS_V1,
)
