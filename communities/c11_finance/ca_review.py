"""Community 11: CA/CPA review workflow with a hard filing gate.

Export-for-filing is refused unless the item reached APPROVED_BY_CA through
the state machine - the code enforces Directive 42's authorization rule.
"""

from datetime import UTC, datetime

from schemas.contracts import ReviewItem, ReviewState

_TERMINAL_OK = {ReviewState.APPROVED_BY_CA}


def _now() -> datetime:
    return datetime.now(UTC)


class CAWorkflow:
    def __init__(self) -> None:
        self.items: dict[str, ReviewItem] = {}

    def create(self, subject_kind: str, subject_ref: str) -> ReviewItem:
        item = ReviewItem(subject_kind=subject_kind, subject_ref=subject_ref)
        self.items[item.item_id] = item
        return item

    def _get(self, item_id: str) -> ReviewItem:
        if item_id not in self.items:
            raise KeyError(f"unknown review item {item_id}")
        return self.items[item_id]

    def prepare(self, item_id: str, prepared_by: str) -> ReviewItem:
        item = self._get(item_id)
        assert item.state == ReviewState.DRAFT, f"prepare requires DRAFT, got {item.state}"
        item.state = ReviewState.PREPARED
        item.prepared_by = prepared_by
        item.updated_at = _now()
        return item

    def submit_for_review(self, item_id: str) -> ReviewItem:
        item = self._get(item_id)
        assert item.state == ReviewState.PREPARED, "submit requires PREPARED"
        item.state = ReviewState.UNDER_REVIEW
        item.updated_at = _now()
        return item

    def approve(self, item_id: str, reviewer: str) -> ReviewItem:
        item = self._get(item_id)
        assert item.state == ReviewState.UNDER_REVIEW, "approve requires UNDER_REVIEW"
        if not reviewer.strip():
            raise ValueError("reviewer identity required")
        item.state = ReviewState.APPROVED_BY_CA
        item.reviewed_by = reviewer.strip()
        item.updated_at = _now()
        return item

    def reject(self, item_id: str, reviewer: str, note: str) -> ReviewItem:
        item = self._get(item_id)
        assert item.state == ReviewState.UNDER_REVIEW, "reject requires UNDER_REVIEW"
        item.state = ReviewState.REJECTED
        item.reviewed_by = reviewer
        item.notes.append(note or "rejected without note")
        item.updated_at = _now()
        return item

    def export_for_filing(self, item_id: str) -> dict[str, str]:
        """HARD GATE: only CA-approved items may leave for external filing."""
        item = self._get(item_id)
        if item.state not in _TERMINAL_OK:
            raise PermissionError(
                f"filing blocked: item {item_id} is {item.state.value}, "
                "requires APPROVED_BY_CA (Directive 42)"
            )
        assert item.reviewed_by is not None
        return {
            "subject_kind": item.subject_kind,
            "subject_ref": item.subject_ref,
            "approved_by": item.reviewed_by,
            "exported_at": _now().isoformat(),
        }
