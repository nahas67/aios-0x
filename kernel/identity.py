"""Identity Model: every meaningful action has a registered actor.

Actors are not implicit. They must be registered before they can request
capabilities. An actor's roles determine which capabilities it may request.
"""

from datetime import UTC
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActorType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"
    WORKFLOW = "WORKFLOW"
    EXTERNAL = "EXTERNAL"


class Role(StrEnum):
    ADMIN = "ADMIN"
    RISK_ADMIN = "RISK_ADMIN"
    OPERATOR = "OPERATOR"
    RESEARCHER = "RESEARCHER"
    VIEWER = "VIEWER"
    AGENT_RESEARCH = "AGENT_RESEARCH"
    AGENT_CRITIC = "AGENT_CRITIC"
    AGENT_STRATEGY = "AGENT_STRATEGY"
    SERVICE_EXECUTION = "SERVICE_EXECUTION"
    SERVICE_DATA = "SERVICE_DATA"


class Actor(BaseModel):
    """A registered identity that can request capabilities."""

    actor_id: str = Field(..., min_length=1, description="Unique identifier")
    actor_type: ActorType
    display_name: str = ""
    roles: frozenset[Role] = Field(default=frozenset(), description="Granted roles")
    metadata: dict[str, Any] = Field(default_factory=dict)
    registered_at: str = ""
    active: bool = True

    def has_role(self, role: Role) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: Role) -> bool:
        return bool(self.roles & set(roles))


class IdentityRegistry:
    """Registers and resolves actors. No implicit identities."""

    def __init__(self) -> None:
        self._actors: dict[str, Actor] = {}

    def register(
        self,
        actor_id: str,
        actor_type: ActorType,
        display_name: str = "",
        roles: set[Role] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Actor:
        if actor_id in self._actors:
            raise ValueError(f"actor already registered: {actor_id!r}")
        actor = Actor(
            actor_id=actor_id,
            actor_type=actor_type,
            display_name=display_name or actor_id,
            roles=frozenset(roles or set()),
            metadata=metadata or {},
            registered_at=datetime_now(),
        )
        self._actors[actor_id] = actor
        return actor

    def resolve(self, actor_id: str) -> Actor:
        actor = self._actors.get(actor_id)
        if actor is None:
            raise KeyError(f"unregistered actor: {actor_id!r}")
        if not actor.active:
            raise PermissionError(f"actor deactivated: {actor_id!r}")
        return actor

    def deactivate(self, actor_id: str) -> None:
        if actor_id in self._actors:
            self._actors[actor_id].active = False

    def list_agents(self) -> list[Actor]:
        return [a for a in self._actors.values() if a.actor_type == ActorType.AGENT]

    def list_all(self) -> list[Actor]:
        return list(self._actors.values())


def datetime_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
