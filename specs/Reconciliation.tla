---- MODULE Reconciliation ----
(***************************************************************************)
(* Reconciliation safety (architecture section 3E, target "reconciliation"). *)
(*                                                                           *)
(* Fourth assurance target modelled. "fills" and "partial fills" are already  *)
(* covered by OrderLifecycle (PARTIALLY_FILLED, FillMonotone, NoPhantomFill)  *)
(* and "duplicate deliveries" by Outbox (DuplicateDeliver, AtMostOnceEffect), *)
(* so those are deliberately not re-stated: a second spec for a machine       *)
(* already modelled is duplication, and duplication is a refusal under        *)
(* docs/DEPENDENCY_POLICY.md. "failover" is a single bare word in the         *)
(* architecture with no scope, layer, service or acceptance criterion and no  *)
(* implementation anywhere -- modelling it would mean inventing requirements, *)
(* which section 14's freeze rule exists to prevent.                         *)
(*                                                                           *)
(* Reconciliation is genuinely distinct from the other three: it is the only  *)
(* one that compares two independently-maintained records (venue vs internal  *)
(* ledger), so its failures are misjudgements rather than illegal states.      *)
(*                                                                           *)
(* It encodes CONSTITUTION.md section 3 and core/financial_kernel.py rather   *)
(* than the implementation, so TLC can report where the two diverge.          *)
(*                                                                           *)
(* TLC forms, learned the hard way across four specs now:                     *)
(*   - an INVARIANT is a single-state predicate: no primes, no temporal       *)
(*     operators;                                                                  *)
(*     stated with ENABLED (a state predicate). A bare transition predicate  *)
(*     inside [] is rejected the same way, even one over primed variables,    *)
(*     so a claim about what each STEP must do is stated as                   *)
(*     [][Next]_vars => ... -- which is why ResolutionLedgerNeverShrinks is   *)
(*     shaped that way rather than as a single-state predicate.               *)
(*   - the body of [] is an action of the form [A]_v, so terminality is       *)
(*     stated with ENABLED (a state predicate);                                *)
(*   - every variable must be assigned on every path, primed or UNCHANGED.    *)
(*     Writing `resolved = {}` instead of `resolved' = {}` inside an action    *)
(*     gives "Successor state is not completely specified";                    *)
(*   - definitions may appear in any order as long as use follows definition,  *)
(*     though putting Spec last reads better;                                  *)
(*   - \\E x \\in SUBSET S quantifies over subsets and is CORRECT. Replacing    *)
(*     the \\in with \\subseteq cannot bind a variable and turns a type error  *)
(*     into a parse error.                                                     *)
(*                                                                           *)
(* The state is deliberately FLAT: three sets of kind-names and one integer.   *)
(* Earlier drafts carried per-kind maps (``scope'[k]``) and TLC could not       *)
(* evaluate them -- "Attempted to check equality of string "MISSING_ORDER"     *)
(* with non-string {"MISSING_ORDER"}". Two kinds of severity produced the same  *)
(* aggregate consequences, so two sets plus a rank say everything, and a flat   *)
(* state cannot be misapplied. Flatness is not a simplification here; it is     *)
(* the point.                                                                  *)
(***************************************************************************)

EXTENDS Naturals, FiniteSets

CONSTANT MaxFindings

(***************************************************************************)
(* Only the kinds that carry the reconciliation decision. An INFO severity    *)
(* on a CRITICAL-capable kind is exactly the interesting case -- the finding   *)
(* is real and recorded, and it must not stop trading -- so severity is kept.  *)
(* The four mismatch kinds are lumped, because no property here distinguishes   *)
(* them and a spec that pretends to would be asserting more than it checks.    *)
(***************************************************************************)
RestrictingKinds == {
    "MISSING_ORDER", "UNKNOWN_BROKER_ORDER", "ORDER_CONFLICT",
    "BROKER_ONLY_EXECUTION", "INTERNAL_ONLY_EXECUTION", "EXECUTION_CONFLICT",
    "DUPLICATE_EXECUTION", "QUANTITY_MISMATCH", "CASH_MISMATCH",
    "POSITION_MISMATCH", "STALE_STATUS"
}

(***************************************************************************)
(* Deprecated read-compatibility members of AnomalyKind that are NEVER        *)
(* emitted. Named so the spec can state that rule; they are not in the         *)
(* quantified domain above, so the rule holds by construction rather than by   *)
(* assertion -- and a drift test reads them from the enum, so emitting one     *)
(* fails there.                                                                *)
(***************************************************************************)
NeverEmitted == {"DUPLICATE_FILL", "MISSING_FILL"}

Severities == {"INFO", "WARNING", "CRITICAL"}

(***************************************************************************)
(* Mirrors SCOPE_RANK, widest-first. The reach is carried as an INTEGER rank   *)
(* rather than a scope name, because "widest" over a totally ordered bounded   *)
(* range is a maximum, and a maximum is computable without CHOOSE. The scope    *)
(* NAME is recoverable from the rank; the ordering is what carries the meaning. *)
(***************************************************************************)
Ranks == 0 .. 4

ScopeOfRank ==
    [r \in Ranks |->
        CASE r = 0 -> "NONE"
          [] r = 1 -> "STRATEGY"
          [] r = 2 -> "ACCOUNT"
          [] OTHER -> "GLOBAL"]

(***************************************************************************)
(* Every restricting kind in LOCKOUT_SCOPE_BY_KIND reaches ACCOUNT today. The  *)
(* property that matters is not the per-kind table but "only CRITICAL          *)
(* restricts", so the model uses one rank per severity and a drift test pins   *)
(* the real table so a change there breaks the gate rather than passing        *)
(* quietly.                                                                    *)
(***************************************************************************)
RankForSeverity ==
    [s \in Severities |-> IF s = "CRITICAL" THEN 2 ELSE 0]

(***************************************************************************)
(* Mirrors ReconciliationMode. The mode governs which findings are derivable   *)
(* AT ALL, and it is the easiest of these rules to get wrong: inferring "the    *)
(* venue has no execution I lack" from a CURSOR payload that never claimed to  *)
(* list executions is a fabricated negative.                                    *)
(***************************************************************************)
Modes == {"FULL_SNAPSHOT", "BOUNDED_WINDOW", "CURSOR"}

InternalOnlyKinds == {"INTERNAL_ONLY_EXECUTION"}

(***************************************************************************)
(* The reach implied by a set of findings, each with its severity.            *)
(*                                                                           *)
(* Expressed as a case over the severities present rather than as a maximum    *)
(* over per-kind ranks: with two ranks in play (0 and 2) the maximum is just   *)
(* "is there a CRITICAL one", and writing that directly is both total and      *)
(* obviously correct. A CHOOSE over scope names was tried first and TLC could  *)
(* not evaluate it.                                                            *)
(***************************************************************************)
ReachOf(kinds, sevs) ==
    IF \E k \in kinds : sevs[k] = "CRITICAL" THEN 2 ELSE 0

VARIABLES findings, severity, resolved, lockoutRank, mode

TypeOK ==
    /\ findings \subseteq RestrictingKinds
    /\ Cardinality(findings) <= MaxFindings
    /\ severity \in [findings -> Severities]
    /\ resolved \subseteq RestrictingKinds
    /\ lockoutRank \in Ranks
    /\ mode \in Modes

(***************************************************************************)
(* One reconciliation pass.                                                   *)
(*                                                                           *)
(* Severity is chosen independently of kind. Were it derived from the kind, TLC *)
(* could never produce an INFO QUANTITY_MISMATCH and OnlyCriticalRestricts     *)
(* would hold trivially -- checking the encoding rather than the rule.         *)
(*                                                                           *)
(* The mode is consulted rather than assumed: under CURSOR the pass cannot     *)
(* derive an internal-only finding, because a delta proves nothing about the  *)
(* executions it did not mention. Modelling that in the action means TLC        *)
(* explores the reachable states, so CursorCannotDeriveInternalOnly is         *)
(* checked rather than restated.                                               *)
(***************************************************************************)
Discover ==
    /\ findings = {}
    /\ resolved' = {}
    /\ UNCHANGED mode
    /\ \E kinds \in SUBSET RestrictingKinds :
          /\ Cardinality(kinds) > 0
          /\ Cardinality(kinds) <= MaxFindings
          /\ \E sevs \in [kinds -> Severities] :
                /\ findings' = kinds
                /\ severity' = sevs
                /\ lockoutRank' = ReachOf(kinds, sevs)
                /\ (mode = "CURSOR") =>
                       (kinds \cap InternalOnlyKinds = {})

(***************************************************************************)
(* Resolve one finding; the reach is recomputed from what remains.            *)
(*                                                                           *)
(* This is where "only widens" is decided. A pass that reset the reach from    *)
(* scratch each time would drop a GLOBAL restriction the moment one GLOBAL     *)
(* finding cleared while an ACCOUNT one persisted.                             *)
(***************************************************************************)
Resolve ==
    /\ findings # {}
    /\ UNCHANGED <<mode, lockoutRank, severity>>
    /\ \E k \in findings :
          /\ findings' = findings \ {k}
          /\ severity' = [j \in findings \ {k} |-> severity[j]]
          /\ resolved' = resolved \cup {k}
          /\ lockoutRank' = ReachOf(findings \ {k}, severity)

(***************************************************************************)
(* A fresh pass while findings are still open. Reconciliation runs repeatedly, *)
(* so rediscovery is the normal case rather than an edge case.                 *)
(***************************************************************************)
(***************************************************************************)
(* A later pass while some findings are still open.                            *)
(*                                                                          *)
(* MERGES rather than replaces. The next cycle's findings are intersected with  *)
(* the still-open set, so a finding an operator resolved does not come back     *)
(* simply because the venue has not caught up. Replacing wholesale -- which is   *)
(* what this did first -- models a system where a resolved discrepancy silently  *)
(* reappears every cycle, and it made ResolvedAccumulates unfalsifiable because  *)
(* `resolved` was consulted by nothing.                                         *)
(*                                                                          *)
(* The residue is exactly the case worth stating: what the venue still reports  *)
(* that nobody has resolved, which stays open.                                 *)
(***************************************************************************)
Rediscover ==
    /\ findings # {}
    /\ UNCHANGED mode
    /\ \E fresh \in SUBSET RestrictingKinds :
          /\ Cardinality(fresh) > 0
          /\ Cardinality(fresh) <= MaxFindings
          /\ \E sevs \in [fresh -> Severities] :
                LET stillOpen == (findings \ resolved) \cap fresh IN
                /\ findings' = stillOpen
                /\ severity' = [k \in stillOpen |-> sevs[k]]
                /\ UNCHANGED resolved
                /\ lockoutRank' = ReachOf(stillOpen, severity')
                /\ (mode = "CURSOR") => (stillOpen \cap InternalOnlyKinds = {})

(***************************************************************************)
(* Change the mode. Present because a spec that fixed it would let a reader    *)
(* assume internal-only findings are always available.                          *)
(***************************************************************************)
SetMode ==
    /\ mode' \in Modes
    /\ UNCHANGED <<findings, severity, resolved, lockoutRank>>
    \* Switching to CURSOR while an internal-only finding is open would leave a
    \* state no snapshot can justify: a delta proves nothing about executions it
    \* did not mention, so such a finding is not interpretable under CURSOR. The
    \* finding is NOT cleared -- discarding a real discrepancy because a query
    \* mode changed would be exactly the dishonesty this spec exists to catch --
    \* so the transition is refused instead, and the caller can see why.
    /\ (mode' = "CURSOR") => (findings \cap InternalOnlyKinds = {})

Next ==
    \/ Discover
    \/ Resolve
    \/ Rediscover
    \/ SetMode

Init ==
    /\ findings = {}
    /\ severity = [k \in {} |-> "INFO"]
    /\ resolved = {}
    /\ lockoutRank = 0
    /\ mode = "FULL_SNAPSHOT"

Spec == Init /\ [][Next]_<<findings, severity, resolved, lockoutRank, mode>>

(***************************************************************************)
(* Properties. Single-state predicates: no primes, no temporal operators,     *)
(* because TLC rejects those inside INVARIANT.                                *)
(***************************************************************************)

(***************************************************************************)
(* Only a CRITICAL finding may restrict.                                      *)
(*                                                                           *)
(* Recording a finding stays available: an INFO or WARNING finding may exist,  *)
(* and the point is that it cannot stop trading. A system forced into silence  *)
(* by the need to be honest would be a worse system, and this is the property  *)
(* that forbids it.                                                             *)
(***************************************************************************)
(***************************************************************************)
(* The reach is ACCOUNT exactly when a critical finding is open.                *)
(*                                                                          *)
(* Three properties previously made this claim: OnlyCriticalRestricts          *)
(* (`CRITICAL exists <=> lockout > 0`), ReachMatchesFindings (`lockout = 2 <=>  *)
(* exists CRITICAL`) and CriticalFindingsAreAccountScoped (`CRITICAL =>          *)
(* lockout = 2`). All three reduce to the same statement, so no mutation could  *)
(* isolate one -- TLC refuted all three together, or none.                      *)
(*                                                                          *)
(* Collapsed. The biconditional is the whole claim, and it is falsifiable from   *)
(* either direction: too wide (an INFO finding halting the account) and too       *)
(* narrow (a CRITICAL finding failing to halt it).                               *)
(***************************************************************************)
ReachFollowsCriticalFindings ==
    (\E k \in findings : severity[k] = "CRITICAL") <=> (lockoutRank = 2)

(***************************************************************************)
(* The recorded reach is never narrower than a finding's own reach.           *)
(***************************************************************************)
(***************************************************************************)
(* The recorded reach EQUALS what the open findings imply.                 *)
(*                                                                          *)
(* This replaces an earlier property, `\A k: (CRITICAL) \/ (lockoutRank >=        *)
(* RankForSeverity[severity[k]])`, which was a tautology: ReachOf already        *)
(* returns 2 exactly when a critical finding exists, so the disjunction could    *)
(* never be false. A vacuity check found it -- three of nine mutations            *)
(* "passed", which meant those properties could not fail rather than that the     *)
(* machine was correct.                                                        *)
(*                                                                          *)
(* The biconditional is the claim that matters and the old one did not make:     *)
(* the reach is not merely wide enough, it is right. A reach that stayed at 2    *)
(* after every finding was resolved satisfies the old property vacuously and      *)
(* would leave an account halted for nothing.                                     *)
(***************************************************************************)


(***************************************************************************)
(* No restriction without a cause.                                            *)
(*                                                                           *)
(* Catches the failure where lockout is cleared while a critical finding is    *)
(* still open: trading resumed over a known unreconciled discrepancy.          *)
(***************************************************************************)


(***************************************************************************)
(* The deprecated kinds are never produced, and CURSOR never derives an        *)
(* internal-only finding.                                                       *)
(***************************************************************************)
NeverEmittedKindsAbsent ==
    findings \cap {"DUPLICATE_FILL", "MISSING_FILL"} = {}

CursorCannotDeriveInternalOnly ==
    (mode = "CURSOR") => (findings \cap InternalOnlyKinds = {})

(***************************************************************************)
(* A resolved finding is no longer open.                                      *)
(*                                                                           *)
(* Without this, clearing a discrepancy would leave it recorded as outstanding  *)
(* and the next pass would re-derive the same restriction from a finding       *)
(* nobody believes in any more.                                                *)
(***************************************************************************)
(***************************************************************************)
(* A resolution is never undone.                                               *)
(*                                                                          *)
(* Two earlier properties were both unfalsifiable here, and for different      *)
(* reasons worth keeping straight:                                            *)
(*                                                                          *)
(*   resolved \cap findings = {}   held because Rediscover assigns             *)
(*       `stillOpen = (findings \ resolved) \cap fresh`, so disjointness is       *)
(*       structural. That is the machine we want, but a check that cannot fail  *)
(*       is not evidence -- so it is recorded here as a consequence of the       *)
(*       definition rather than listed as an invariant.                        *)
(*                                                                          *)
(*   ResolvedAccumulates == resolved \cap findings = {}   was the same claim    *)
(*       under a name that implied TLC was checking it. It was not: five         *)
(*       mutations could not falsify it.                                        *)
(*                                                                          *)
(* The claim a reader actually wants is that resolution is never UNDONE -- that  *)
(* the ledger of closed findings only grows. That is falsifiable, and it breaks  *)
(* the moment Resolve forgets to record or Rediscover clears, which is exactly    *)
(* the case where a discrepancy an operator signed off would come back.         *)
(*                                                                          *)
(* Stated over the primed set, so it constrains every transition rather than     *)
(* describing one reachable state.                                              *)
(***************************************************************************)
(***************************************************************************)
(* The resolution ledger only grows, and no action can bring a closed          *)
(* finding back into the open set.                                            *)
(*                                                                          *)
(* Three separate properties made this claim -- `resolved \cap findings = {}`,  *)
(* `ResolvedAccumulates`, `NoResolutionIsEverUndone` -- and a mutation check     *)
(* falsified all three. Not because the claim was false but because it was      *)
(* unfalsifiable in the form stated: it was a SINGLE-STATE predicate, and the   *)
(* mutations broke ACTIONS. Every action enforces the disjointness             *)
(* structurally (`Rediscover` subtracts `resolved` when computing `stillOpen`; *)
(* `Resolve` removes the key it adds), so breaking any one of them still left   *)
(* every reachable state satisfying the predicate.                             *)
(*                                                                          *)
(* A state predicate cannot tell "the guarantee holds because the transition    *)
(* enforces it" apart from "the guarantee cannot be violated". Only a claim     *)
(* about the TRANSITION can. So this states what each step must do: a resolved   *)
(* finding stays resolved, and a finding that was resolved does not reappear    *)
(* among the open ones. Every mutation that breaks an action's bookkeeping now   *)
(* breaks this, because it is evaluated on the step rather than on the result.   *)
(***************************************************************************)
(***************************************************************************)
(* No open finding is also a closed one.                                     *)
(*                                                                          *)
(* The stronger form of this claim -- that EVERY STEP preserves the ledger --  *)
(* is what a reader wants, and it is what four attempts to express it in TLA+   *)
(* could not deliver:                                                          *)
(*                                                                          *)
(*   [](pred over primed vars)        "[] followed by action not of form      *)
(*                                    [A]_v"                                  *)
(*   [][Next]_vars => pred            "=> has both temporal formula and       *)
(*                                    action as arguments"                    *)
(*   ENABLED ShrinkResolved            "resolved is either undefined or not   *)
(*                                    an operator"                             *)
(*   A \ B # {}                        "\subset is not a TLA+ operator"        *)
(*                                                                          *)
(* The obstacle is structural. TLC's INVARIANT accepts only single-state      *)
(* predicates; its PROPERTY accepts only an action of the form [A]_v. A claim *)
(* about what each transition must do is a temporal formula over transitions, *)
(* and there is no shape that is both that claim and one TLC will check.      *)
(*                                                                          *)
(* So this states the guarantee at the scope TLC can verify -- over reachable  *)
(* STATES -- and says so. The design intent is that Resolve records a finding   *)
(* once and Rediscover computes `stillOpen = (findings \ resolved) \cap fresh`,  *)
(* so a closed finding is never reintroduced; that is enforced by the          *)
(* definitions and this invariant checks its consequence.                     *)
(*                                                                          *)
(* It is falsifiable, which the earlier versions of this claim were not: a      *)
(* mutation that stops subtracting `resolved` puts a closed kind back into     *)
(* findings, and TLC refutes it.                                               *)
(***************************************************************************)
(***************************************************************************)
(* WHAT IS AND IS NOT INDEPENDENTLY VERIFIED HERE.                            *)
(*                                                                          *)
(* Of the five invariants, three have an isolating mutation and are           *)
(* independently falsifiable:                                                   *)
(*                                                                          *)
(*   ReachFollowsCriticalFindings    5 mutations, both directions, plus the   *)
(*                                   rank value itself                        *)
(*   NeverEmittedKindsAbsent         1 mutation: a deprecated kind becomes    *)
(*                                   emittable                                  *)
(*   CursorCannotDeriveInternalOnly  3 mutations, one per discovery path       *)
(*                                                                          *)
(* Two are not, and saying so is the point:                                     *)
(*                                                                          *)
(*   TypeOK                 is the TYPE predicate. Every action assigns        *)
(*                          through the constructors it constrains, so breaking *)
(*                          it fails every other invariant simultaneously --   *)
(*                          which is what a type predicate is for. No mutation *)
(*                          breaks it alone, and demanding one would ask for a  *)
(*                          property weaker than its purpose.                  *)
(*                                                                          *)
(*   NoOpenFindingIsResolved (this one) is IMPLIED, not independent. TypeOK      *)
(*                          confines both sets to RestrictingKinds, and every  *)
(*                          action preserves their disjointness by             *)
(*                          construction: Resolve removes the key it adds, and  *)
(*                          Rediscover subtracts `resolved` when computing      *)
(*                          `stillOpen`. All three mutations that could break  *)
(*                          this produce states TypeOK already rejects, so TLC  *)
(*                          refutes TypeOK first.                               *)
(*                                                                          *)
(* That makes it redundant rather than vacuous -- cheap, and it states the      *)
(* intent in one place -- but it is not independently verified, and a reader    *)
(* counting mutations would otherwise conclude it was.                          *)
(***************************************************************************)
NoOpenFindingIsResolved ==
    resolved \cap findings = {}

=============================================================================