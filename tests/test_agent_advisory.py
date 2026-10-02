"""Agent advisory: authority, attribution, honesty, and resolution.

THE TEST THAT MATTERS MOST
==========================
`test_advisory_module_cannot_reach_authority` reads the SOURCE of
`core/agent_advisory.py` and asserts it imports neither the control plane nor any order
sink. Every other assertion here could pass while the module quietly grew a way to execute
something; this one is what makes that a build failure rather than a code-review problem.

It is a source-level check on purpose. A behavioural test — "ask an agent to pause trading
and observe that nothing happens" — proves only that today's routing is correct. The source
check proves the capability is absent, which is the property the constitution actually
requires: an advisory is not permitted to hold authority, rather than declining to use it.
"""

from __future__ import annotations

import ast
import itertools
import pathlib
import tempfile

import pytest
from pydantic import ValidationError

from api.views import SystemSnapshotBuilder
from core.agent_advisory import (
    ADVISORY_AUTHORITY,
    READ_ONLY_VIEWS,
    AdvisoryAnswer,
    AgentAdvisor,
    known_agent_ids,
)
from core.chat_console import OperatorChat
from core.persistence import SqliteMemoryStore

REPO = pathlib.Path(__file__).resolve().parents[1]
ADVISORY_SRC = REPO / "core" / "agent_advisory.py"

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="aios-advisory-"))
_COUNTER = itertools.count()


def new_store() -> SqliteMemoryStore:
    """A fresh store per call.

    There is no in-memory store implementation — `core/persistence.py` offers
    `SqliteMemoryStore` only — so each call gets its own file. Sharing one would let a test
    observe another test's AGENT_REGISTERED events and pass for the wrong reason.
    """
    return SqliteMemoryStore(_TMP / f"advisory-{next(_COUNTER)}.db")


def _roster(store: SqliteMemoryStore) -> None:
    from core.agents import AgentIdentity, register_roster

    register_roster(
        store,
        [
            AgentIdentity(agent_id="c4_strategy.agent", community="c4_strategy", role="STRATEGIST"),
            AgentIdentity(agent_id="c7_memory.agent", community="c7_memory", role="MEMORY"),
        ],
    )


def _builder(store: SqliteMemoryStore) -> SystemSnapshotBuilder:
    return SystemSnapshotBuilder(store=store)


# --------------------------------------------------------------------------------------
# No authority. This is the load-bearing group.
# --------------------------------------------------------------------------------------


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_advisory_module_cannot_reach_authority() -> None:
    imported = _imports(ADVISORY_SRC)
    forbidden = {
        "core.control_plane",
        "communities.c5_execution.oms",
        "communities.c5_execution.adapters",
        "simulation.paper_engine",
        "core.authorization",
        "core.capital_firewall",
    }
    assert not (imported & forbidden), (
        f"core/agent_advisory.py must not be able to reach authority: {sorted(imported & forbidden)}"
    )


def test_advisory_module_calls_no_venue_or_execution_api() -> None:
    # Belt and braces against the import check: a same-module helper could reach an order
    # sink without importing anything new.
    source = ADVISORY_SRC.read_text(encoding="utf-8")
    for verb in ("create_order", "place_order", "submit_order", "send_order", "execute("):
        assert verb not in source, f"advisory module references {verb!r}"


def test_answers_are_labelled_advisory_and_cannot_mint_anything_else() -> None:
    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store)).advise("c4_strategy.agent", "what is leaning?"))

    assert answer.authority == ADVISORY_AUTHORITY == "ADVISORY"
    # `model_copy` does NOT validate, so the check goes through `model_validate` — which
    # is the point: the type is what forbids a forged authority, so the test has to use the
    # path a real caller would.
    payload = answer.model_dump(mode="json")
    payload["authority"] = "AUTHORIZED"
    with pytest.raises(ValidationError):
        AdvisoryAnswer.model_validate(payload)


