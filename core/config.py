"""AIOS runtime configuration.

All secrets come exclusively from the environment (pydantic-settings) per
.cursorrules and Directive 46. Absence of credentials is a normal, logged
state: the system degrades to deterministic mode and never fabricates LLM
capability.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings; every field has a safe default."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------- gateway
    model_provider: str = Field(
        default="none",
        description="'openai' | 'openai_compatible' | 'anthropic' | 'none' (deterministic mode)",
    )
    openai_api_key: str | None = Field(default=None, repr=False)
    anthropic_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str = Field(
        default="https://api.xkiro.com/v1",
        description="OpenAI-compatible endpoint (DeepSeek, Together, local vLLM, OpenRouter...)",
    )

    # ---------------------------------------------------------- data providers
    finnhub_api_key: str | None = Field(default=None, repr=False)
    gnews_api_key: str | None = Field(default=None, repr=False)
    newsdata_api_key: str | None = Field(default=None, repr=False)
    marketstack_api_key: str | None = Field(default=None, repr=False)
    fred_api_key: str | None = Field(default=None, repr=False)
    telegram_bot_token: str | None = Field(default=None, repr=False)
    telegram_chat_id: str | None = Field(default=None, repr=False)

    # ------------------------------------------------------------- routing
    research_model_cheap: str = Field(
        default="gpt-4o-mini", description="Cheap tier for bull/bear drafting"
    )
    research_model_reasoning: str = Field(
        default="gpt-4o", description="Reasoning tier for moderator synthesis"
    )
    verification_model: str = Field(default="gpt-4o-mini")

    # ------------------------------------------------------------ behaviour
    research_mode: str = Field(
        default="auto",
        description="'deterministic' forces template research; 'auto' uses debate when models available",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1200, gt=0)

    # Cost table USD per 1M tokens (input, output); extend per provider pricing
    cost_usd_per_mtok_input: float = Field(default=0.15)
    cost_usd_per_mtok_output: float = Field(default=0.60)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
