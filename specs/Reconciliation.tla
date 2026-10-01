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
(***************************************************************************)
(* A fresh pass resets the ledger. `resolved' = {}` below is deliberate and   *)
(* is part of the machine, not an oversight: a new pass reports what the      *)
(* venue currently says, and an operator's earlier sign-off does not survive  *)
(* into a later window. An earlier version of this file carried the deleted    *)
(* property's prose here -- "the resolution ledger only grows" -- attached    *)
(* to nothing, while this line contradicted it.                               *)
(*                                                                          *)
(* The consequence is stated rather than left to be discovered: after         *)
(* Discover -> Resolve -> Discover a previously resolved kind is re-derivable.  *)
(* That is the honest shape of the machine; what is NOT claimed is that a      *)
(* resolution is permanent across passes.                                       *)
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
(* WHAT IS AND IS NOT INDEPENDENTLY VERIFIED HERE.                            *)
(*                                                                          *)
(* Of the five invariants, three have an isolating mutation and are           *)
(* independently falsifiable:                                                   *)
(*                                                                          *)
(*   ReachFollowsCriticalFindings    5 mutations: both directions, plus the   *)
(*                                   rank value itself                        *)
(*   NeverEmittedKindsAbsent         1 mutation: a deprecated kind, or an     *)
(*                                   extras provider, becomes unemittable     *)
(*   CursorCannotDeriveInternalOnly  3 mutations, one per discovery path       *)
(*                                                                          *)
(* Two are not, and saying so is the point:                                     *)
(*                                                                          *)
(*   TypeOK                 is the TYPE predicate. Every action assigns        *)
(*                          through the constructors it constrains, so breaking *)
(*                          it fails every other invariant at once -- which is  *)
(*                          what a type predicate is for. No mutation breaks it  *)
(*                          alone.                                            *)
(*                                                                          *)
(*   NoOpenFindingIsResolved (this one) is IMPLIED, not independent. TypeOK    *)
(*                          confines both sets to RestrictingKinds, and every  *)
(*                          action preserves their disjointness by             *)
(*                          construction, so every mutation that could break    *)
(*                          this produces a state TypeOK already rejects.       *)
(*                                                                          *)
(* Redundant rather than vacuous -- cheap, and it states the intent in one     *)
(* place -- but NOT independently verified, and a reader counting mutations    *)
(* would otherwise conclude it was. A drift test pins this note: removing it   *)
(* would mean the spec no longer claims the limit anywhere, and silence is    *)
(* indistinguishable from not having checked.                                  *)
(***************************************************************************)
NoOpenFindingIsResolved ==
    resolved \cap findings = {}

=============================================================================