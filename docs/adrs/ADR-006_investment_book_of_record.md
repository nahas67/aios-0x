# ADR-006: Investment Book of Record — Single Source of Portfolio Truth

## Context

AIOS-0X had several partial answers to "what do we own?":

- `PaperEngine` owns simulated cash and open positions (venue simulation).
- `communities/c11_finance/ledger.py` owns double-entry accounting legs.
- `LotBook` owns FIFO tax lots.
- `api/views.py` derives executive numbers from whichever component it reads.

None of them is *the* book of record. Master-spec §27 requires one authoritative
answer for holdings, cash, reservations, live orders, exposure and P&L, and §26
requires that this internal truth be compared against broker truth on a schedule.
Letting each layer keep its own version of portfolio truth is how double-counted
fills and phantom positions survive.

## Decision

1. **`core/ibor.py` is the canonical Investment Book of Record** for durable
   account state. It reads from the deterministic financial store and answers the
   §27 questions in one typed payload (`BookSnapshot`): positions with marks,
   settled vs reserved vs available cash, open orders, gross/net exposure, NAV,
   realized/unrealized P&L, and the number of fills applied.

2. **Ingest is the only write path.** `InvestmentBookOfRecord.ingest_fill(...)`
   delegates to the exactly-once store. The IBOR never keeps a private copy of
   positions it could disagree with; it is a projection over orders/fills/cash,
   and `rebuild()` proves that the projection equals the live rows.

3. **Honest valuation.** With a missing mark, market value/NAV/exposure are
   reported as `None` and `marks_complete=False`; the book never invents a price
   (spec §75). Unmarked symbols are returned with quantity and cost only.

4. **Buying power is explicit.** `reserve_cash()` / `release_cash()` make "what
   cash is reserved?" a first-class question; a reservation beyond
   settled-minus-reserved is refused (`InsufficientCash`).

5. **Reconciliation is a first-class workflow (`§26`), not a log line.**
   `communities/c5_execution/reconciliation.py` compares a typed `BrokerSnapshot`
   (orders, executions, positions, cash) against internal state and classifies
   every divergence into the §26 taxonomy (`UNKNOWN_BROKER_ORDER`,
   `MISSING_ORDER`, `QUANTITY_MISMATCH`, `STALE_STATUS`, `DUPLICATE_FILL`,
   `MISSING_FILL`, `POSITION_MISMATCH`, `CASH_MISMATCH`). Each run and finding is
   persisted; findings move OPEN → RESOLVED only through a human identity; the
   result exposes `requires_lockout` so the safety plane can react mechanically.

6. **Ownership boundary.** The IBOR and the reconciliation engine are AIOS-owned
   authoritative components (spec §58). No agent, and no LLM, may write to them
   directly: agents propose, the kernel/authority path mutates, the book records.

## Status

- State: ACCEPTED
- Date: 2026-09-15
- Authors: AIOS System Architecture Team

## Consequences

### Positive Consequences

- One answer per §27 question, with a machine-checkable proof
  (`InvestmentBookOfRecord.rebuild()` and `verify_invariants()`).
- Broker divergence becomes an actionable, auditable queue instead of a warning;
  critical divergences name both sides of the mismatch.
- The runner's existing per-bar `ReconciliationReport` (positions-only) remains as
  a cheap liveness check, while the durable engine provides the full workflow.

### Negative Consequences / Trade-offs

- Two reconciliation mechanisms exist until the runner's per-bar check is retired;
  the durable engine is the superset and the legacy check is positions-only.
  Retiring it is deliberate follow-up work, not an oversight.
- NAV depends on marks supplied by the caller (`mark_provider`), so a stale mark
  is a caller concern; the book's guarantee is that it never substitutes a guess.

## Compliance & Verification

- `tests/test_v1a_financial_kernel.py::test_book_snapshot_is_honest_about_missing_marks`
  — NAV/market value are `None` without marks, computed with them.
- `…::test_book_survives_restart_and_rebuilds_from_fills` — the book survives a
  simulated process death and rebuilds from the ledger.
- `…::test_reconciliation_flags_unknown_order_and_cash_mismatch`,
  `…::test_reconciliation_flags_duplicate_execution`,
  `…::test_clean_reconciliation_and_human_resolution` — taxonomy, persistence,
  lockout signal and human-only resolution.
- `simulation/replay_runner.py` reports `ibor_rebuild_ok` and
  `financial_invariants_ok` on every `RunSummary`, and logs an error (never a
  silent pass) when either is false.
