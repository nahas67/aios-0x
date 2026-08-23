"""Model router v0: task-tier based routing with honest unavailability.

Tiers (Directive 62):
- CHEAP: high-volume drafting (bull/bear theses, simple classification)
- REASONING: synthesis/judgment (moderator, verification adjudication)

The router never fabricates capability: when no gateway exists it reports
``available=False`` and callers must use their deterministic fallback.
"""

import logging
from dataclasses import dataclass

from core.config import Settings
from core.model_gateway import BaseModelGateway

logger = logging.getLogger(__name__)


class TaskTier:
    """Routing tier constants (kept as str for easy audit serialization)."""

    CHEAP = "cheap"
    REASONING = "reasoning"


@dataclass(frozen=True)
class RoutingDecision:
    tier: str
    available: bool
    model_id: str | None
    reason: str


class ModelRouter:
    """Chooses gateway+model per task tier from Settings."""

    def __init__(self, gateway: BaseModelGateway | None, settings: Settings) -> None:
        self._gateway = gateway
        self._settings = settings

    @property
    def gateway(self) -> BaseModelGateway | None:
        return self._gateway

    @property
    def llm_available(self) -> bool:
        return self._gateway is not None

    def resolve(self, tier: str) -> RoutingDecision:
        if not self._gateway:
            return RoutingDecision(
                tier=tier,
                available=False,
                model_id=None,
                reason="no gateway configured; deterministic mode",
            )
        if tier == TaskTier.REASONING:
            model_id: str | None = self._settings.research_model_reasoning
        elif tier == TaskTier.CHEAP:
            model_id = self._settings.research_model_cheap
        else:
            raise ValueError(f"unknown routing tier: {tier!r}")
        return RoutingDecision(
            tier=tier,
            available=True,
            model_id=model_id,
            reason=f"tier={tier} on provider={self._gateway.provider}",
        )
