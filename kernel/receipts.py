"""Decision Receipt Engine: every consequential decision generates a receipt.

The receipt is the bridge between WHAT AIOS did and WHY AIOS did it.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class DecisionReceipt(BaseModel):
    """Immutable record of a decision made by the authority gateway."""

    receipt_id: str = Field(
        default_factory=lambda: hashlib.sha256(_receipt_entropy()).hexdigest()[:16]
    )
    actor_id: str
    actor_type: str
    object_type: str
    object_id: str
    requested_action: str
    capability: str
    policy_version: str = "v1"
    input_hash: str
    decision: Decision
    reason: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    related_evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def input_hash_of(self, data: Any) -> str:
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


def _receipt_entropy() -> bytes:
    import time

    return f"{time.time_ns()}".encode()


class ReceiptStore:
    """Receipt store with optional durable sink.

    When ``sink`` is provided, EVERY saved receipt (gateway ALLOW/DENY and
    state-machine co-receipts alike) is mirrored through it — typically into
    the hash-chained audit log. One persistence path, no double logging.
    """

    def __init__(
        self,
        sink: Callable[[str, str | None, dict[str, Any]], None] | None = None,
    ) -> None:
        self._receipts: list[DecisionReceipt] = []
        self._by_object: dict[str, list[DecisionReceipt]] = {}
        self._sink = sink

    def save(self, receipt: DecisionReceipt) -> None:
        self._receipts.append(receipt)
        key = f"{receipt.object_type}:{receipt.object_id}"
        self._by_object.setdefault(key, []).append(receipt)
        if self._sink is not None:
            self._sink("DECISION_RECEIPT", receipt.receipt_id, receipt.model_dump(mode="json"))

    def by_object(self, object_type: str, object_id: str) -> list[DecisionReceipt]:
        return self._by_object.get(f"{object_type}:{object_id}", [])

    def by_actor(self, actor_id: str) -> list[DecisionReceipt]:
        return [r for r in self._receipts if r.actor_id == actor_id]

    def recent(self, limit: int = 50) -> list[DecisionReceipt]:
        return self._receipts[-limit:]

    def count(self) -> int:
        return len(self._receipts)
