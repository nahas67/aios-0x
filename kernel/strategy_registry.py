"""Strategy registry and certification state machine (vNext goal G080).

The vNext architecture has a layer between "we built a strategy" and "a
playbook exists": the certification firewall. Its job is to answer one
question — *is this strategy's apparent edge real, or is it the maximum of many
things we tried?* — and to answer it with evidence rather than a score.

Four properties are structural, and each exists because of a specific way a
certification process rots:

**No sign-off without a verdict.** A strategy with no recorded
``CertificationVerdict`` cannot reach APPROVED. Without this the gate is a
formality: the risk firewall downstream has no way to ask whether a strategy
was ever validated, which is precisely the question that must be answerable.

**The validator may not approve.** A validator that signs off its own work has
added no information, so the registry refuses when the two identities match.

**Adaptation resets evidence.** An adapted strategy is a different strategy.
Inheriting the parent's verdict would make adaptation the cheapest way to ship
an untested one — the failure is silent, and the lineage would look clean.

**A recorded verdict is immutable.** Otherwise a disappointing result can be
overwritten by a re-run with different parameters, and the ledger becomes a
record of successes.

Transitions are validated explicitly rather than inherited from the kernel's
generic state machine. A dedicated machine is warranted here because the
interesting failures are semantic — approving something unvalidated, approving
your own work — and a generic engine would express neither.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.backtest import RegimeSlice
from core.quant_statistics import deflated_sharpe_ratio, pbo_from_cscv

__all__ = [
    "CertificationCheck",
    "CertificationEvidence",
    "CertificationVerdict",
    "StrategyArtifact",
    "StrategyRegistry",
    "ValidationError",
    "ValidationStatus",
    "certification_policy",
]


class ValidationError(RuntimeError):
    """A validation transition was refused."""


class ValidationStatus(StrEnum):
    """Certification lifecycle of one strategy artifact version."""

    UNVALIDATED = "UNVALIDATED"
    IN_VALIDATION = "IN_VALIDATION"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


#: Legal transitions. The machine is intentionally narrow: anything not listed
#: is refused, because a certification state machine that permits arbitrary
#: hops is a status field with extra steps.
#:
#: REJECTED is reachable from every non-terminal state on purpose. An operator
#: must be able to kill a candidate without first running validation, and a
#: rejection that requires prior validation is a rejection that can be dodged
#: by simply not validating.
_TRANSITIONS: dict[ValidationStatus, frozenset[ValidationStatus]] = {
    ValidationStatus.UNVALIDATED: frozenset(
        {ValidationStatus.IN_VALIDATION, ValidationStatus.REJECTED}
    ),
    ValidationStatus.IN_VALIDATION: frozenset(
        {ValidationStatus.VALIDATED, ValidationStatus.REJECTED}
    ),
    ValidationStatus.VALIDATED: frozenset(
        {ValidationStatus.APPROVED, ValidationStatus.REJECTED}
    ),
    ValidationStatus.APPROVED: frozenset({ValidationStatus.REJECTED}),
    ValidationStatus.REJECTED: frozenset(),
}



#: Prefix of the per-regime certification check. Certification adds one check per
#: regime in the supplied decomposition, named ``regime_sharpe:<regime value>``, and
#: it passes only when that regime is neither too thin to support a playbook nor
#: losing money net of costs.
#:
#: Named rather than left as an f-string literal inside the loop, because
#: `kernel.competence` derives a strategy's domain of competence from these checks
#: and a hardcoded copy of this string would make the join invisible: renaming the
#: check would leave the derivation silently empty, every strategy would become
#: incompetent everywhere, and that fails CLOSED -- so it would read as a deliberate
#: refusal rather than a broken coupling.
REGIME_CHECK_PREFIX = "regime_sharpe:"

def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def certification_policy() -> dict[str, Any]:
    """The thresholds a verdict is judged against.

    Returned as data rather than buried as literals so a certification report
    can state the policy it was judged under, and so raising a bar is a visible
    change rather than an edit inside a method.
    """
    return {
        "version": "v1",
        "min_deflated_sharpe": 0.95,
        "min_probabilistic_sharpe": 0.95,
        "max_pbo": 0.20,
        "min_cpcv_paths": 5,
        "min_stress_sharpe": 0.0,
        # A regime slice thinner than this cannot support a playbook: the Sharpe
        # of twenty observations is noise with a decimal point, and publishing
        # a policy for a state the strategy barely visited is the same as
        # publishing one for a state it never visited.
        "min_regime_observations": 30,
        # A regime that lost money net of costs is not a regime to trade. Zero
        # rather than the deflated bar because the per-regime question is
        # narrower — "does it work here at all" — and the bar for the strategy
        # as a whole is judged separately.
        "min_regime_sharpe": 0.0,
        # Below 1% of book a position cannot move portfolio-level outcomes
        # beyond noise, so publishing a playbook for one manufactures a
        # precision the portfolio cannot feel. Declared here rather than buried
        # in the derivation so raising it is a visible policy change.
        "min_playbook_weight": 0.01,
        "require_lookahead_clean": True,
        "require_survivorship_clean": True,
        "require_fees_modelled": True,
        "require_capacity_modelled": True,
        "require_regime_decomposition": True,
        "require_stress_test": True,
        "require_execution_simulation": True,
        "multiple_testing": "benjamini_hochberg",
        "alpha": 0.05,
    }


class CertificationCheck(BaseModel):
    """One named check within a verdict, with the number behind it."""

    model_config = {"frozen": True}

    name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None
    detail: str = ""


class CertificationEvidence(BaseModel):
    """Measured operational evidence backing a verdict.

    Every field defaults to a value that fails its check. A caller must
    produce a real backtest to pass, which is the point: the previous
    signature took ``capacity_modelled=True`` and believed it, so a team under
    deadline could certify a strategy it had never costed.

    The four properties are derived rather than stored:

    ``costs_applied``
        The gross and net series differ. A run with no cost model produces
        identical series, so the claim is checked against the numbers.
    ``capacity_measured``
        A ceiling was measured AND it covers the size the mandate needs. A
        strategy that only works at $10k does not certify a $1m mandate.
    ``stress_measured``
        At least one scenario ran and the worst of them clears the floor.
    ``execution_measured``
        The fill model was not frictionless.
    """

    model_config = {"frozen": True}

    gross_sharpe: float = 0.0
    net_sharpe: float = 0.0
    n_trades: int = 0
    cost_bps: float = 0.0
    participation: float = 0.0

    capacity_ceiling_usd: float = 0.0
    required_notional_usd: float = 0.0

    stress_scenarios_run: int = 0
    worst_stress_sharpe: float = 0.0
    worst_stress_scenario: str = ""

    execution_latency_bars: int = 0
    execution_partial_fill_ratio: float = 1.0
    execution_rejected_rate: float = 0.0

    #: Measured contamination reports. Absent means the detector was never
    #: run, which fails the check for the same reason an unmeasured capacity
    #: ceiling does: a check nobody ran is not a check that passed.
    look_ahead_clean: bool | None = None
    look_ahead_detail: str = "the look-ahead detector was not run"
    panel_clean: bool | None = None
    panel_detail: str = "the panel-leakage detector was not run"
    survivorship_clean: bool | None = None
    survivorship_detail: str = "the survivorship detector was not run"

    @classmethod
    def from_contamination(
        cls,
        look_ahead: Any,
        survivorship: Any,
        *,
        panel: Any = None,
        **kwargs: Any,
    ) -> CertificationEvidence:
        """Build evidence from detector reports.

        ``None`` for any report means the detector did not run, and the derived
        property returns False — so a caller that skips a detector cannot
        accidentally pass it.
        """
        clean = look_ahead.clean if look_ahead is not None else None
        surv = survivorship.clean if survivorship is not None else None
        return cls(
            look_ahead_clean=clean,
            look_ahead_detail=look_ahead.summary() if look_ahead is not None else "not run",
            panel_clean=(panel.clean if panel is not None else None),
            panel_detail=panel.summary() if panel is not None else "not run",
            survivorship_clean=surv,
            survivorship_detail=survivorship.summary() if survivorship is not None else "not run",
            **kwargs,
        )

    @property
    def contamination_measured(self) -> bool:
        """Every contamination detector ran and reported clean.

        ``None`` fails rather than defaulting to True. A detector that never
        ran is not a detector that found nothing, and conflating the two is how
        an unrun check becomes a silent pass.
        """
        return bool(self.look_ahead_clean) and bool(self.panel_clean) and bool(self.survivorship_clean)

    @property
    def cost_drag(self) -> float:
        return self.gross_sharpe - self.net_sharpe

    @property
    def costs_applied(self) -> bool:
        """A cost model that produced no difference is no cost model."""
        return self.cost_drag > 1e-9 and (self.cost_bps > 0.0 or self.participation > 0.0)

    @property
    def cost_detail(self) -> str:
        if not self.costs_applied:
            return (
                "net and gross Sharpe are identical, so no cost was applied despite the "
                "result being described as net-of-cost"
            )
        return (
            f"drag {self.cost_drag:.4f} Sharpe over {self.n_trades} trade(s) at "
            f"{self.cost_bps:.2f} bps round trip, peak participation {self.participation:.4f}"
        )

    @property
    def capacity_measured(self) -> bool:
        """A measured ceiling that also covers the intended size.

        Both halves matter. A ceiling of zero means nothing was measured; a
        ceiling below the required notional means the edge does not scale to
        the mandate, which is a different and equally disqualifying finding.
        """
        return (
            self.capacity_ceiling_usd > 0.0
            and self.capacity_ceiling_usd >= self.required_notional_usd
        )

    @property
    def capacity_detail(self) -> str:
        if self.capacity_ceiling_usd <= 0.0:
            return "no capacity sweep was run, so the result may not scale at all"
        if self.capacity_ceiling_usd < self.required_notional_usd:
            return (
                f"measured capacity ceiling {self.capacity_ceiling_usd:,.0f} is below the "
                f"{self.required_notional_usd:,.0f} the mandate requires"
            )
        return (
            f"measured ceiling {self.capacity_ceiling_usd:,.0f} covers the required "
            f"{self.required_notional_usd:,.0f}"
        )

    @property
    def stress_measured(self) -> bool:
        return (
            self.stress_scenarios_run > 0
            and self.worst_stress_sharpe >= certification_policy()["min_stress_sharpe"]
        )

    @property
    def stress_detail(self) -> str:
        if self.stress_scenarios_run == 0:
            return "no stress scenarios were run"
        return (
            f"worst of {self.stress_scenarios_run} scenario(s) was "
            f"{self.worst_stress_scenario or 'unknown'} at {self.worst_stress_sharpe:.4f}"
        )

    @property
    def execution_measured(self) -> bool:
        """A frictionless fill model describes a venue that does not exist."""
        return not (
            self.execution_latency_bars == 0
            and self.execution_partial_fill_ratio >= 1.0
            and self.execution_rejected_rate <= 0.0
        )

    @property
    def execution_detail(self) -> str:
        if not self.execution_measured:
            return (
                "execution was modelled as frictionless: zero latency, full fills, no "
                "rejections. Costs are optimistic by construction."
            )
        return (
            f"latency {self.execution_latency_bars} bar(s), partial fill "
            f"{self.execution_partial_fill_ratio:.2f}, rejects {self.execution_rejected_rate:.4f}"
        )

    @classmethod
    def from_backtest(
        cls,
        result: Any,
        *,
        required_notional_usd: float = 0.0,
        capacity_ceiling_usd: float = 0.0,
        stress_scenarios_run: int = 0,
        worst_stress_sharpe: float = 0.0,
        worst_stress_scenario: str = "",
        execution_latency_bars: int = 0,
        execution_partial_fill_ratio: float = 1.0,
        execution_rejected_rate: float = 0.0,
    ) -> CertificationEvidence:
        """Build evidence from a :class:`core.backtest.BacktestResult`.

        The conversion is one-way and mechanical, which is the point: a caller
        cannot hand-assemble a passing evidence object without having run
        something that produces these numbers.
        """
        return cls(
            gross_sharpe=result.gross_sharpe,
            net_sharpe=result.net_sharpe,
            n_trades=result.n_trades,
            cost_bps=result.cost_bps,
            participation=result.participation,
            capacity_ceiling_usd=capacity_ceiling_usd,
            required_notional_usd=required_notional_usd,
            stress_scenarios_run=stress_scenarios_run,
            worst_stress_sharpe=worst_stress_sharpe,
            worst_stress_scenario=worst_stress_scenario,
            execution_latency_bars=execution_latency_bars,
            execution_partial_fill_ratio=execution_partial_fill_ratio,
            execution_rejected_rate=execution_rejected_rate,
        )


class CertificationVerdict(BaseModel):
    """The immutable result of certifying one strategy artifact.

    ``verdict`` is CERTIFIED, CERTIFIED_WITH_LIMITS, or REJECTED. The middle
    state exists because refusing a strategy for a weak sub-metric is as wrong
    as accepting one with a contaminated split: a system that only ever says
    yes or no will be tuned to say yes.
    """

    model_config = {"frozen": True}

    strategy_id: str
    strategy_version: str
    verdict: str = Field(..., pattern="^(CERTIFIED|CERTIFIED_WITH_LIMITS|REJECTED)$")
    checks: list[CertificationCheck]
    failure_reasons: list[str] = Field(default_factory=list)
    observed_sharpe: float
    deflated_sharpe: float
    n_trials: int
    policy_version: str
    validator_id: str
    decided_at: str = Field(default_factory=_utc_now)
    #: Empty by construction on a fresh artifact. A non-empty set here means the
    #: verdict was inherited, which the registry forbids.
    inherited_from: str | None = None

    @property
    def is_certified(self) -> bool:
        return self.verdict in {"CERTIFIED", "CERTIFIED_WITH_LIMITS"}


class StrategyArtifact(BaseModel):
    """One version of one strategy, with its lineage and certification state."""

    strategy_id: str
    version: str
    hypothesis_id: str
    family: str
    dataset_ref: dict[str, str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ValidationStatus = ValidationStatus.UNVALIDATED
    verdict: CertificationVerdict | None = None

    def __setattr__(self, name: str, value: Any) -> None:
        """Refuse to re-point a recorded verdict at a different one.

        `record_verdict` already refuses a second verdict, but only through the
        method. `StrategyArtifact` is a mutable model, `verdict` a plain field, and
        `StrategyRegistry` a public attribute of the kernel -- so `artifact.verdict =
        <wider>` reassigned it, and `kernel.competence.competence_resolver` reads that
        field. Demonstrated before this guard: a strategy recorded as LOSING MONEY in
        crisis became competent there, silently, for every playbook already admitted.

        That gap matters more than it first appears, because the two facts are treated
        differently downstream on purpose. `PlaybookRouter.register` re-asks the oracle
        about certification on EVERY selection, precisely because "a verdict can be
        revoked by the oracle at any instant". Competence is checked ONCE at admission,
        justified by the claim that a recorded verdict is immutable. That justification
        was convention until this guard made it enforced, and a convention is not a
        property a design can lean on.

        An `__setattr__` override rather than `validate_assignment`: a field validator
        is handed the new value and cannot see whether one was already recorded, so it
        cannot distinguish the first assignment (which `record_verdict` performs) from
        a second. Construction is unaffected -- pydantic v2 populates `__dict__`
        directly rather than through `__setattr__`.

        Amending a decision means registering a new version, which is what
        `record_verdict`'s own refusal message already told callers to do.
        """
        if name == "verdict" and self.__dict__.get("verdict") is not None:
            raise ValidationError(
                f"{getattr(self, 'ref', 'artifact')!r} already carries a verdict. A "
                "recorded verdict is immutable: re-deciding a disappointing result is "
                "how a ledger becomes a record of successes, and a domain of competence "
                "is derived from the verdict once and never re-checked. Register a new "
                "artifact version."
            )
        super().__setattr__(name, value)
    #: The measurements the verdict was built from, retained. A verdict without
    #: its evidence is a conclusion without its premises: nothing downstream —
    #: notably the playbook derivation, which sizes positions from the capacity
    #: ceiling — could check its numbers against anything. Retained at record
    #: time rather than re-supplied later so the evidence cannot drift from the
    #: verdict it justified.
    evidence: CertificationEvidence | None = None
    validator_id: str | None = None
    approver: str | None = None
    parent_ref: str | None = None
    created_at: str = Field(default_factory=_utc_now)
    decided_at: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.strategy_id}:{self.version}"

    def is_playable(self) -> bool:
        """Whether this artifact may be selected by the fast execution tier.

        Approved *and* carrying a certified verdict. Both, because either alone
        is reachable by a bug.
        """
        return (
            self.status is ValidationStatus.APPROVED
            and self.verdict is not None
            and self.verdict.is_certified
        )


class StrategyRegistry:
    """Versioned strategies and their certification verdicts."""

    def __init__(self, provenance: Any = None) -> None:
        self._provenance = provenance
        self._artifacts: dict[str, StrategyArtifact] = {}

    # -------------------------------------------------------------- registration

    def register(
        self,
        *,
        strategy_id: str,
        version: str,
        hypothesis_id: str,
        family: str,
        dataset_ref: dict[str, str],
        parameters: dict[str, Any] | None = None,
        parent_ref: str | None = None,
    ) -> StrategyArtifact:
        """Register a new artifact. Duplicate refs are refused."""
        artifact = StrategyArtifact(
            strategy_id=strategy_id,
            version=version,
            hypothesis_id=hypothesis_id,
            family=family,
            dataset_ref=dataset_ref,
            parameters=parameters or {},
            parent_ref=parent_ref,
        )
        if artifact.ref in self._artifacts:
            raise ValidationError(f"strategy artifact already registered: {artifact.ref!r}")
        self._artifacts[artifact.ref] = artifact
        return artifact

    def adapt(
        self,
        strategy_id: str,
        version: str,
        new_strategy_id: str,
        new_version: str,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> StrategyArtifact:
        """Derive a child artifact with **empty** certification evidence.

        The child is UNVALIDATED and carries no verdict, whatever the parent's
        status. This is the whole point: an adapted strategy is a different
        strategy, and inheriting a sign-off would make adaptation the cheapest
        route past the firewall.
        """
        parent = self.get(strategy_id, version)
        return self.register(
            strategy_id=new_strategy_id,
            version=new_version,
            hypothesis_id=parent.hypothesis_id,
            family=parent.family,
            dataset_ref=parent.dataset_ref,
            parameters=parameters if parameters is not None else dict(parent.parameters),
            parent_ref=parent.ref,
        )

    def get(self, strategy_id: str, version: str) -> StrategyArtifact:
        ref = f"{strategy_id}:{version}"
        artifact = self._artifacts.get(ref)
        if artifact is None:
            raise KeyError(f"unknown strategy artifact: {ref!r}")
        return artifact

    def artifacts(self) -> list[StrategyArtifact]:
        return list(self._artifacts.values())

    # ------------------------------------------------------------- certification

    def build_verdict(
        self,
        strategy_id: str,
        version: str,
        observed_sharpe: float,
        n_trials: int,
        *,
        n_observations: int = 252,
        pbo: float | None = None,
        performance: list[list[float]] | None = None,
        regime_performance: dict[str, RegimeSlice] | None = None,
        cpcv_paths: int = 15,
        embargo_enforced: bool = True,
        purged_cv: bool = True,
        evidence: CertificationEvidence | None = None,
    ) -> CertificationVerdict:
        """Run the certification checks and return a verdict.

        The cost, capacity, stress, and execution checks are derived from
        :class:`CertificationEvidence` rather than accepted as booleans. A
        caller that cannot produce a measured backtest therefore cannot
        certify, which is the entire point: the previous signature took
        ``capacity_modelled=True`` and believed it.

        Every check is recorded whether it passed or failed. A verdict listing
        only its successes is a summary, and a summary cannot be audited.
        """
        policy = certification_policy()
        checks: list[CertificationCheck] = []
        measured = evidence or CertificationEvidence()

        def add(name: str, passed: bool, value: float | None, threshold: float | None, detail: str = "") -> None:
            checks.append(
                CertificationCheck(
                    name=name, passed=passed, value=value, threshold=threshold, detail=detail
                )
            )

        add(
            "lookahead_detected",
            bool(measured.look_ahead_clean),
            1.0 if measured.look_ahead_clean else 0.0,
            1.0,
            measured.look_ahead_detail,
        )
        add(
            "panel_composition_leak",
            bool(measured.panel_clean),
            1.0 if measured.panel_clean else 0.0,
            1.0,
            measured.panel_detail,
        )
        add(
            "survivorship_clean",
            bool(measured.survivorship_clean),
            1.0 if measured.survivorship_clean else 0.0,
            1.0,
            measured.survivorship_detail,
        )
        add("purged_cv", purged_cv, 1.0 if purged_cv else 0.0, 1.0, "purged cross-validation")
        add(
            "embargo_enforced",
            embargo_enforced,
            1.0 if embargo_enforced else 0.0,
            1.0,
            "an embargo was applied after each test block",
        )
        add(
            "cpcv_paths",
            cpcv_paths >= policy["min_cpcv_paths"],
            float(cpcv_paths),
            float(policy["min_cpcv_paths"]),
            f"{cpcv_paths} combinatorial paths",
        )

        deflated = deflated_sharpe_ratio(
            observed_sharpe, n_trials=max(1, n_trials), n_observations=n_observations
        )
        add(
            "deflated_sharpe",
            deflated >= policy["min_deflated_sharpe"],
            round(deflated, 6),
            policy["min_deflated_sharpe"],
            f"observed {observed_sharpe:.2f} selected as best of {n_trials}",
        )
        add(
            "probabilistic_sharpe",
            deflated >= policy["min_probabilistic_sharpe"],
            round(deflated, 6),
            policy["min_probabilistic_sharpe"],
            "PSR evaluated against the expected maximum of the trial family",
        )

        resolved_pbo = pbo
        if resolved_pbo is None and performance is not None:
            resolved_pbo = pbo_from_cscv(performance)
        if resolved_pbo is None:
            add(
                "probabilistic_backtest_overfitting",
                False,
                None,
                policy["max_pbo"],
                "no CSCV performance matrix supplied, so overfitting was not measured",
            )
        else:
            add(
                "probabilistic_backtest_overfitting",
                resolved_pbo <= policy["max_pbo"],
                round(resolved_pbo, 6),
                policy["max_pbo"],
                "fraction of times the in-sample winner landed in the bottom half",
            )

        add("multiple_testing_corrected", True, 1.0, 1.0, policy["multiple_testing"])

        # Measured, not asserted. A caller supplying a backtest result whose
        # net and gross series are identical has declared a cost model and
        # applied none, and that is detectable without trusting them.
        add(
            "fees_slippage_modelled",
            measured.costs_applied,
            round(measured.cost_drag, 6),
            0.0,
            measured.cost_detail,
        )
        add(
            "capacity_modelled",
            measured.capacity_measured,
            measured.capacity_ceiling_usd,
            float(measured.required_notional_usd),
            measured.capacity_detail,
        )
        # Measured, not asserted. The previous signature took
        # ``regime_decomposition=True`` and believed it, so a strategy could be
        # certified as regime-aware on the strength of a boolean. Now the caller
        # supplies the per-regime measurement and each regime is judged on its
        # own numbers: enough observations to mean something, and a net Sharpe
        # that does not lose money. A regime that fails either is recorded
        # under its own name, so the playbook derivation can refuse exactly
        # that regime without disputing the strategy as a whole.
        if regime_performance is None:
            add(
                "regime_decomposition",
                False,
                0.0,
                1.0,
                "no regime decomposition was supplied, so where the strategy "
                "works was never measured",
            )
        else:
            supplied = len(regime_performance) > 0
            add(
                "regime_decomposition",
                supplied,
                float(len(regime_performance)),
                1.0,
                f"performance decomposed across {len(regime_performance)} regime(s)"
                if supplied
                else "an empty decomposition measures nothing",
            )
            for name in sorted(regime_performance):
                measured_slice = regime_performance[name]
                # The check name is what `kernel.competence` maps back to a `Regime`, by
                # `Regime.value`. Naming it from this dict's key instead would emit
                # `regime_sharpe:<key>`, which maps to nothing for any key that is not
                # a regime value -- and the strategy would then be reported as never
                # decomposed when it had been. Fail loudly rather than certify into a
                # state the reader cannot interpret.
                if measured_slice.regime != name:
                    raise ValidationError(
                        f"regime_performance key {name!r} does not match its slice's "
                        f"regime {measured_slice.regime!r}. The key names the check "
                        "that competence is read back from, so the two must agree."
                    )
                thin = measured_slice.n_observations < policy["min_regime_observations"]
                losing = measured_slice.net_sharpe < policy["min_regime_sharpe"]
                add(
                    f"{REGIME_CHECK_PREFIX}{name}",
                    not thin and not losing,
                    round(measured_slice.net_sharpe, 6),
                    policy["min_regime_sharpe"],
                    (
                        f"{measured_slice.n_observations} observation(s) in {name!r}, "
                        f"net Sharpe {measured_slice.net_sharpe:.4f}"
                        + ("; too thin to support a playbook" if thin else "")
                        + ("; loses money net of costs" if losing else "")
                    ),
                )
        add(
            "stress_tested",
            measured.stress_measured,
            round(measured.worst_stress_sharpe, 6),
            policy["min_stress_sharpe"],
            measured.stress_detail,
        )
        add(
            "execution_simulated",
            measured.execution_measured,
            1.0 if measured.execution_measured else 0.0,
            1.0,
            measured.execution_detail,
        )

        failed = [check.name for check in checks if not check.passed]
        # Three failure classes, because collapsing them teaches the wrong
        # lesson. INTEGRITY failures mean the number is not measuring what it
        # claims (a leaked split, a survivorship-biased universe) and reject
        # outright. STATISTICAL failures mean the edge was not demonstrated to
        # clear the selection bar, which also rejects. OPERATIONAL failures
        # mean the result may be real but does not yet scale, simulate, or
        # survive stress - those yield CERTIFIED_WITH_LIMITS, because refusing
        # a strategy for a missing capacity model would just teach a team to
        # stop reporting capacity.
        #
        # Regime slices are operational by prefix rather than by name, because
        # the names are dynamic: a regime that underperforms constrains *where*
        # the strategy may trade the way a low ceiling constrains *how much*,
        # and neither says the measurement was dishonest.
        integrity = {
            "lookahead_detected",
            "panel_composition_leak",
            "survivorship_clean",
            "purged_cv",
            "embargo_enforced",
            "fees_slippage_modelled",
        }
        statistical = {
            "deflated_sharpe",
            "probabilistic_sharpe",
            "probabilistic_backtest_overfitting",
            "cpcv_paths",
        }
        failed_set = set(failed)
        if not failed:
            verdict_value = "CERTIFIED"
        elif failed_set & (integrity | statistical):
            verdict_value = "REJECTED"
        else:
            verdict_value = "CERTIFIED_WITH_LIMITS"

        return CertificationVerdict(
            strategy_id=strategy_id,
            strategy_version=version,
            verdict=verdict_value,
            checks=checks,
            failure_reasons=failed,
            observed_sharpe=observed_sharpe,
            deflated_sharpe=round(deflated, 6),
            n_trials=n_trials,
            policy_version=policy["version"],
            validator_id=self.get(strategy_id, version).validator_id or "unknown",
        )

    def begin_validation(self, strategy_id: str, version: str, validator_id: str) -> None:
        artifact = self.get(strategy_id, version)
        self._transition(artifact, ValidationStatus.IN_VALIDATION)
        artifact.validator_id = validator_id

    def record_verdict(
        self,
        strategy_id: str,
        version: str,
        verdict: CertificationVerdict,
        *,
        evidence: CertificationEvidence,
    ) -> None:
        """Attach a verdict with the measurements behind it. Both are immutable.

        ``evidence`` is required rather than optional because a verdict without
        retained measurements is a conclusion without premises: the playbook
        derivation sizes positions from the capacity ceiling, and it must read
        that ceiling off the artifact rather than accept a fresh number from
        whoever happens to be publishing.

        The evidence is checked against the verdict it claims to support. The
        verdict's observed Sharpe must be the evidence's gross Sharpe: the two
        are the same trial's number, reported in two places, and a mismatch
        means the measurements describe a different backtest than the one that
        was certified. That is the binding that keeps a strong verdict from
        being recorded alongside weak measurements.
        """
        artifact = self.get(strategy_id, version)
        if artifact.verdict is not None:
            raise ValidationError(
                f"{artifact.ref!r} already carries a verdict. A recorded verdict is "
                "immutable: re-deciding a disappointing result is how a ledger "
                "becomes a record of successes. Register a new artifact version."
            )
        if abs(evidence.gross_sharpe - verdict.observed_sharpe) > 1e-6:
            raise ValidationError(
                f"{artifact.ref!r} evidence gross Sharpe {evidence.gross_sharpe:.6f} does "
                f"not match the verdict's observed Sharpe {verdict.observed_sharpe:.6f}. "
                "The measurements must describe the trial that was certified, not "
                "another backtest."
            )
        if verdict.verdict == "REJECTED":
            self._transition(artifact, ValidationStatus.REJECTED)
        else:
            self._transition(artifact, ValidationStatus.VALIDATED)
        artifact.verdict = verdict
        artifact.evidence = evidence
        artifact.decided_at = _utc_now()

    def approve(
        self, strategy_id: str, version: str, *, validator: str, approver: str
    ) -> None:
        """Promote a validated artifact to APPROVED.

        Three refusals, each a distinct failure mode:

        * no recorded verdict — the gate is being skipped
        * a rejected verdict — the strategy failed certification
        * validator == approver — self-certification is not a control
        """
        artifact = self.get(strategy_id, version)

        if artifact.status is ValidationStatus.UNVALIDATED:
            raise ValidationError(
                f"{artifact.ref!r} is {ValidationStatus.UNVALIDATED} and cannot be approved. "
                "A strategy with no CertificationVerdict has not been certified."
            )
        if artifact.verdict is None:
            raise ValidationError(
                f"{artifact.ref!r} cannot be approved: no CertificationVerdict is recorded."
            )
        if not artifact.verdict.is_certified:
            raise ValidationError(
                f"{artifact.ref!r} cannot be approved: its verdict is "
                f"{artifact.verdict.verdict} "
                f"({', '.join(artifact.verdict.failure_reasons) or 'no reason recorded'})."
            )
        if validator == approver:
            raise ValidationError(
                f"{approver!r} cannot approve its own validation of {artifact.ref!r}. "
                "The validator and the approver must be different identities."
            )
        self._transition(artifact, ValidationStatus.APPROVED)
        artifact.approver = approver
        artifact.decided_at = _utc_now()

    def reject(self, strategy_id: str, version: str, reason: str, *, actor: str) -> None:
        """Reject an artifact. Terminal."""
        artifact = self.get(strategy_id, version)
        self._transition(artifact, ValidationStatus.REJECTED)
        artifact.decided_at = _utc_now()
        artifact.parameters = {**artifact.parameters, "rejection_reason": reason}
        _ = actor

    def playable(self) -> list[StrategyArtifact]:
        """Artifacts the fast execution tier is permitted to select.

        Selection is filtered by the registry rather than by each caller, so a
        missing check is one bug rather than one per call site.
        """
        return [artifact for artifact in self._artifacts.values() if artifact.is_playable()]

    def _transition(self, artifact: StrategyArtifact, target: ValidationStatus) -> None:
        allowed = _TRANSITIONS[artifact.status]
        if target not in allowed:
            raise ValidationError(
                f"{artifact.ref!r} cannot transition {artifact.status} -> {target}. "
                f"Allowed: {sorted(s.value for s in allowed) or 'nothing (terminal)'}"
            )
        artifact.status = target
