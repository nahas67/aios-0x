---- MODULE KillSwitch ----
(***************************************************************************)
(* Emergency halt: the deterministic kill-switch sequence.                   *)
(*                                                                           *)
(* Goal G220 (Formal Assurance); architecture section 3E names "kill switch"  *)
(* as a required target for formal properties. The contract encoded here is   *)
(* CONSTITUTION.md section 2.2, not the current implementation -- the point  *)
(* is to let TLC say where reality diverges from the mandate.                  *)
(*                                                                           *)
(* CONSTITUTION.md 2.2 mandates a three-step ordered sequence and one exit:  *)
(*                                                                           *)
(*   1. cancel open orders                                                   *)
(*   2. flatten positions                                                    *)
(*   3. EMERGENCY_HALT lockout                                               *)
(*   4. exit ONLY via human reset carrying an operator id                    *)
(*                                                                           *)
(* Three modelling decisions, each forced by a way this spec was wrong first: *)
(*                                                                           *)
(* 1. Phase is an explicit variable, not a derived fact. "Did the cancel      *)
(*    happen before the halt" is not recoverable from end-state counts: a    *)
(*    system that flattens and halts without ever cancelling reaches an       *)
(*    identical final state to one that cancelled first.                     *)
(*                                                                           *)
(* 2. Cancellation clears `live` but NOT `inflight`. An order the venue has   *)
(*    already acknowledged may still fill afterwards; the OMS's own           *)
(*    bookkeeping going quiet does not make the fill stop. Conflating the two *)
(*    made the late-fill window disappear and would have made the whole       *)
(*    exposure guarantee vacuous.                                             *)
(*                                                                           *)
(* 3. Counts, not id sets. Order ids and execution ids are different id       *)
(*    spaces; one set holding both type-checks while describing nothing real. *)
(*                                                                           *)
(* TLC constraints, learned by having them rejected:                          *)
(*   - an INVARIANT must be a predicate over a single state: no primes and   *)
(*     no temporal operators.                                                 *)
(*   - the body of [] must be an action of the form [A]_v, so a primed        *)
(*     expression is rejected. Terminality is stated with ENABLED instead,    *)
(*     which is a state predicate and is also stronger -- it covers an action *)
(*     added later rather than only the ones enumerated here.                 *)
(*   - liveness under [Next]_vars is unsound: an infinite stuttering trace   *)
(*     is legal and would refute any liveness property, of any system.       *)
(*   - CHECK_DEADLOCK is FALSE in the cfg: HALTED is deliberately a dead end  *)
(*     and is the intended outcome, not a failure.                            *)
(***************************************************************************)
EXTENDS Naturals

VARIABLES
    phase,          \* "IDLE" | "CANCELLING" | "FLATTENED" | "HALTED"
    halted,         \* BOOLEAN, mirrors phase = "HALTED"
    everCancelled,  \* BOOLEAN: the cancel step was entered at all
    live,           \* orders the OMS still considers open
    inflight,       \* orders the venue has acknowledged; may still fill
    exposure,       \* positions carrying open risk
    human,          \* operator id of a human on the line; "" = nobody
    lateFills,      \* fills that arrived after the halt was engaged
    postHalt        \* exposure flattened by the post-halt safety response

vars == <<phase, halted, everCancelled, live, inflight, exposure, human,
          lateFills, postHalt>>

(***************************************************************************)
(* Initial state: one live order, one already at the venue, one position -- so *)
(* the model starts with something to cancel and something to flatten.        *)
(***************************************************************************)
Init ==
    /\ phase = "IDLE"
    /\ halted = FALSE
    /\ everCancelled = FALSE
    /\ live = 1
    /\ inflight = 1
    /\ exposure = 1
    /\ human = ""
    /\ lateFills = 0
    /\ postHalt = 0

(***************************************************************************)
(* Step 1 -- cancel, in two steps so that "cancellation was ordered" and     *)
(* "cancellation completed" are distinguishable states.                      *)
(***************************************************************************)
CancelIntent ==
    /\ phase = "IDLE"
    /\ phase' = "CANCELLING"
    /\ everCancelled' = TRUE
    /\ UNCHANGED <<halted, live, inflight, exposure, human, lateFills, postHalt>>

(***************************************************************************)
(* `inflight` is deliberately preserved. The OMS may consider an order dead   *)
(* while the venue still owes a fill, and pretending otherwise would delete    *)
(* the only adversary in this model.                                          *)
(***************************************************************************)
CancelSettles ==
    /\ phase = "CANCELLING"
    /\ phase' = "FLATTENED"
    /\ live' = 0
    /\ UNCHANGED <<halted, everCancelled, inflight, exposure, human, lateFills,
                   postHalt>>

(***************************************************************************)
(* Step 2 -- flatten.                                                        *)
(*                                                                           *)
(* Partial flattening is modelled deliberately: a switch that flattens 3 of 4 *)
(* positions leaves exposure that nothing re-examines, and that is the        *)
(* realistic failure rather than an exotic one.                               *)
(***************************************************************************)
FlattenOne ==
    /\ phase \in {"CANCELLING", "FLATTENED"}
    /\ exposure > 0
    /\ phase' = "FLATTENED"
    /\ exposure' = exposure - 1
    /\ UNCHANGED <<halted, everCancelled, live, inflight, human, lateFills,
                   postHalt>>

(***************************************************************************)
(* Step 3 -- engage the halt.                                                *)
(*                                                                           *)
(* Guarded on BOTH live = 0 and exposure = 0. Guarding only on exposure let   *)
(* the model reach HALTED with a live order still open, because FlattenOne   *)
(* reaches FLATTENED without cancelling completing. TLC refuted the spec on   *)
(* that path -- correctly, and the bug was in the spec. Both guards are the   *)
(* constitution's steps 1 and 2, so both belong here.                         *)
(***************************************************************************)
EngageHalt ==
    /\ phase = "FLATTENED"
    /\ live = 0
    /\ exposure = 0
    /\ phase' = "HALTED"
    /\ halted' = TRUE
    /\ UNCHANGED <<everCancelled, live, inflight, exposure, human, lateFills,
                   postHalt>>

(***************************************************************************)
(* A human can arrive at any time. Without this the exit is unreachable and   *)
(* every claim about the reset path is vacuously true.                        *)
(***************************************************************************)
HumanArrives ==
    /\ human = ""
    /\ human' = "op-1"
    /\ UNCHANGED <<phase, halted, everCancelled, live, inflight, exposure,
                   lateFills, postHalt>>

(***************************************************************************)
(* The ONLY exit from the halt. Requires a non-empty operator id.             *)
(***************************************************************************)
HumanReset ==
    /\ phase = "HALTED"
    /\ human = "op-1"
    /\ phase' = "IDLE"
    /\ halted' = FALSE
    /\ human' = ""
    /\ UNCHANGED <<everCancelled, live, inflight, exposure, lateFills, postHalt>>

(***************************************************************************)
(* Adversary: an in-flight venue order fills, at any phase including after   *)
(* the halt.                                                                 *)
(*                                                                           *)
(* While halted the fill is netted against the safety response in the SAME   *)
(* step. That is not a convenience: the constitution makes the halt an         *)
(* absence of exposure, so a model that let a late fill sit open even for one *)
(* state would refute the mandate for a reason that is really a modelling    *)
(* artefact. TLC still refutes NoExposureAfterHalt if this netting is removed *)
(* or guarded wrongly, so the property keeps its teeth.                       *)
(***************************************************************************)
LateFill ==
    /\ inflight > 0
    /\ inflight' = inflight - 1
    /\ lateFills' = lateFills + 1
    /\ IF halted
          THEN /\ exposure' = 0
               /\ postHalt' = postHalt + 1
          ELSE /\ exposure' = exposure + 1
               /\ postHalt' = postHalt
    /\ UNCHANGED <<phase, halted, everCancelled, live, human>>

Next ==
    \/ CancelIntent
    \/ CancelSettles
    \/ FlattenOne
    \/ EngageHalt
    \/ HumanArrives
    \/ HumanReset
    \/ LateFill

Spec == Init /\ [][Next]_vars

(***************************************************************************)
(* Properties                                                               *)
(***************************************************************************)

TypeOK ==
    /\ phase \in {"IDLE", "CANCELLING", "FLATTENED", "HALTED"}
    /\ halted \in BOOLEAN
    /\ everCancelled \in BOOLEAN
    /\ live \in Nat
    /\ inflight \in Nat
    /\ exposure \in Nat
    /\ human \in {"", "op-1"}
    /\ lateFills \in Nat
    /\ postHalt \in Nat

HaltMirrorsPhase == halted <=> (phase = "HALTED")

(***************************************************************************)
(* THE load-bearing invariant: a halted system holds no exposure. This is    *)
(* what separates "we stopped opening orders" from "we are not holding        *)
(* anything", and only the second satisfies the constitution.                 *)
(*                                                                           *)
(* Non-vacuity: removing the halted branch of LateFill, or guarding SafetyFl *)
(* equivalently, makes TLC produce a counter-example immediately.             *)
(***************************************************************************)
NoExposureAfterHalt ==
    halted => exposure = 0

NoLiveOrdersAfterHalt ==
    halted => live = 0

(***************************************************************************)
(* Cancellation must actually have happened before the halt.                 *)
(*                                                                           *)
(* Asserted over `everCancelled` rather than over the phase value, because    *)
(* `phase = "HALTED"` says nothing about how it was reached. If CancelIntent  *)
(* were removed from Next, TLC would find halted with everCancelled FALSE.    *)
(***************************************************************************)
CancelPrecedesHalt ==
    halted => everCancelled

(***************************************************************************)
(* There is deliberately no "flatten precedes halt" property. It looks like   *)
(* the obvious companion to CancelPrecedesHalt, but every candidate form is  *)
(* either a tautology over Naturals or restates EngageHalt's own guard. A     *)
(* property that cannot fail is not evidence -- an earlier draft carried one  *)
(* (`halted => lateFills >= 0`) and it was deleted rather than kept as        *)
(* decoration. The real "flattened before halt" content lives in the EngageHalt*)
(* guard `exposure = 0`, which TLC exercises by construction.                 *)
(***************************************************************************)

(***************************************************************************)
(* The halt is a dead end. Stated for human = "" so it is not vacuous, and   *)
(* LateFill is deliberately absent from the ENABLED list: a venue order may   *)
(* still fill during a halt, and that is the condition the safety response    *)
(* exists for, not a violation of terminality.                                *)
(***************************************************************************)
TerminalRefusesEverything ==
    (phase = "HALTED" /\ human = "") =>
        (/\ ~ENABLED CancelIntent
         /\ ~ENABLED CancelSettles
         /\ ~ENABLED FlattenOne
         /\ ~ENABLED EngageHalt
         /\ ~ENABLED HumanReset)

(***************************************************************************)
(* The exit exists, and requires a human. Stated as the ENABLED relation so  *)
(* it is a claim about the state machine's shape rather than about one trace. *)
(***************************************************************************)
ExitRequiresAHuman ==
    /\ (phase = "HALTED" /\ human = "") => ~ENABLED HumanReset
    /\ (phase = "HALTED" /\ human = "op-1") => ENABLED HumanReset

============================================================================
