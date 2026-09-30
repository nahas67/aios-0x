# ADR-005: Durable Financial State, Transactional Outbox & Consumer Inbox

## Context

Every prior layer of AIOS-0X treated order state as **process memory**:

- `communities/c5_execution/execution.py` kept `self.orders: dict[str, OrderRequest]`.
- A restart erased the fact that orders were live. "Order accepted" and "trade
  filled" were the same object with a mutated `status` field.
- Financial state changes and the events describing them were written on
  separate paths, so a crash between them could lose an event (or duplicate one).
- Nothing in the system could answer "no fill is economically applied twice" or
  "positions can be reconstructed" with machine-checkable evidence.

Master-spec V1-A requires exactly that: durable OMS state (§23), reconciliation
records (§26), the canonical event envelope with a transactional outbox (§29–§31),
and the §61 invariants. Without a deterministic financial kernel, "autonomous
live" can never be more than a supervised demo.

## Decision

Introduce a **deterministic financial state plane** (`core/financial_kernel.py`)
with four properties enforced by code, not convention:

1. **Transactional outbox (§30).** All financial mutations run inside
   `BaseFinancialStore.transaction()`. State change *and* its outbox envelope
   commit together, or neither does. A publisher (`OutboxPublisher`) drains the
   outbox afterwards; delivery is at-least-once and correctness comes from the
   deterministic `idempotency_key` on every envelope. Failures retry with
   backoff and land in `DEAD_LETTER` after `max_outbox_attempts` — a failed sink
   never loses an event.

2. **Durable consumer inbox (§31).** `consumer_inbox(consumer_name, event_id)`
   is the exactly-once gate: a consumer calls `record_applied(...)` inside its
   own transaction and skips the effect when the row already exists. Transport is
   at-least-once; application effects are exactly-once.

3. **Persistent order state machines (§23).** `DurableOrder` + `order_transitions`
   + optimistic `version`. `ORDER_TRANSITIONS` is the legal map; a hop to the same
   status is allowed only as a recorded audit event (amendment, successive partial
   fill) and can never move money by itself. A stale writer receives
   `StaleOrderVersion`; an illegal hop receives `InvalidOrderTransition`.

4. **Exactly-once fills + reconstructible positions (§61).** A fill is identified
   by `fill_id` (and `broker_execution_id` where the venue supplies one). A
   re-delivered callback is a **no-op**: no state change, no outbox event. Fills
   mutate order state, positions and events in one transaction.
   `rebuild_positions()` recomputes positions from the immutable fill ledger, and
   `verify_invariants()` compares it with live state.

Two venue realities discovered while wiring this into the composition root are
modelled explicitly rather than papered over:

- **Venue-authoritative sizing.** The paper venue sizes from live equity and can
  fill slightly *more* than the plan-derived estimate. The durable order keeps the
  estimate until the venue reports what it did; the change is applied with
  `amend_order_quantity(...)` and recorded as an audit hop
  (`quantity amendment …: venue sizing supersedes plan estimate`). It is never a
  silent mutation.
- **Dust remainders.** A funds-limited venue may deliver 99.95% of a market order.
  A market order is considered complete when the shortfall is within
  `dust_ratio` (default 0.1%), and the reason string records the exact unfilled
  remainder. Without this, the book would report a phantom live order forever.

**Idempotency keys are attempt-scoped.** `OrderManager` scopes the durable key to
the plan (`<client_order_id>#<plan_id>`). An idempotency key identifies ONE order
attempt forever, so a genuine retry after rejection (a new plan) is a new attempt,
while a re-delivered plan is a no-op.

Exits are capital movements too: bracket exits are recorded as closing orders +
fills (`_record_durable_exit`), so the book realises P&L instead of only seeing
entries. The paper venue charges the round trip on the entry fill, so the exit leg
carries no fee of its own — recorded, not guessed.

## Status

- State: ACCEPTED
- Date: 2026-09-15
- Authors: AIOS System Architecture Team

## Consequences

### Positive Consequences

- Crash-safety: an order that was persisted is never forgotten; a state change
  without its event is impossible.
- The §61 invariants are executable (`verify_invariants()`), including
  `cash_postings_balance`, `fills_match_order_state`, `no_overfilled_orders`,
  `order_transitions_legal`, `order_version_matches_history`,
  `outbox_payload_hashes`, `positions_reconstructible`.
- The live order path in `ReplayRunner` now writes durable state before the venue
  call (write-ahead OMS) without changing any bus topic or audit event, so
  determinism and existing audit semantics are untouched.
- Buying power is explicit: settled cash minus live reservations
  (`InsufficientCash` refusal instead of an optimistic guess).

### Negative Consequences / Trade-offs

- Every order now costs a few SQLite writes; the ordering path is no longer free.
  Accepted for V1: correctness outranks nanoseconds (spec §71), and LLMs are not
  in this loop.
- The SQLite tier is the only backend shipped. `BaseFinancialStore` is the adapter
  seam for the PostgreSQL tier; until it exists, the financial plane is
  single-machine. Documented as a V1 residual rather than hidden.
- `OrderStatus.EXPIRED` was added to the shared contract (spec §23 "Expiration");
  `is_terminal()` includes it.

## Compliance & Verification

`tests/test_v1a_financial_kernel.py` (26 tests) encodes the invariants and the
§59 failure modes as executable proofs:

| Invariant / failure mode | Test |
|---|---|
| state change + event commit together (crash rollback) | `test_state_change_and_event_commit_together` |
| mutations require a transaction | `test_mutations_require_a_transaction` |
| outbox claim/retry/dead-letter; no double-claim | `test_outbox_claim_publish_retry_and_dead_letter` |
| publisher retry loses nothing; sink failure ≠ lost event | `test_outbox_publisher_retries_without_losing_events`, `…_outbox_is_durable_for_the_publisher` |
| payload hash tamper detection | `test_outbox_payload_hash_is_verifiable` |
| duplicate delivery applies an effect exactly once | `test_consumer_inbox_applies_effect_exactly_once` |
| legal state machine / stale writer / terminal states | `test_order_lifecycle_and_transitions`, `test_illegal_transition_is_refused`, `test_stale_version_cannot_overwrite_newer_state`, `test_expired_and_cancelled_orders_are_terminal` |
| no fill applied twice (by fill id and by execution id) | `test_duplicate_fill_is_not_applied_twice`, `test_duplicate_fill_detected_by_broker_execution_id` |
| over-fill refused without side effects | `test_overfill_is_refused_without_side_effects` |
| cash zero-sum; reservations gate buying power | `test_unbalanced_cash_postings_are_refused`, `test_reservations_gate_buying_power` |
| restart recovery + reconstruction | `test_book_survives_restart_and_rebuilds_from_fills` |
| corruption detection | `test_invariants_detect_tampered_positions` |
| reordered + duplicated venue callbacks | `test_out_of_order_fill_delivery_keeps_book_correct` |
| composition-root integration (entries + exits, flat book) | `test_replay_runner_persists_durable_financial_state` |
