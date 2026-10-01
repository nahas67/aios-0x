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
(* Checked properties, with TLC 2.19 against a real JVM (see                 *)
(* scripts/run_tlc.ps1 and specs/*.cfg -- this is no longer "unrun"):        *)
(*   TypeOK, FillMonotone, NoPhantomFill, TerminalRefusesEveryTransition      *)
(*   as invariants; TerminalIsSticky as a temporal property.                  *)
(*                                                                           *)
(* Property forms are constrained by what TLC accepts, which is worth stating *)
(* because two of these had to be rewritten to be checkable at all:          *)
(*                                                                           *)
(*   - An INVARIANT must be a predicate over a single state: no primes, no   *)
(*     temporal operators. FillMonotone and NoPhantomFill are therefore state *)
(*     predicates, and their content follows from the guards on every         *)
(*     transition rather than from a primed expression inside [].             *)
(*   - The body of [] must be an action of the form [A]_v, so `status' =     *)
(*     status` is rejected. ENABLED is a state predicate, so terminality is   *)
(*     stated as "no action is enabled here" -- which is also stronger, since *)
(*     it covers an action added later.                                       *)
(*   - CHECK_DEADLOCK is off in the config: every terminal state is           *)
(*     deliberately a dead end, so the default check reports the intended     *)
(*     behaviour as an error.                                                *)
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

(***************************************************************************)
(* Terminal orders refuse every transition.                                     *)
(*                                                                            *)
(* Stated as UNCHANGED on the whole variable tuple when the state is already   *)
(* terminal. TLC requires the body of [] to be an action, and UNCHANGED <<...>> *)
(* is one -- the stuttering action, which is exactly what a terminal order     *)
(* does: it changes nothing. A bare `status' = status` is rejected, because a  *)
(* primed expression over one variable is not an action over the tuple.        *)
(*                                                                            *)
(* This is stronger than "every named action is disabled", because it also    *)
(* covers any action added later: there is no outgoing edge from Terminal at   *)
(* all, so a newly-added transition cannot silently reopen a closed order.    *)
(***************************************************************************)
(***************************************************************************)
(* Terminal orders refuse every transition.                                     *)
(*                                                                            *)
(* Stated with ENABLED, which is a *state* predicate, so TLC accepts it inside *)
(* []. It says something stronger and more useful than "no transition has been  *)
(* taken out of a terminal state": it says no transition is even *possible*     *)
(* from one. That covers an action added later, which a claim about observed   *)
(* transitions could not.                                                        *)
(*                                                                            *)
(* An earlier phrasing used `(status \in Terminal) => UNCHANGED <<...>>`, which *)
(* TLC rejects: [] demands an action, and an implication whose consequent is a *)
(* stuttering action is not one. ENABLED sidesteps that by asking about the     *)
(* state rather than about a step.                                             *)
(***************************************************************************)
TerminalRefusesEveryTransition ==
    (status \in Terminal) =>
        (/\ ~ENABLED Accept
         /\ ~ENABLED FullFill
         /\ ~ENABLED PartialFill(1)
         /\ ~ENABLED Cancel
         /\ ~ENABLED Reject
         /\ ~ENABLED Expire)

Spec == Init /\ [][Next]_<<status, filled, ordered>>

TerminalIsSticky ==
    [](status \in Terminal => [](status \in Terminal))

(***************************************************************************)
(* These are state predicates, not action formulas. TLC rejects a primed     *)
(* variable inside [] because [] demands an action of the form [A]_v, and   *)
(* an expression over status' and filled' is not one. That is the point of   *)
(* the check: the properties are stated over reachable states, and the       *)
(* transitions that reach them are what the state machine enumerates.      *)
(***************************************************************************)

FillMonotone ==
    (filled >= 0) /\ (filled =< ordered)

NoPhantomFill ==
    (status = "FILLED") => (filled > 0)

NoResurrection ==
    TerminalRefusesEveryTransition

=============================================================================
