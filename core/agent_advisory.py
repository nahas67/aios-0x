"""Agent advisory: let an operator question a named agent and get a sourced opinion.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
==============================================

`OperatorChat` could already run deterministic regex over read-only snapshots and could
already execute `ControlPlane` actions with the operator's own role. It had never reached
an agent. This module adds the missing third thing: an agent can be *asked*.

It cannot *act*. An advisory answer carries evidence, an opinion, an attribution and a list
of action NAMES it would suggest — and nothing else. There is no call from this module to
`ControlPlane`, to an OMS, or to any order sink, and `tests/test_agent_advisory.py` asserts
that structurally rather than by inspection. That is `CONSTITUTION.md` §2.6: the governed
path stays the only path that moves capital.

WHY AGENTS ARE NOT INVOKED
==========================

The agent classes in `communities/` are event-bus SINKS with `on_*(payload)` methods.
`StrategyAgent.generate_strategy`, `ResearchAgent.analyze_and_generate_hypothesis` and
`EvolutionAgent.evaluate_and_evolve` all mutate state when called — they publish
strategies, create hypotheses, emit evolution signals. Calling one to answer a chat message
would mean a read path with write side effects, driven by an operator's typing.

So an advisor never invokes an agent. It reports what that agent has already recorded,
read out of the hash-chained audit log, and optionally asks a model to interpret that
record. "What does the strategy agent think?" is answered from the strategy agent's
published record — not by waking it up.

WHY THE READS ARE AN ALLOWLIST
==============================

`SystemSnapshotBuilder` mixes read-only views with mutating ones: alongside `risk_state()`
and `positions()` it has `settings_plane_put()`. A route table that resolved view names
dynamically (`getattr(builder, name)`) would be one careless edit away from a chat message
changing platform settings. `READ_ONLY_VIEWS` is therefore a closed frozenset, every domain
lists its views by hand, and `_gather` raises on anything absent from it. There is no code
path from an operator's words to an arbitrary builder method.

HONESTY, PER §3
===============

  - §3.1 no fabricated capability: every answer names how it was produced.
  - §3.2 missing data means UNKNOWN: a domain with no readable evidence returns
    `stance="UNKNOWN"` and says which view was unavailable. It never substitutes a default.
  - Model unavailability is stated, not hidden: `model_gateway` is optional and returns
    `None` with zero credentials, so the deterministic answer is produced and the
    attribution says `deterministic`.

ZONE NOTE. This module sits in D (control, beside `chat_console.py`) and imports
`core.model_gateway` from C (intelligence). D -> C is the permitted direction; the
forbidden one is C -> A, the capital zone. It is deliberately NOT added to
`tests/test_authority_chain.py`'s `DETERMINISTIC_CORE`, which is the list of modules whose
answers must stay reproducible because they decide whether capital moves. An advisory never
does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    from core.model_gateway import BaseModelGateway

#: The one and only authority an advisory carries. Not a size, not an order, not a
#: permission: an opinion with its sources attached.
ADVISORY_AUTHORITY = "ADVISORY"

#: How the answer was produced. `deterministic` means no model was consulted — the text was
#: composed from the audit record. Stated on every answer so nobody reads a composed
#: summary as a model's judgement, or vice versa.
AttributionMode = Literal["deterministic", "model"]


class Attribution(BaseModel):
    """Who produced this answer, and by what means."""

    mode: AttributionMode
    provider: str | None = None
    model: str | None = None
    #: Why the mode is what it is. Always populated: an unexplained attribution is how a
    #: composed summary starts being quoted as an opinion.
    note: str


class EvidenceRef(BaseModel):
    """One read-only view consulted, and whether it had anything in it."""

    label: str
    #: The builder method. Recorded so an operator can ask "where did that come from?" and
    #: get a name rather than a shrug.
    source: str
    available: bool
    rows: int | None = None
    detail: str = ""


class AdvisoryAnswer(BaseModel):
    """A sourced, attributed, non-executable opinion."""

    #: Literal, and asserted in tests. A caller receiving this cannot mistake it for an
    #: authorization, because the type says so and the value cannot be anything else.
    authority: Literal["ADVISORY"] = "ADVISORY"

    agent_id: str
    community: str
    role: str
    question: str
    answer: str
    stance: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    #: Action NAMES the advisor would suggest. Deliberately strings. Nothing in this module
    #: can execute one, so the strongest thing that can happen here is a human reading a
    #: name and typing the command themselves — through the governed path, under their own
    #: role.
    proposed_actions: list[str] = Field(default_factory=list)
    attribution: Attribution
    #: Stated limits on this answer. Standing honesty, not a disclaimer template.
    limitations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# The read allowlist
# --------------------------------------------------------------------------------------

#: Every builder method an advisor may call. Closed by construction: `_gather` refuses
#: anything not named here, so adding a mutating view to `SystemSnapshotBuilder` cannot
#: silently widen what chat can reach.
READ_ONLY_VIEWS: frozenset[str] = frozenset(
    {
        "agents",
        "approvals_view",
        "evaluations_view",
        "events",
        "executive",
        "executions",
        "health",
        "knowledge",
        "models_view",
        "opportunities",
        "platform_feed",
        "portfolio",
        "positions",
        "research_quality",
        "risk_state",
    }
)

#: community -> ((label, builder method), ...). Hand-listed rather than derived, so that
#: adding a community requires deciding what that community is allowed to be asked about.
_DOMAIN_EVIDENCE: dict[str, tuple[tuple[str, str], ...]] = {
    "c1_data": (("data versions", "events"),),
    "c2_research": (("hypothesis knowledge", "knowledge"), ("calibration", "research_quality")),
    "c3_verification": (("evaluation records", "evaluations_view"),),
    "c4_strategy": (("ranked opportunities", "opportunities"),),
    "c5_execution": (("recent executions", "executions"), ("open positions", "positions")),
    "c6_observation": (("recent events", "events"),),
    "c7_memory": (("agent reputation", "agents"),),
    "c8_evolution": (("promotion approvals", "approvals_view"), ("evaluation records", "evaluations_view")),
    "c9_portfolio": (("portfolio", "portfolio"), ("risk state", "risk_state")),
    "c10_macro": (("recent events", "events"),),
    "c11_finance": (("accounting", "approvals_view"),),
}

_FALLBACK_EVIDENCE: tuple[tuple[str, str], ...] = (("recent events", "events"),)

#: Actions an advisor may NAME. A display vocabulary, not an executable one — there is no
#: dispatch table anywhere that maps these strings to calls.
_SUGGESTABLE: dict[str, tuple[str, ...]] = {
    "c2_research": ("evaluate_trial", "reject challenger"),
    "c3_verification": ("evaluate_trial",),
    "c4_strategy": ("set_autonomy supervised",),
    "c5_execution": ("pause_trading",),
    "c9_portfolio": ("set_autonomy supervised", "pause_trading"),
}

_SYSTEM_PROMPT = (
    "You are advising a human operator of an automated investment platform. "
    "You may only describe the EVIDENCE below. Do not invent prices, fills, positions or "
    "capability. Do not instruct, and do not claim authority: you cannot place, cancel or "
    "authorize anything, and any action must be performed by the operator through the "
    "governed control path. If the evidence does not answer the question, say so. "
    "Answer in at most four sentences."
)


class _Unavailable(Exception):
    """A view could not be read. Recorded, never substituted."""


def _count_rows(data: Any) -> int | None:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "items", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return None
    return None


def _summarize(data: Any) -> str:
    if isinstance(data, list):
        return f"{len(data)} record(s)"
    if isinstance(data, dict):
        if data.get("status") == "UNAVAILABLE" or "unavailable" in data:
            # The builder's own honest-absence marker, passed through rather than papered
            # over. `views.py` builds these when a component is unwired.
            return f"unavailable ({data.get('reason', 'no reason given')})"
        return f"{len(data)} field(s): " + ", ".join(list(data)[:4])
    return type(data).__name__


def _gather(builder: Any, community: str) -> list[EvidenceRef]:
    """Read this community's allowlisted views. Never calls anything else."""
    sources = _DOMAIN_EVIDENCE.get(community, _FALLBACK_EVIDENCE)
    refs: list[EvidenceRef] = []
    for label, method in sources:
        if method not in READ_ONLY_VIEWS:
            # A programming error, not a runtime condition. Failing loudly here is the whole
            # point of the allowlist: a new domain cannot quietly acquire a privileged view.
            raise _Unavailable(f"{method!r} is not on the read-only allowlist")
        try:
            data = getattr(builder, method)()
        except Exception as exc:  # a view may raise when its component is unwired
            refs.append(
                EvidenceRef(
                    label=label,
                    source=method,
                    available=False,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        detail = _summarize(data)
        refs.append(
            EvidenceRef(
                label=label,
                source=method,
                available="unavailable" not in detail,
                rows=_count_rows(data),
                detail=detail,
            )
        )
    return refs


def _compose(agent_id: str, community: str, role: str, question: str, evidence: list[EvidenceRef]) -> tuple[str, str]:
    """Deterministic answer text and stance. No model, no inference, no invention."""
    readable = [ref for ref in evidence if ref.available]
    if not readable:
        return (
            f"UNKNOWN. No readable evidence for {agent_id} ({community}). "
            f"Asked: {question!r}. Every view consulted was unavailable: "
            + "; ".join(f"{ref.source} ({ref.detail})" for ref in evidence)
            + ". Nothing is inferred from absence.",
            "UNKNOWN",
        )

    parts = [f"{agent_id} ({community}, {role}) has recorded:"]
    for ref in readable:
        parts.append(f"- {ref.label}: {ref.detail}")
    parts.append(
        "This is the agent's own published record, summarised. It is not a judgement and it "
        "authorises nothing."
    )
    return " ".join(parts), "RECORDED"


class AgentAdvisor:
    """Answers one agent's questions from its audit record. Holds no authority."""

    def __init__(self, builder: Any, gateway: BaseModelGateway | None = None) -> None:
        self._builder = builder
        self._gateway = gateway

    async def advise(self, agent_id: str, question: str) -> AdvisoryAnswer:
        """Async because the optional gateway is.

        `BaseModelGateway.complete` is `async def`, so a synchronous call here would have
        returned an un-awaited coroutine — which stringifies to a repr and would have been
        served to the operator as the agent's answer. Caught by mypy, not by a test: the
        gateway is optional, so the broken path is the one every default deployment never
        takes.
        """
        from core.agents import registered_agents

        roster = registered_agents(self._builder.store)
        record = roster.get(agent_id)
        if record is None:
            return self._unknown_agent(agent_id, question)

        community = str(record.get("community", "unknown"))
        role = str(record.get("role", "unknown"))

        try:
            evidence = _gather(self._builder, community)
        except _Unavailable as exc:
            evidence = [EvidenceRef(label="allowlist", source="READ_ONLY_VIEWS", available=False, detail=str(exc))]

        # Attribution is assigned from the DETERMINISTIC path, and only upgraded if a model
        # actually produced text. The first version computed it from `self._gateway is not
        # None`, which labelled a fallback answer "model" whenever a gateway object existed
        # — including when the provider had thrown and the deterministic text was what the
        # operator was reading. §3.1 says never fabricate; an attribution that describes an
        # intent rather than an outcome is the same defect in a smaller package.
        answer, stance = _compose(agent_id, community, role, question, evidence)
        result = AdvisoryAnswer(
            agent_id=agent_id,
            community=community,
            role=role,
            question=question,
            answer=answer,
            stance=stance,
            evidence=evidence,
            proposed_actions=list(_SUGGESTABLE.get(community, ())),
            attribution=self._deterministic_attribution(evidence),
            limitations=self._limitations(stance),
        )

        enriched = await self._ask_model(question, evidence)
        if enriched is not None:
            text, attribution = enriched
            result = result.model_copy(
                update={
                    "answer": text,
                    "attribution": attribution,
                    "stance": "MODEL",
                    "limitations": [
                        *result.limitations,
                        "A model wrote this text over the evidence above; the evidence is "
                        "authoritative and the wording is not.",
                    ],
                }
            )
        return result

    # ------------------------------------------------------------- internals

    def _unknown_agent(self, agent_id: str, question: str) -> AdvisoryAnswer:
        from core.agents import registered_agents

        known = sorted(registered_agents(self._builder.store))
        return AdvisoryAnswer(
            agent_id=agent_id,
            community="unknown",
            role="unknown",
            question=question,
            answer=(
                f"UNKNOWN. No agent named {agent_id!r} has registered an identity, so there "
                f"is no record to summarise. Registered agents: "
                + (", ".join(known) if known else "(none)")
                + ". Nothing is inferred from the empty roster."
            ),
            stance="UNKNOWN",
            evidence=[],
            attribution=Attribution(mode="deterministic", note="no agent record; no model consulted"),
            limitations=[
                "An unregistered name is answered as UNKNOWN rather than matched loosely.",
                *self._limitations("UNKNOWN"),
            ],
        )

    def _deterministic_attribution(self, evidence: list[EvidenceRef]) -> Attribution:
        """Assigned first, and kept unless a model genuinely replaced the text."""
        return Attribution(
            mode="deterministic",
            note=(
                "composed from the audit record; no model was consulted "
                f"({len(evidence)} view(s) read)"
            ),
        )

    @staticmethod
    def _limitations(stance: str) -> list[str]:
        base = [
            "Advisory only. This agent cannot place, cancel or authorise anything.",
            "Any action named here must be typed by the operator through the governed "
            "control path, under their own role.",
        ]
        if stance == "UNKNOWN":
            base.append("Evidence was missing, so nothing was concluded from it.")
        return base

    async def _ask_model(self, question: str, evidence: list[EvidenceRef]) -> tuple[str, Attribution] | None:
        """Optional model synthesis. Returns None on any failure — never raises.

        The gateway is optional by design (`build_gateway` returns None with no
        credentials), and a chat answer must not become an outage because a provider is
        rate-limiting. Every failure path returns None, and the deterministic answer stands
        with an attribution that says a model was not consulted.
        """
        if self._gateway is None:
            return None
        try:
            from core.model_gateway import ChatMessage, ModelRequest

            readable = [ref for ref in evidence if ref.available]
            if not readable:
                return None
            evidence_text = "\n".join(f"{ref.label} [{ref.source}]: {ref.detail}" for ref in readable)
            response = await self._gateway.complete(
                ModelRequest(
                    messages=[
                        ChatMessage(role="system", content=_SYSTEM_PROMPT),
                        ChatMessage(
                            role="user",
                            content=f"QUESTION: {question}\n\nEVIDENCE:\n{evidence_text}",
                        ),
                    ],
                    temperature=0.0,
                    max_tokens=400,
                    metadata={"surface": "agent_advisory"},
                )
            )
            content = (response.content or "").strip()
            if not content:
                return None
            return content, Attribution(
                mode="model",
                provider=response.provider,
                model=response.model,
                note="synthesised from the evidence listed",
            )
        except Exception:
            # Provider down, quota, timeout, refusal, malformed response: all the same to
            # the operator, who gets the deterministic answer and an honest attribution.
            return None


# --------------------------------------------------------------------------------------
# Addressing
# --------------------------------------------------------------------------------------


def known_agent_ids(builder: Any) -> list[str]:
    """Every agent with a registered identity. The only names `advise` will accept."""
    from core.agents import registered_agents

    return sorted(registered_agents(builder.store))
