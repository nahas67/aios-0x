"""Topic-level access control (Security Model section 3).

Agents get explicit publish/subscribe capabilities per topic. ``ACLBus``
wraps any BaseEventBus: system components use the normal API; agents must
present a principal via ``publish_as``/``subscribe_as`` and are denied
otherwise. Denials raise PermissionError - loud, never silent.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from core.event_bus import BaseEventBus, EventTopic

EventHandler = Callable[[BaseModel], Awaitable[None]]


@dataclass(frozen=True)
class AgentPrincipal:
    """Capability set for one agent identity."""

    agent_id: str
    publish_topics: frozenset[EventTopic] = field(default_factory=frozenset)
    subscribe_topics: frozenset[EventTopic] = field(default_factory=frozenset)


class ACLBus(BaseEventBus):
    """Enforcing decorator around another bus."""

    def __init__(self, inner: BaseEventBus) -> None:
        self._inner = inner
        self._principals: dict[str, AgentPrincipal] = {}

    def register(self, principal: AgentPrincipal) -> None:
        self._principals[principal.agent_id] = principal

    def _require_publish(self, agent_id: str, topic: EventTopic) -> AgentPrincipal:
        principal = self._principals.get(agent_id)
        if principal is None:
            raise PermissionError(f"unknown agent identity: {agent_id!r}")
        if topic not in principal.publish_topics:
            raise PermissionError(f"agent {agent_id!r} may not publish to {topic.value}")
        return principal

    # -------------------------------------------------- system-level pass-through

    async def publish(self, topic: EventTopic, payload: BaseModel) -> None:
        await self._inner.publish(topic, payload)

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        await self._inner.subscribe(topic, handler)

    async def start(self) -> None:
        await self._inner.start()

    async def stop(self) -> None:
        await self._inner.stop()

    async def wait_until_idle(self) -> None:
        await self._inner.wait_until_idle()

    # ------------------------------------------------------------- agent paths

    async def publish_as(self, agent_id: str, topic: EventTopic, payload: BaseModel) -> None:
        self._require_publish(agent_id, topic)
        await self._inner.publish(topic, payload)

    async def subscribe_as(
        self,
        agent_id: str,
        topic: EventTopic,
        handler: EventHandler,
    ) -> None:
        principal = self._principals.get(agent_id)
        if principal is None:
            raise PermissionError(f"unknown agent identity: {agent_id!r}")
        if topic not in principal.subscribe_topics:
            raise PermissionError(f"agent {agent_id!r} may not subscribe to {topic.value}")
        await self._inner.subscribe(topic, handler)
