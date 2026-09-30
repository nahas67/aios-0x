"""Dialect-portable invariant verification (§61).

The SQLite and PostgreSQL tiers must prove *the same* things about financial
state, so the checks live here once and each store supplies only a row reader.
Every statement is deliberately parameter-free and portable: ``TRUE``/``FALSE``
literals are understood by PostgreSQL and by SQLite >= 3.23, and the only
per-account arithmetic (reservations versus settled cash) is done in Python
through the store's own helpers rather than in dialect-specific SQL.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from core.migrations import latest_version
from schemas.contracts import OrderStatus

if TYPE_CHECKING:  # pragma: no cover - typing only (runtime import is circular)
    from core.financial_kernel import InvariantReport

logger = logging.getLogger(__name__)


class InvariantVerificationMixin:
    """Mixin providing :meth:`verify_invariants` over a portable row reader.

    Implementors provide :meth:`_invariant_rows` (returns dicts keyed by column
    name), plus the standard store readers used for reconstruction proofs.
    """

    def _invariant_rows(self, sql: str) -> list[dict[str, Any]]:
        """Run a parameter-free read query and return rows keyed by column."""
        raise NotImplementedError

    #: Implemented by the concrete store.
    _cash_balance_minor: Any
    _reserved_cash_minor: Any
    positions: Any
    rebuild_positions: Any
    schema_version: Any

    def verify_invariants(self) -> InvariantReport:
        """Deterministic proof that the financial invariants hold (§61)."""
        # Imported lazily: core.financial_kernel imports this mixin, so a
        # module-level import here would be circular.
        from core.financial_kernel import (
            InvariantCheck,
            InvariantReport,
            _payload_hash,
            is_transition_allowed,
        )

        checks: list[InvariantCheck] = []

        unbalanced = self._invariant_rows(
            "SELECT transaction_id, SUM(amount_minor) AS total FROM cash_postings"
            " GROUP BY transaction_id HAVING SUM(amount_minor) <> 0"
        )
        checks.append(
            InvariantCheck(
                name="cash_postings_balance",
                ok=not unbalanced,
                detail=""
                if not unbalanced
                else f"unbalanced transactions: {[r['transaction_id'] for r in unbalanced]}",
            )
        )

        fill_mismatch = self._invariant_rows(
            "SELECT o.internal_order_id AS order_id, o.filled_quantity AS filled,"
            " COALESCE(SUM(f.quantity), 0) AS summed FROM orders o"
            " LEFT JOIN fills f ON f.order_id = o.internal_order_id"
            " GROUP BY o.internal_order_id, o.filled_quantity"
            " HAVING ABS(o.filled_quantity - COALESCE(SUM(f.quantity), 0)) > 1e-9"
        )
        checks.append(
            InvariantCheck(
                name="fills_match_order_state",
                ok=not fill_mismatch,
                detail=""
                if not fill_mismatch
                else "orders whose fills disagree with state: "
                f"{[r['order_id'] for r in fill_mismatch]}",
            )
        )

        overfill = self._invariant_rows(
            "SELECT internal_order_id FROM orders WHERE filled_quantity > quantity + 1e-9"
        )
        checks.append(
            InvariantCheck(
                name="no_overfilled_orders",
                ok=not overfill,
                detail="" if not overfill else f"{len(overfill)} overfilled order(s)",
            )
        )

        illegal = [
            f"{r['order_id']}: {r['from_status']}->{r['to_status']}"
            for r in self._invariant_rows(
                "SELECT order_id, from_status, to_status FROM order_transitions"
                " WHERE from_status IS NOT NULL"
            )
            if not is_transition_allowed(
                OrderStatus(str(r["from_status"])), OrderStatus(str(r["to_status"]))
            )
        ]
        checks.append(
            InvariantCheck(
                name="order_transitions_legal",
                ok=not illegal,
                detail="" if not illegal else f"illegal hops: {illegal}",
            )
        )

        version_gap = self._invariant_rows(
            "SELECT o.internal_order_id AS order_id, COUNT(t.transition_id) AS hops"
            " FROM orders o LEFT JOIN order_transitions t"
            " ON t.order_id = o.internal_order_id GROUP BY o.internal_order_id, o.version"
            " HAVING o.version <> COUNT(t.transition_id)"
        )
        checks.append(
            InvariantCheck(
                name="order_version_matches_history",
                ok=not version_gap,
                detail=""
                if not version_gap
                else f"version/history mismatches: {[r['order_id'] for r in version_gap]}",
            )
        )

        tampered = [
            str(r["event_id"])
            for r in self._invariant_rows(
                "SELECT event_id, payload_json, payload_hash FROM event_outbox"
            )
            if _payload_hash(json.loads(str(r["payload_json"]))) != str(r["payload_hash"])
        ]
        checks.append(
            InvariantCheck(
                name="outbox_payload_hashes",
                ok=not tampered,
                detail="" if not tampered else f"tampered events: {tampered}",
            )
        )

        over_reserved: list[str] = []
        for row in self._invariant_rows(
            "SELECT DISTINCT account_id, currency FROM cash_reservations"
        ):
            account_id = str(row["account_id"])
            currency = str(row["currency"])
            settled = self._cash_balance_minor(account_id, currency)
            reserved = self._reserved_cash_minor(account_id, currency)
            if reserved > max(settled, 0):
                over_reserved.append(
                    f"{account_id}/{currency}: reserved {reserved} > settled {settled}"
                )
        checks.append(
            InvariantCheck(
                name="reservations_within_settled_cash",
                ok=not over_reserved,
                detail="" if not over_reserved else f"over-reserved: {over_reserved}",
            )
        )

        unpublished = self._invariant_rows(
            "SELECT COUNT(*) AS n FROM event_outbox"
            " WHERE status = 'PUBLISHED' AND published_at IS NULL"
        )
        unpublished_n = int(unpublished[0]["n"]) if unpublished else 0
        checks.append(
            InvariantCheck(
                name="published_events_have_timestamp",
                ok=unpublished_n == 0,
                detail=f"{unpublished_n} published event(s) without a timestamp"
                if unpublished_n
                else "",
            )
        )

        cleared = self._invariant_rows(
            "SELECT COUNT(*) AS n FROM reconciliation_findings f"
            " JOIN reconciliation_runs r ON r.run_id = f.run_id"
            " WHERE f.severity = 'CRITICAL'"
            " AND (r.ok = TRUE OR (f.status = 'RESOLVED' AND COALESCE(f.resolved_by, '') = ''))"
        )
        cleared_n = int(cleared[0]["n"]) if cleared else 0
        checks.append(
            InvariantCheck(
                name="critical_findings_not_silently_cleared",
                ok=cleared_n == 0,
                detail=f"{cleared_n} critical finding(s) cleared without a named human resolution"
                if cleared_n
                else "",
            )
        )

        released = self._invariant_rows(
            "SELECT COUNT(*) AS n FROM safety_lockouts"
            " WHERE active = FALSE AND COALESCE(released_by, '') = ''"
        )
        released_n = int(released[0]["n"]) if released else 0
        checks.append(
            InvariantCheck(
                name="lockouts_released_by_named_human",
                ok=released_n == 0,
                detail=f"{released_n} anonymous lockout release(s)" if released_n else "",
            )
        )

        current_version = int(self.schema_version())
        checks.append(
            InvariantCheck(
                name="schema_up_to_date",
                ok=current_version >= latest_version(),
                detail=""
                if current_version >= latest_version()
                else f"schema at {current_version}, code requires {latest_version()}",
            )
        )

        stored = {f"{p.account_id}|{p.symbol}": p for p in self.positions()}
        rebuilt = {f"{p.account_id}|{p.symbol}": p for p in self.rebuild_positions()}
        divergence = [
            key
            for key in set(stored) | set(rebuilt)
            if key not in stored
            or key not in rebuilt
            or abs(stored[key].quantity - rebuilt[key].quantity) > 1e-9
            or abs(stored[key].realized_pnl - rebuilt[key].realized_pnl) > 1e-6
        ]
        checks.append(
            InvariantCheck(
                name="positions_reconstructible",
                ok=not divergence,
                detail="" if not divergence else f"divergent positions: {divergence}",
            )
        )
        return InvariantReport(checks=checks)
