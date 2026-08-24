"""Promotion + Rollback Controllers: controlled artifact lifecycle.

No agent can self-promote by changing metadata. Promotion requires evaluation
evidence and passes through the authority gateway. Every promotion records a
rollback target.
"""

from datetime import UTC
from enum import StrEnum

from pydantic import BaseModel, Field

from kernel.receipts import Decision, DecisionReceipt, ReceiptStore


class PromotionState(StrEnum):
    CANDIDATE = "CANDIDATE"
    EVALUATED = "EVALUATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class PromotionRecord(BaseModel):
    promotion_id: str
    artifact_type: str
    artifact_id: str
    artifact_version: str
    state: PromotionState = PromotionState.CANDIDATE
    evaluation_ref: str = ""
    promoted_by: str = ""
    rollback_target: str = ""
    created_at: str = Field(default_factory=lambda: _now())
    decided_at: str = ""


class RollbackTarget(BaseModel):
    artifact_type: str
    artifact_id: str
    current_version: str
    rollback_version: str
    rolled_back_by: str = ""
    rolled_back_at: str = ""


def _now() -> str:
    return datetime_now()


def datetime_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


class PromotionController:
    """Controls artifact promotion. Requires EVALUATED state + human action."""

    def __init__(self, receipts: ReceiptStore) -> None:
        self._receipts = receipts
        self._records: dict[str, PromotionRecord] = {}

    def propose(
        self,
        artifact_type: str,
        artifact_id: str,
        artifact_version: str,
        evaluation_ref: str = "",
    ) -> PromotionRecord:
        key = f"{artifact_type}:{artifact_id}:{artifact_version}"
        record = PromotionRecord(
            promotion_id=key,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            evaluation_ref=evaluation_ref,
        )
        self._records[key] = record
        return record

    def promote(
        self,
        artifact_type: str,
        artifact_id: str,
        artifact_version: str,
        operator_id: str,
        rollback_target_version: str = "",
    ) -> PromotionRecord:
        """HUMAN-GATED: only after EVALUATED state."""
        key = f"{artifact_type}:{artifact_id}:{artifact_version}"
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"promotion not found: {key!r}")
        if record.state != PromotionState.EVALUATED:
            raise PermissionError(f"promotion requires EVALUATED state, got {record.state.value}")
        record.state = PromotionState.PROMOTED
        record.promoted_by = operator_id
        record.decided_at = _now()
        record.rollback_target = rollback_target_version
        self._receipts.save(
            DecisionReceipt(
                actor_id=operator_id,
                actor_type="HUMAN",
                object_type=artifact_type,
                object_id=artifact_id,
                requested_action=f"promote:{artifact_version}",
                capability=f"AIOS.promote.{artifact_type}",
                input_hash=key,
                decision=Decision.ALLOW,
                reason=f"promoted by {operator_id}",
            )
        )
        return record

    def reject(
        self, artifact_type: str, artifact_id: str, artifact_version: str, operator_id: str
    ) -> PromotionRecord:
        key = f"{artifact_type}:{artifact_id}:{artifact_version}"
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"promotion not found: {key!r}")
        record.state = PromotionState.REJECTED
        record.decided_at = _now()
        return record

    def mark_evaluated(
        self, artifact_type: str, artifact_id: str, artifact_version: str
    ) -> PromotionRecord:
        key = f"{artifact_type}:{artifact_id}:{artifact_version}"
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"promotion not found: {key!r}")
        record.state = PromotionState.EVALUATED
        return record

    def get(self, artifact_type: str, artifact_id: str, artifact_version: str) -> PromotionRecord:
        key = f"{artifact_type}:{artifact_id}:{artifact_version}"
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"promotion not found: {key!r}")
        return record


class RollbackController:
    """Tracks rollback targets for every promoted artifact."""

    def __init__(self) -> None:
        self._targets: dict[str, RollbackTarget] = {}

    def register_target(
        self,
        artifact_type: str,
        artifact_id: str,
        current_version: str,
        rollback_version: str,
    ) -> RollbackTarget:
        key = f"{artifact_type}:{artifact_id}"
        target = RollbackTarget(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            current_version=current_version,
            rollback_version=rollback_version,
        )
        self._targets[key] = target
        return target

    def get_rollback(self, artifact_type: str, artifact_id: str) -> RollbackTarget:
        key = f"{artifact_type}:{artifact_id}"
        target = self._targets.get(key)
        if target is None:
            raise KeyError(f"no rollback target for {key!r}")
        return target

    def execute_rollback(
        self, artifact_type: str, artifact_id: str, operator_id: str
    ) -> RollbackTarget:
        target = self.get_rollback(artifact_type, artifact_id)
        target.rolled_back_by = operator_id
        target.rolled_back_at = _now()
        return target