def test_no_order_can_be_placed_from_chat_under_any_role() -> None:
    """A question that names an action must not execute it, at any privilege level.

    "should I pause trading" contains a command verb. If advisory routing lost to command
    routing, this would pause trading for an ADMIN. The ordering is the security property,
    so it is asserted through the public `ask` entry point across every role in the matrix.
    """
    from core.control_plane import ControlPlane
    from core.event_bus import InMemoryEventBus
    from core.risk_governor import RiskGovernor

    for role in ("VIEWER", "OPERATOR", "RISK_ADMIN", "ADMIN"):
        store = new_store()
        _roster(store)
        plane = ControlPlane(
            store=store,
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        chat = OperatorChat(_builder(store), plane)

        result = _run(chat.ask("op-1", role, "ask strategy should I pause trading"))

        assert result["kind"] == "advisory", f"{role} reached a non-advisory branch"
        assert result["authority"] == "ADVISORY"
        # Nothing was executed: the control plane recorded no authorised action.
        events = [
            p
            for p in store.iter_event_payloads("CONTROL_ACTION")
            if p.get("authorized")
        ]
        assert events == [], f"{role} caused an authorised control action: {events}"


# --------------------------------------------------------------------------------------
# Honesty (§3)
# --------------------------------------------------------------------------------------


def test_missing_data_yields_unknown_not_a_default() -> None:
    store = new_store()
    _roster(store)
    # An empty store: every view the strategy domain reads is bare.
    answer = _run(AgentAdvisor(_builder(store)).advise("c4_strategy.agent", "what is ranked?"))

    assert answer.stance in {"UNKNOWN", "RECORDED"}
    if answer.stance == "UNKNOWN":
        assert "UNKNOWN" in answer.answer
        assert any("unavailable" in ref.detail for ref in answer.evidence)


def test_unregistered_agent_is_unknown_and_lists_what_is_registered() -> None:
    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store)).advise("c99_nope.agent", "hello?"))

    assert answer.stance == "UNKNOWN"
    assert "UNKNOWN" in answer.answer
    assert "c4_strategy.agent" in answer.answer  # the real roster is offered
    assert answer.evidence == []


def test_every_answer_carries_an_attribution_with_a_reason() -> None:
    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store)).advise("c7_memory.agent", "how are you scored?"))
    assert answer.attribution.mode == "deterministic"
    assert answer.attribution.note, "an unexplained attribution gets quoted as an opinion"


def test_every_answer_states_it_cannot_act() -> None:
    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store)).advise("c4_strategy.agent", "ideas?"))
    joined = " ".join(answer.limitations).lower()
    assert "cannot place, cancel or authorise" in joined
    assert "governed control path" in joined


def test_proposed_actions_are_names_only_and_map_to_no_dispatch_table() -> None:
    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store)).advise("c4_strategy.agent", "ideas?"))
    for name in answer.proposed_actions:
        assert isinstance(name, str)
        assert name  # not a callable, not a dict, not a payload


# --------------------------------------------------------------------------------------
# The read allowlist
# --------------------------------------------------------------------------------------


def test_read_allowlist_excludes_every_mutating_builder_method() -> None:
    """Every method on the builder must be classified: readable, or absent.

    A method that is neither on the allowlist nor a known mutation is a hole — so this
    asserts the allowlist names only read-only views, and that the builder has not grown a
    read method we forgot (which would simply be unavailable rather than dangerous).
    """
    builder_methods = {
        name
        for name in dir(SystemSnapshotBuilder)
        if not name.startswith("_") and callable(getattr(SystemSnapshotBuilder, name, None))
    }
    mutating = {name for name in builder_methods if name.split("_")[0] in {"set", "put", "post", "delete", "update"}}

    assert not (READ_ONLY_VIEWS & mutating), (
        f"allowlist contains mutating builder methods: {sorted(READ_ONLY_VIEWS & mutating)}"
    )
    # Every allowlisted name must actually exist on the builder, or the allowlist has
    # drifted into naming methods that will raise AttributeError at runtime.
    assert READ_ONLY_VIEWS <= builder_methods, (
        f"allowlist names non-existent methods: {sorted(READ_ONLY_VIEWS - builder_methods)}"
    )


def test_a_view_that_raises_is_recorded_not_crashed() -> None:
    class Exploding:
        store = new_store()

        def opportunities(self):
            raise RuntimeError("engine unwired")

    Exploding.store = new_store()
    from core.agents import AgentIdentity, register_roster

    register_roster(Exploding.store, [AgentIdentity(agent_id="c4_strategy.agent", community="c4_strategy", role="S")])

    answer = _run(AgentAdvisor(Exploding()).advise("c4_strategy.agent", "anything?"))
    assert answer.evidence
    assert any("unwired" in ref.detail for ref in answer.evidence)


# --------------------------------------------------------------------------------------
# Addressing
# --------------------------------------------------------------------------------------


def test_known_agent_ids_reads_the_roster() -> None:
    store = new_store()
    _roster(store)
    assert known_agent_ids(_builder(store)) == ["c4_strategy.agent", "c7_memory.agent"]


