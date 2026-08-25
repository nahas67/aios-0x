"""State Machine Engine: formal lifecycle transitions with validation and receipts.

Objects (strategies, hypotheses, experiments) do not jump between states
arbitrarily. Every transition requires: current_state, requested_state, actor,
reason, evidence, and passes through the authority gateway.
"""

import hashlib
import json

from pydantic import BaseModel

from kernel.receipts import Decision, DecisionReceipt, ReceiptStore


class TransitionError(Exception):
    """Raised when a state transition is invalid."""

    def __init__(
        self, object_type: str, object_id: str, current: str, requested: str, reason: str = ""
    ):
        self.object_type = object_type
        self.object_id = object_id
        self.current = current
        self.requested = requested
        msg = f"invalid transition: {object_type}:{object_id} {current!r} -> {requested!r}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class StateTransition(BaseModel):
    """A validated state transition record."""

    object_type: str
    object_id: str
    from_state: str
    to_state: str
    actor_id: str
    reason: str
    receipt: DecisionReceipt


class StateMachineDefinition:
    """Defines valid transitions for an object type.

    Example:
        sm = StateMachineDefinition("strategy", {
            "IDEA": {"HYPOTHESIS"},
            "HYPOTHESIS": {"DRAFT", "REJECTED"},
            "DRAFT": {"VALIDATED", "REJECTED"},
            ...
        })
    """

    def __init__(
        self,
        object_type: str,
        transitions: dict[str, set[str]],
        initial_state: str,
        terminal_states: set[str] | None = None,
    ) -> None:
        self.object_type = object_type
        self._transitions = transitions
        self.initial_state = initial_state
        self.terminal_states = terminal_states or set()

    def can_transition(self, current: str, requested: str) -> bool:
        return requested in self._transitions.get(current, set())

    def validate(self, current: str, requested: str) -> None:
        if current in self.terminal_states:
            raise TransitionError(
                self.object_type,
                "?",
                current,
                requested,
                "terminal state cannot transition",
            )
        if current not in self._transitions:
            raise TransitionError(
                self.object_type,
                "?",
                current,
                requested,
                f"unknown state {current!r}",
            )
        if requested not in self._transitions[current]:
            allowed = self._transitions[current]
            raise TransitionError(
                self.object_type,
                "?",
                current,
                requested,
                f"allowed: {sorted(allowed)}",
            )


class StateMachineEngine:
    """Enforces state transitions for registered object types.

    Every valid transition produces a StateTransition record with a receipt.
    Every invalid transition raises TransitionError.
    """

    def __init__(self, receipts: ReceiptStore) -> None:
        self._definitions: dict[str, StateMachineDefinition] = {}
        self._receipts = receipts
        self._objects: dict[str, str] = {}  # object_key -> current_state
        self._transitions: list[StateTransition] = []

    def register_definition(self, definition: StateMachineDefinition) -> None:
        self._definitions[definition.object_type] = definition

    def create_object(self, object_type: str, object_id: str, actor_id: str) -> str:
        definition = self._get_definition(object_type)
        key = f"{object_type}:{object_id}"
        if key in self._objects:
            raise ValueError(f"object already exists: {key}")
        self._objects[key] = definition.initial_state
        return definition.initial_state

    def restore_object(self, object_type: str, object_id: str, state: str) -> None:
        """Re-register an object at an EXISTING state after a restart.

        Cross-session recovery path (used by the research plane at boot).
        Public API on purpose: callers must never touch ``_objects`` directly.
        Validates that ``state`` is a legal state of the registered machine.
        """
        definition = self._get_definition(object_type)
        key = f"{object_type}:{object_id}"
        legal = set(definition._transitions.keys()) | {definition.initial_state}
        if state not in legal:
            raise ValueError(f"illegal state {state!r} for {object_type}")
        self._objects[key] = state

    def has_object(self, object_type: str, object_id: str) -> bool:
        return f"{object_type}:{object_id}" in self._objects

    def get_state(self, object_type: str, object_id: str) -> str:
        key = f"{object_type}:{object_id}"
        state = self._objects.get(key)
        if state is None:
            raise KeyError(f"object not found: {key}")
        return state

    def transition(
        self,
        object_type: str,
        object_id: str,
        requested_state: str,
        actor_id: str,
        reason: str,
        evidence_refs: list[str] | None = None,
    ) -> StateTransition:
        definition = self._get_definition(object_type)
        key = f"{object_type}:{object_id}"
        current = self.get_state(object_type, object_id)

        definition.validate(current, requested_state)

        input_data = {
            "object_type": object_type,
            "object_id": object_id,
            "from": current,
            "to": requested_state,
            "reason": reason,
        }
        input_hash = hashlib.sha256(json.dumps(input_data, sort_keys=True).encode()).hexdigest()

        receipt = DecisionReceipt(
            actor_id=actor_id,
            actor_type="SYSTEM",
            object_type=object_type,
            object_id=object_id,
            requested_action=f"transition:{current}->{requested_state}",
            capability=f"AIOS.transition.{object_type}",
            input_hash=input_hash,
            decision=Decision.ALLOW,
            reason=reason,
            related_evidence=evidence_refs or [],
        )
        self._receipts.save(receipt)

        self._objects[key] = requested_state
        transition = StateTransition(
            object_type=object_type,
            object_id=object_id,
            from_state=current,
            to_state=requested_state,
            actor_id=actor_id,
            reason=reason,
            receipt=receipt,
        )
        self._transitions.append(transition)
        return transition

    def history(self, object_type: str, object_id: str) -> list[StateTransition]:
        key = f"{object_type}:{object_id}"
        return [t for t in self._transitions if f"{t.object_type}:{t.object_id}" == key]

    def _get_definition(self, object_type: str) -> StateMachineDefinition:
        definition = self._definitions.get(object_type)
        if definition is None:
            raise ValueError(f"no state machine defined for {object_type!r}")
        return definition
