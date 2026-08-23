"""Agent identity registry (Directive 15/79): who is who, who may do what.

The composition root registers every operational agent at boot; registrations
land in the hash-chained audit log as AGENT_REGISTERED events so identity is
tamper-evident and queryable.
"""

from typing import Any

from pydantic import BaseModel, Field

from core.persistence import BaseMemoryStore


class AgentIdentity(BaseModel):
    agent_id: str
    community: str
    role: str
    publishes: list[str] = Field(default_factory=list)
    subscribes: list[str] = Field(default_factory=list)
    version: str = "v1"


def register_roster(store: BaseMemoryStore, roster: list[AgentIdentity]) -> int:
    """Persist identities; returns count registered."""
    for agent in roster:
        store.append_event(
            "AGENT_REGISTERED",
            agent.agent_id,
            agent.model_dump(mode="json"),
        )
    return len(roster)


def registered_agents(store: BaseMemoryStore) -> dict[str, Any]:
    """Latest registration per agent_id."""
    out: dict[str, Any] = {}
    for payload in store.iter_event_payloads("AGENT_REGISTERED"):
        out[payload.get("agent_id", "?")] = payload
    return out
