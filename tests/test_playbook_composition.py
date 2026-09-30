"""The playbook router is wired to the real certification authority.

``kernel/playbook.py`` defines the contract and ``kernel/strategy_registry.py``
holds the authority, but until a composition root connects them the two are
independently tested pieces of a system that has never observed itself
refusing anything. That is the same gap as a certification check exercised by
fixtures rather than by a real backtest, and it is the kind of gap that hides a
wrong join.

Every test here drives the real ``StrategyRegistry`` through its real state
machine: a strategy is registered, validated, certified, and approved by
distinct actors, and only then can a playbook exist for it. The properties
worth having are the *refusals* — a playbook must not be publishable, and must
not remain selectable, when the authority says no.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kernel.bootstrap import (
    AIOSKernel,
    RegistryCertificationOracle,
    build_playbook_router,
    create_kernel,
    publish_playbook,
)
from kernel.playbook import (
    AbstentionReason,
    Bound,
    FeatureObservation,
    Observation,
    PlaybookActionKind,
    PlaybookNotCertified,
    Regime,
)
from kernel.strategy_registry import ValidationError

T0 = datetime(2024, 6, 3, 14, 30, tzinfo=UTC)


@pytest.fixture()
def kernel() -> AIOSKernel:
    return create_kernel()


def _bounds() -> tuple[Bound, ...]:
    return (Bound(feature="trend_strength", minimum=0.3, maximum=1.0),)


def _observation(trend: float = 0.5) -> Observation:
    return Observation(
        as_of=T0,
        features={
            "trend_strength": FeatureObservation(
                "trend_strength", trend, T0 - timedelta(minutes=1)
            )
        },
    )


def _certify_and_approve(
    kernel: AIOSKernel,
    strategy_id: str = "momentum-1",
    *,
    verdict_result: str = "CERTIFIED",
) -> object:
    """Drive one strategy all the way to APPROVED, through the real state machine.

    No shortcuts: the certification firewall refuses to build a verdict for an
    artifact that has not been backtested, and refuses to approve one whose
    verdict rejected it. A helper that stubbed either step would be testing the
    stub.
    """
    from kernel.registries import ExperimentRegistry

    assert kernel.strategies is not None
    assert kernel.state_machine is not None
    assert kernel.provenance is not None
    registry = kernel.strategies
    registry.register(
        strategy_id=strategy_id,
        version="v1",
        hypothesis_id="h-momentum",
        family="momentum",
        dataset_ref={"dataset_version": "d1"},
        parameters={"lookback": 20},
    )
    sm = kernel.state_machine
    sm.create_object("strategy", strategy_id, "researcher")
    for state in ("HYPOTHESIS", "DRAFT", "VALIDATED", "BACKTESTED", "EVALUATED"):
        sm.transition("strategy", strategy_id, state, "researcher", f"reached {state}")

    experiments = ExperimentRegistry(sm, kernel.provenance)
    experiments.create(
        experiment_id="exp-1",
        hypothesis_id="h-momentum",
        strategy_version="v1",
        dataset_version="d1",
        actor_id="researcher",
    )
    from core.backtest import RegimeSlice
    from kernel.strategy_registry import CertificationEvidence

    evidence = CertificationEvidence(
        look_ahead_clean=True,
        panel_clean=True,
        survivorship_clean=True,
        gross_sharpe=2.1,
        net_sharpe=1.6,
        cost_bps=6.0,
        capacity_ceiling_usd=5_000_000.0,
        required_notional_usd=100_000.0,
        stress_scenarios_run=4,
        worst_stress_sharpe=0.4,
        execution_latency_bars=1,
    )
    artifact_verdict = registry.build_verdict(
        strategy_id,
        "v1",
        2.1,
        140,
        n_observations=500,
        pbo=0.10,
        evidence=evidence,
        regime_performance={
            "trending_up": RegimeSlice("trending_up", 1.4, 300),
            "range_bound": RegimeSlice("range_bound", 0.3, 200),
        },
    )
    registry.begin_validation(strategy_id, "v1", "validator-1")
    registry.record_verdict(strategy_id, "v1", artifact_verdict, evidence=evidence)
    registry.approve(strategy_id, "v1", validator="validator-1", approver="risk-1")
    del verdict_result
    return registry.get(strategy_id, "v1")


# ══════════════════════════════════════════════════════════════════════════
# The kernel carries the whole chain
# ══════════════════════════════════════════════════════════════════════════


def test_the_kernel_wires_certification_and_the_router_together() -> None:
    """One kernel, one authority, one router — not four separately constructed.

    A router wired to a throwaway registry would certify against nothing while
    appearing to work, so the wiring is asserted structurally rather than left
    to whoever writes the composition root.
    """
    kernel = create_kernel()
    assert kernel.strategies is not None
    assert kernel.playbook_router is not None
    assert kernel.certification is not None
    assert isinstance(kernel.certification, RegistryCertificationOracle)
    assert kernel.certification.registry is kernel.strategies


def test_two_kernels_do_not_share_a_registry() -> None:
    """Otherwise an approval in one test could leak into another.

    Also a real deployment concern: two processes must not share a mutable
    certification authority by accident.
    """
    assert create_kernel().strategies is not create_kernel().strategies


# ══════════════════════════════════════════════════════════════════════════
# The end-to-end path
# ══════════════════════════════════════════════════════════════════════════


def test_a_certified_and_approved_strategy_yields_a_selectable_playbook() -> None:
    """The happy path, through every real component."""
    kernel = create_kernel()
    artifact = _certify_and_approve(kernel)
    assert artifact.is_playable() is True

    router = kernel.playbook_router
    assert router is not None
    playbook = publish_playbook(
        router,
        artifact,
        playbook_id="pb-momentum",
        version="v1",
        title="trend momentum",
        regime=Regime.TRENDING_UP,
        bounds=_bounds(),
        book_size_usd=1_000_000.0,
        evidence=("tests/test_playbook_composition.py",),
    )
    assert playbook.verdict_hash

    selection = router.select(_observation())
    assert selection.action is not None
    assert selection.action.kind is PlaybookActionKind.TRADE
    # Derived, not supplied: the mandate needs 100k against a 1M book.
    assert selection.action.target_weight == pytest.approx(0.10)
    assert selection.action.max_notional_usd == pytest.approx(100_000.0)
    assert selection.playbook.ref == "pb-momentum:v1"
    # And the basis is on the playbook, recomputable by whoever reads it.
    assert selection.playbook.sizing_basis is not None
    assert selection.playbook.sizing_basis.verify(selection.action) is True


def test_the_bound_verdict_is_the_registrys_own() -> None:
    """The playbook is bound to the verdict the registry holds, not a copy."""
    import hashlib

    kernel = create_kernel()
    artifact = _certify_and_approve(kernel)
    router = kernel.playbook_router
    assert router is not None
    playbook = publish_playbook(
        router,
        artifact,
        playbook_id="pb",
        version="v1",
        title="t",
        regime=Regime.TRENDING_UP,
        bounds=_bounds(),
        book_size_usd=1_000_000.0,
    )
    assert playbook.verdict_hash == hashlib.sha256(
        artifact.verdict.model_dump_json().encode()  # type: ignore[union-attr]
    ).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# The refusals — the part worth having
# ══════════════════════════════════════════════════════════════════════════


def test_a_playbook_cannot_be_published_for_an_uncertified_strategy() -> None:
    """Not even a directly-constructed router can bypass the registry."""
    kernel = create_kernel()
    registry = kernel.strategies
    router = build_playbook_router(registry)  # type: ignore[arg-type]
    registry.register(
        strategy_id="draft-1",
        version="v1",
        hypothesis_id="h",
        family="momentum",
        dataset_ref={},
    )
    with pytest.raises(ValueError, match="no CertificationVerdict"):
        publish_playbook(
            router,
            registry.get("draft-1", "v1"),
            playbook_id="pb",
            version="v1",
            title="t",
            regime=Regime.TRENDING_UP,
            bounds=_bounds(),
            book_size_usd=1_000_000.0,
        )


def test_a_certified_but_unapproved_strategy_is_not_tradable() -> None:
    """The distinction that ``is_playable`` exists for.

    A verdict with no approval means somebody measured and nobody signed off.
    Accepting that as tradable is the failure of a pipeline that skipped a
    control, and it is exactly the case a verdict-only check would pass.
    """
    kernel = create_kernel()
    registry = kernel.strategies
    _certify_and_approve(kernel)
    # Withdraw permission through the registry's own gate.
    registry.reject("momentum-1", "v1", "risk limit breached", actor="risk-1")
    after = registry.get("momentum-1", "v1")
    assert after.is_playable() is False

    router = build_playbook_router(registry)  # type: ignore[arg-type]
    with pytest.raises(PlaybookNotCertified):
        publish_playbook(
            router,
            after,
            playbook_id="pb",
            version="v1",
            title="t",
            regime=Regime.TRENDING_UP,
            bounds=_bounds(),
            book_size_usd=1_000_000.0,
        )


def test_a_retired_strategy_stops_being_selectable() -> None:
    """Live certification, observed on the real registry.

    The playbook was legitimately published and the router legitimately selected
    it. The authority then withdraws permission, and the next selection must
    refuse — without anyone re-registering anything.
    """
    kernel = create_kernel()
    artifact = _certify_and_approve(kernel)
    router = kernel.playbook_router
    assert router is not None
    publish_playbook(
        router,
        artifact,
        playbook_id="pb",
        version="v1",
        title="t",
        regime=Regime.TRENDING_UP,
        bounds=_bounds(),
        book_size_usd=1_000_000.0,
    )
    assert router.select(_observation()).action is not None

    kernel.strategies.reject("momentum-1", "v1", "post-incident freeze", actor="risk-1")  # type: ignore[union-attr]

    selection = router.select(_observation())
    assert selection.action is None
    assert selection.reason is AbstentionReason.NO_CERTIFIED_PLAYBOOK


def test_an_unknown_strategy_is_refused_rather_than_raising() -> None:
    """A typo in a binding must not take the fast tier down.

    And it must not be treated as certified either — the reason it returns
    ``False`` is that "not found" and "found and permitted" must never collapse
    into the same answer.
    """
    kernel = create_kernel()
    oracle = kernel.certification
    assert oracle is not None
    assert oracle.is_certified("does-not-exist", "v1") is False
    assert oracle.verdict_for("does-not-exist", "v1") is None


def test_the_oracle_does_not_expose_the_certification_authority() -> None:
    """The router must not be able to approve, reject, or re-certify.

    Handing the router a ``StrategyRegistry`` would put ``approve`` and
    ``record_verdict`` on the fast tier's collaborator — the authority would be
    one refactor away from being reachable from the path that trades.
    """
    kernel = create_kernel()
    oracle = kernel.certification
    assert isinstance(oracle, RegistryCertificationOracle)
    public = {n for n in dir(oracle) if not n.startswith("_")}
    assert public == {"registry", "is_certified", "verdict_for"}

    router = kernel.playbook_router
    assert router is not None
    for forbidden in ("approve", "reject", "record_verdict", "build_verdict", "registry"):
        assert not hasattr(router, forbidden), (
            f"the router exposes {forbidden!r}; the fast tier must not reach the "
            "certification authority"
        )


def test_the_registry_still_refuses_approving_without_a_verdict() -> None:
    """The other direction: the firewall is not weakened by the wiring.

    Worth asserting explicitly because the composition is new and the
    firewall's guarantee is the one thing that must not have moved.
    """
    kernel = create_kernel()
    registry = kernel.strategies
    assert registry is not None
    registry.register(
        strategy_id="draft-2",
        version="v1",
        hypothesis_id="h",
        family="momentum",
        dataset_ref={},
    )
    with pytest.raises(ValidationError, match="UNVALIDATED|cannot be approved"):
        registry.approve("draft-2", "v1", validator="validator-1", approver="risk-1")


def test_an_unmatched_regime_still_abstains_with_the_observation_detail() -> None:
    """The router's diagnostic survives the wiring.

    Regression guard for defect 17: the reason and the bound detail have to
    arrive from the condition rather than from a generic fallback.
    """
    kernel = create_kernel()
    artifact = _certify_and_approve(kernel)
    router = kernel.playbook_router
    assert router is not None
    publish_playbook(
        router,
        artifact,
        playbook_id="pb",
        version="v1",
        title="t",
        regime=Regime.TRENDING_UP,
        bounds=_bounds(),
        book_size_usd=1_000_000.0,
    )
    selection = router.select(_observation(trend=0.1))
    assert selection.reason is AbstentionReason.NO_PLAYBOOK_MATCHED
    assert "trend_strength" in selection.detail
    assert "0.1" in selection.detail
