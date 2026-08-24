"""Authority Gateway: the ONLY path to mutate high-authority state.

Every request flows through: schema → identity → authorization → policy →
state transition check → ALLOW / DENY / REQUIRE_APPROVAL.

A language model may explain "this trade should be allowed" — but that has
zero authority unless the gateway produces ALLOW.
"""

from typing import Any

from pydantic import BaseModel, Field

from kernel.capability import CapabilityRouter
from kernel.identity import IdentityRegistry, Role
from kernel.receipts import Decision, DecisionReceipt, ReceiptStore
from kernel.state_machine import StateMachineEngine


class AuthorityRequest(BaseModel):
    """A request to perform a capability-governed action."""

    actor_id: str
    capability: str
    object_type: str
    object_id: str
    action: str
    reason: str
    params: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class AuthorityResult(BaseModel):
    """The result of an authority check."""

    decision: Decision
    receipt: DecisionReceipt
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class PolicyCheck(BaseModel):
    """A named policy check with its result."""

    name: str
    passed: bool
    detail: str = ""


PolicyFn = Any  # Callable[[AuthorityRequest, Any], PolicyCheck]


class AuthorityGateway:
    """The ONLY path to mutate high-authority state.

    Every request flows through the full chain. No shortcuts. No bypasses.
    If any check fails, the result is DENY (fail closed).
    """

    def __init__(
        self,
        identity: IdentityRegistry,
        capabilities: CapabilityRouter,
        receipts: ReceiptStore,
        state_machine: StateMachineEngine,
    ) -> None:
        self._identity = identity
        self._capabilities = capabilities
        self._receipts = receipts
        self._state_machine = state_machine
        self._policies: list[PolicyFn] = []
        self._role_capability_map: dict[Role, set[str]] = {}

    def register_policy(self, check: PolicyFn) -> None:
        """Register a named policy check that runs on every request."""
        self._policies.append(check)

    def grant_role_capability(self, role: Role, capability: str) -> None:
        """Grant a role access to a capability."""
        self._role_capability_map.setdefault(role, set()).add(capability)

    async def authorize(self, request: AuthorityRequest) -> AuthorityResult:
        """The ONLY path to state mutation. Runs the full chain."""
        # 1. Resolve identity
        try:
            actor = self._identity.resolve(request.actor_id)
        except (KeyError, PermissionError) as exc:
            return self._deny(request, str(exc))

        # 2. Check capability is declared (implementation may or may not be registered)
        if not self._capabilities.is_declared(request.capability):
            return self._deny(request, f"capability not declared: {request.capability!r}")

        # 3. Check actor has role that grants this capability
        granted = False
        for role in actor.roles:
            caps = self._role_capability_map.get(role, set())
            if request.capability in caps or "*:all" in caps:
                granted = True
                break
        if not granted:
            return self._deny(
                request,
                f"actor {request.actor_id!r} roles {sorted(r.value for r in actor.roles)} "
                f"do not grant capability {request.capability!r}",
            )

        # 4. Run registered policy checks (fail closed)
        for policy in self._policies:
            try:
                check = policy(request, self)
                if isinstance(check, PolicyCheck) and not check.passed:
                    return self._deny(request, f"policy {check.name} failed: {check.detail}")
            except Exception as exc:  # noqa: BLE001 - fail closed
                return self._deny(request, f"policy check raised: {exc}")

        # 5. State transition check (if applicable)
        if request.action.startswith("transition:"):
            target_state = request.action.split(":", 1)[1]
            try:
                transition = self._state_machine.transition(
                    object_type=request.object_type,
                    object_id=request.object_id,
                    requested_state=target_state,
                    actor_id=request.actor_id,
                    reason=request.reason,
                    evidence_refs=request.evidence_refs,
                )
                return self._allow(
                    request,
                    f"transitioned {request.object_type}:{request.object_id} "
                    f"{transition.from_state} -> {transition.to_state}",
                    data={"from_state": transition.from_state, "to_state": transition.to_state},
                )
            except Exception as exc:  # noqa: BLE001 - fail closed
                return self._deny(request, f"state transition failed: {exc}")

        # 6. Default: ALLOW (capability + role + policies all passed)
        return self._allow(request, "authorized")

    def _allow(
        self, request: AuthorityRequest, reason: str, data: dict[str, Any] | None = None
    ) -> AuthorityResult:
        receipt = self._make_receipt(request, Decision.ALLOW, reason)
        self._receipts.save(receipt)
        return AuthorityResult(
            decision=Decision.ALLOW, receipt=receipt, detail=reason, data=data or {}
        )

    def _deny(self, request: AuthorityRequest, reason: str) -> AuthorityResult:
        receipt = self._make_receipt(request, Decision.DENY, reason)
        self._receipts.save(receipt)
        return AuthorityResult(decision=Decision.DENY, receipt=receipt, detail=reason)

    def _make_receipt(
        self, request: AuthorityRequest, decision: Decision, reason: str
    ) -> DecisionReceipt:
        try:
            actor = self._identity.resolve(request.actor_id)
            actor_type = actor.actor_type.value
        except (KeyError, PermissionError):
            actor_type = "UNKNOWN"
        input_data = request.model_dump(mode="json")
        input_hash = (
            __import__("hashlib")
            .sha256(__import__("json").dumps(input_data, sort_keys=True).encode())
            .hexdigest()
        )
        return DecisionReceipt(
            actor_id=request.actor_id,
            actor_type=actor_type,
            object_type=request.object_type,
            object_id=request.object_id,
            requested_action=request.action,
            capability=request.capability,
            input_hash=input_hash,
            decision=decision,
            reason=reason,
            related_evidence=request.evidence_refs,
        )