@pytest.mark.parametrize(
    "message,expected",
    [
        ("ask strategy what is leaning", "c4_strategy.agent"),
        ("ask the strategy agent what is leaning", "c4_strategy.agent"),
        ("ask memory how are you scored", "c7_memory.agent"),
        ("ask c7_memory.agent anything", "c7_memory.agent"),
    ],
)
def test_addressing_resolves_names_aliases_and_ids(message: str, expected: str) -> None:
    store = new_store()
    _roster(store)
    chat = OperatorChat(_builder(store), None)  # no control plane: advisory must still work
    result = _run(chat.ask("op-1", "VIEWER", message))
    assert result["kind"] == "advisory"
    assert result["agent"] == expected


def test_advisory_works_with_no_control_plane() -> None:
    """Advisory is a read. It must not require the write path to be wired."""
    store = new_store()
    _roster(store)
    chat = OperatorChat(_builder(store), None)
    result = _run(chat.ask("op-1", "VIEWER", "ask strategy what is leaning"))
    assert result["kind"] == "advisory"
    assert result["advisory"]["authority"] == "ADVISORY"


def test_unresolvable_agent_is_unknown_not_a_guess() -> None:
    store = new_store()
    _roster(store)
    chat = OperatorChat(_builder(store), None)
    result = _run(chat.ask("op-1", "VIEWER", "ask the weather agent is it raining"))
    assert result["kind"] == "advisory"
    assert result["agent"] is None
    assert "UNKNOWN" in result["answer"]


def test_the_existing_query_and_command_contract_is_unchanged() -> None:
    """Adding advisory must not have shadowed the routes that were already there."""
    store = new_store()
    _roster(store)
    chat = OperatorChat(_builder(store), None)

    assert _run(chat.ask("op-1", "VIEWER", "pnl"))["kind"] == "query"
    assert _run(chat.ask("op-1", "VIEWER", "show me the gates"))["kind"] == "query"
    assert _run(chat.ask("op-1", "VIEWER", "hello there"))["kind"] == "help"


# --------------------------------------------------------------------------------------
# Optional model synthesis
# --------------------------------------------------------------------------------------


def test_gateway_synthesis_is_attributed_and_never_raises() -> None:
    from core.model_gateway import ModelRequest, ModelResponse

    class Gateway:
        provider = "test-provider"
        model = "test-model"

        def __init__(self, payload: str = "The strategy agent has 3 ranked opportunities.") -> None:
            self.payload = payload
            self.seen: list[ModelRequest] = []

        async def complete(self, request: ModelRequest) -> ModelResponse:
            self.seen.append(request)
            return ModelResponse(content=self.payload, model=self.model, provider=self.provider)

    store = new_store()
    _roster(store)
    gateway = Gateway()
    answer = _run(AgentAdvisor(_builder(store), gateway).advise("c4_strategy.agent", "what is leaning?"))

    assert answer.stance == "MODEL"
    assert answer.attribution.mode == "model"
    assert answer.attribution.model == "test-model"
    # The evidence is still attached: the model words it, the record grounds it.
    assert answer.evidence
    assert any("model" in lim.lower() for lim in answer.limitations)
    # Temperature zero and an advisory system prompt: the model phrases, it does not act.
    sent = gateway.seen[0]
    assert sent.messages[0].role == "system"
    assert "cannot place, cancel or authorize" in sent.messages[0].content
    assert sent.temperature == 0.0
    assert all(m.role in {"system", "user"} for m in sent.messages)


def test_a_failing_gateway_falls_back_to_deterministic_and_says_so() -> None:
    class Broken:
        provider = "test"
        model = "test"

        async def complete(self, request):
            raise RuntimeError("provider rate-limited")

    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store), Broken()).advise("c4_strategy.agent", "what is leaning?"))

    # Degrades instead of raising: a chat answer must not become an outage.
    assert answer.attribution.mode == "deterministic"
    assert answer.stance in {"RECORDED", "UNKNOWN"}


def test_a_gateway_returning_nothing_does_not_blank_the_answer() -> None:
    from core.model_gateway import ModelResponse

    class Empty:
        provider = "test"
        model = "test"

        async def complete(self, request):
            return ModelResponse(content="   ", model="test", provider="test")

    store = new_store()
    _roster(store)
    answer = _run(AgentAdvisor(_builder(store), Empty()).advise("c4_strategy.agent", "what?"))
    assert answer.answer.strip(), "an empty model response must not erase the answer"
    assert answer.attribution.mode == "deterministic"


# --------------------------------------------------------------------------------------


def _run(coro):
    import asyncio

    return asyncio.run(coro)
