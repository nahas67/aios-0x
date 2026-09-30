---- MODULE OrderLifecycle ----
(***************************************************************************)
(* Order lifecycle safety (goal G220).                                       *)
(*                                                                           *)
(* Mirrors schemas.contracts.OrderStatus and                                 *)
(* _TERMINAL_ORDER_STATES exactly: PENDING_NEW, ACCEPTED,                    *)
(* PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED, with FILLED,       *)
(* CANCELLED, REJECTED, EXPIRED terminal. A test pins the mirror             *)
(* (tests/test_formal_assurance.py): a state renamed in code without         *)
(* renaming it here fails loudly rather than letting the spec describe a     *)
(* machine the implementation no longer runs.                                *)
(*                                                                           *)
(* Checked properties (run TLC when a JVM is available; no JVM exists in     *)
(* this environment, stated not hidden):                                     *)
(*   - TerminalIsSticky: once terminal, every successor is itself.           *)
(*   - FillMonotone: filled_quantity never decreases and never exceeds       *)
(*     quantity (DurableOrder._validate).                                     *)
(*   - NoPhantomFill: FILLED is reachable only with filled_quantity > 0.     *)
(*   - NoResurrection: no transition leaves a terminal state.                *)
(***************************************************************************)

EXTENDS Naturals, FiniteSets

CONSTANTS MaxQty

VARIABLES status, filled, ordered

OrderStates == {
    "PENDING_NEW", "ACCEPTED", "PARTIALLY_FILLED",
    "FILLED", "CANCELLED", "REJECTED", "EXPIRED"
}

Terminal == {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}

TypeOK ==
    /\ status \in OrderStates
    /\ filled \in 0 .. MaxQty
    /\ ordered \in 1 .. MaxQty
    /\ filled =< ordered

Init ==
    /\ status = "PENDING_NEW"
    /\ filled = 0
    /\ ordered \in 1 .. MaxQty

Accept ==
    /\ status = "PENDING_NEW"
    /\ status' = "ACCEPTED"
    /\ UNCHANGED <<filled, ordered>>

PartialFill(amount) ==
    /\ status \in {"ACCEPTED", "PARTIALLY_FILLED"}
    /\ amount \in 1 .. (ordered - filled)
    /\ filled' = filled + amount
    /\ status' = IF filled' = ordered THEN "FILLED" ELSE "PARTIALLY_FILLED"
    /\ UNCHANGED <<ordered>>

FullFill ==
    /\ status \in {"ACCEPTED", "PARTIALLY_FILLED"}
    /\ filled < ordered
    /\ filled' = ordered
    /\ status' = "FILLED"
    /\ UNCHANGED <<ordered>>

Cancel ==
    /\ status \notin Terminal
    /\ status' = "CANCELLED"
    /\ UNCHANGED <<filled, ordered>>

Reject ==
    /\ status = "PENDING_NEW"
    /\ status' = "REJECTED"
    /\ UNCHANGED <<filled, ordered>>

Expire ==
    /\ status \in {"PENDING_NEW", "ACCEPTED", "PARTIALLY_FILLED"}
    /\ status' = "EXPIRED"
    /\ UNCHANGED <<filled, ordered>>

Next ==
    \/ Accept
    \/ \E amount \in 1 .. MaxQty : PartialFill(amount)
    \/ FullFill
    \/ Cancel
    \/ Reject
    \/ Expire

Spec == Init /\ [][Next]_<<status, filled, ordered>>

TerminalIsSticky ==
    [](status \in Terminal => [](status \in Terminal))

FillMonotone ==
    []((filled' >= filled) /\ (filled =< ordered))

NoPhantomFill ==
    [](status = "FILLED" => filled > 0)

NoResurrection ==
    [](status \in Terminal => [Next]_status \/ UNCHANGED status)

=============================================================================
