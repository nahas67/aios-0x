"""AIOS runtime configuration.

All secrets come exclusively from the environment (pydantic-settings) per
.cursorrules and Directive 46. Absence of credentials is a normal, logged
state: the system degrades to deterministic mode and never fabricates LLM
capability.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings; every field has a safe default."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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
    api_auth_token: str | None = Field(default=None, repr=False)

    # ------------------------------------------------------- server identity
    # These values are server-side configuration only. They are never sent to
    # the browser as credentials; the API resolves the bearer token to them.
    server_operator_id: str = Field(
        default="principal", validation_alias="AIOS_OPERATOR_ID"
    )
    server_default_role: str = Field(
        default="VIEWER", validation_alias="AIOS_DEFAULT_ROLE"
    )
    server_token_map: str | None = Field(
        default=None, validation_alias="AIOS_TOKEN_MAP", repr=False
    )

    # ------------------------------------------------------------- routing
    research_model_cheap: str = Field(
        default="gpt-4o-mini", description="Cheap tier for bull/bear drafting"
    )
    research_model_reasoning: str = Field(
        default="gpt-4o", description="Reasoning tier for moderator synthesis"
    )
    verification_model: str = Field(default="gpt-4o-mini")

    # ------------------------------------------------------------ behaviour
    autonomy_mode: str = Field(
        default="SUPERVISED",
        description="Production execution mode: MANUAL | ASSISTED | SUPERVISED | AUTONOMOUS",
    )
    research_mode: str = Field(
        default="auto",
        description="'deterministic' forces template research; 'auto' uses debate when models available",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1200, gt=0)

    # ---------------------------------------------------------------- data tier
    database_url: str | None = Field(
        default=None,
        repr=False,
        description=(
            "PostgreSQL DSN (postgres://...) promotes the memory store to the "
            "server-grade Data & State Plane tier; None keeps local SQLite."
        ),
    )

    # ------------------------------------------------------------- autoresearch
    auto_research: bool = Field(
        default=True,
        description=(
            "After each replay, deterministically propose new hypotheses from "
            "settled outcomes (UPDATE-HYPOTHESIS-SPACE step of the core loop)."
        ),
    )

    # ---------------------------------------------------------------- models
    ml_training: bool = Field(
        default=True,
        description=(
            "After each replay, train the stdlib logistic direction model on "
            "the replay closes and register it walk-forward-evaluated in the "
            "model registry (original architecture §12 lifecycle)."
        ),
    )

    # Cost table USD per 1M tokens (input, output); extend per provider pricing
    cost_usd_per_mtok_input: float = Field(default=0.15)
    cost_usd_per_mtok_output: float = Field(default=0.60)

    @field_validator("autonomy_mode", mode="before")
    @classmethod
    def validate_autonomy_mode(cls, value: object) -> str:
        """Reject unsafe/unknown execution modes during configuration load."""
        mode = str(value).strip().upper()
        allowed = {"MANUAL", "ASSISTED", "SUPERVISED", "AUTONOMOUS"}
        if mode not in allowed:
            raise ValueError(
                f"invalid autonomy_mode {value!r}; expected one of {sorted(allowed)}"
            )
        return mode

    @field_validator("server_default_role", mode="before")
    @classmethod
    def validate_server_default_role(cls, value: object) -> str:
        role = str(value).strip().upper()
        allowed = {"VIEWER", "OPERATOR", "RISK_ADMIN", "ADMIN"}
        if role not in allowed:
            raise ValueError(
                f"invalid server_default_role {value!r}; expected one of {sorted(allowed)}"
            )
        return role

    @field_validator("server_operator_id", mode="before")
    @classmethod
    def validate_server_operator_id(cls, value: object) -> str:
        operator_id = str(value).strip()
        if not operator_id or len(operator_id) > 128:
            raise ValueError("server_operator_id must be 1-128 non-whitespace characters")
        return operator_id


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
