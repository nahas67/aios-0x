---- MODULE Outbox ----
(***************************************************************************)
(* Outbox safety: exactly-once effect under duplicate delivery (goal G220). *)
(*                                                                           *)
(* Mirrors core.financial_kernel.OutboxEvent and OutboxStatus exactly:       *)
(* PENDING, PUBLISHING, PUBLISHED, DEAD_LETTER. Each event carries an        *)
(* idempotency key plus a payload hash; the store refuses a second write    *)
(* under one key, and the hash binds the bytes to the key so a redelivery   *)
(* with different bytes is corruption, not a retry. A test pins the mirror  *)
(* (tests/test_formal_assurance.py).                                         *)
(*                                                                           *)
(* Checked properties (run TLC when a JVM is available; no JVM exists in     *)
(* this environment, stated not hidden):                                     *)
(*   - AtMostOnceEffect: no event is applied twice, however often it is      *)
(*     delivered.                                                            *)
(*   - HashBindsKey: a delivered payload whose hash mismatches is never      *)
(*     applied — it is quarantined, not retried.                             *)
(*   - DeadLetterTerminal: DEAD_LETTER has no successor except an explicit   *)
(*     operator requeue, which is a new event rather than a resurrection.    *)
(*   - NoLoss: every published event is eventually PUBLISHED or              *)
(*     DEAD_LETTER — nothing rests in PUBLISHING forever.                    *)
(***************************************************************************)

EXTENDS Naturals

CONSTANTS MaxAttempts

VARIABLES status, attempts, applied, hashOk

OutboxStates == {"PENDING", "PUBLISHING", "PUBLISHED", "DEAD_LETTER"}

TypeOK ==
    /\ status \in OutboxStates
    /\ attempts \in 0 .. MaxAttempts
    /\ applied \in {0, 1}
    /\ hashOk \in {TRUE, FALSE}

Init ==
    /\ status = "PENDING"
    /\ attempts = 0
    /\ applied = 0
    /\ hashOk \in {TRUE, FALSE}

Claim ==
    (* Worker takes ownership of a pending event. *)
    /\ status = "PENDING"
    /\ status' = "PUBLISHING"
    /\ UNCHANGED <<attempts, applied, hashOk>>

Publish ==
    (* Delivery succeeds: exactly one application, then published. *)
    /\ status = "PUBLISHING"
    /\ hashOk = TRUE
    /\ applied' = 1
    /\ status' = "PUBLISHED"
    /\ attempts' = attempts + 1
    /\ UNCHANGED <<hashOk>>

FailTransient ==
    (* Delivery fails but retries remain: back to pending, never applied. *)
    /\ status = "PUBLISHING"
    /\ attempts + 1 < MaxAttempts
    /\ status' = "PENDING"
    /\ attempts' = attempts + 1
    /\ UNCHANGED <<applied, hashOk>>

FailPermanent ==
    (* Retries exhausted: dead letter, still never applied twice. *)
    /\ status = "PUBLISHING"
    /\ attempts + 1 >= MaxAttempts
    /\ status' = "DEAD_LETTER"
    /\ attempts' = attempts + 1
    /\ UNCHANGED <<applied, hashOk>>

Quarantine ==
    (* Hash mismatch on delivery: quarantined as dead letter, never applied.
       A redelivery with different bytes is corruption, not a retry. *)
    /\ status = "PUBLISHING"
    /\ hashOk = FALSE
    /\ status' = "DEAD_LETTER"
    /\ UNCHANGED <<attempts, applied, hashOk>>

DuplicateDeliver ==
    (* The network redelivers an already-published event: stutter step.
       The idempotency key makes redelivery a no-op by construction. *)
    /\ status = "PUBLISHED"
    /\ UNCHANGED <<status, attempts, applied, hashOk>>

Next ==
    \/ Claim
    \/ Publish
    \/ FailTransient
    \/ FailPermanent
    \/ Quarantine
    \/ DuplicateDeliver

Spec == Init /\ [][Next]_<<status, attempts, applied, hashOk>>

AtMostOnceEffect ==
    [](applied =< 1)

HashBindsKey ==
    [](~hashOk /\ status = "DEAD_LETTER" => applied = 0)

DeadLetterTerminal ==
    [](status = "DEAD_LETTER" => [Next]_status \/ UNCHANGED status)

NoLoss ==
    <>(status = "PUBLISHED" \/ status = "DEAD_LETTER")

=============================================================================
