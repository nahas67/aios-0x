"""The experiment ledger exists to remember failures (goal G070).

An experiment ledger that only keeps successes is worse than no ledger: it
manufactures the exact illusion the vNext architecture is built to prevent.

> 10,000 failed experiments → 1 lucky result → a claimed 99% strategy

That chain needs all three links, and this suite removes two of them. A failed
run must carry its reason, or it is indistinguishable from a run that was never
attempted and the count of trials cannot be audited. And a run must know its
parent, or "what did we try before this?" is a grep rather than a query.

The tests are deliberately blunt about the direction of the argument. It is
easy to write a suite that proves a happy path and leaves the failure path
unchanged; every test here is about the failure.
"""

from __future__ import annotations

import pytest

from kernel.bootstrap import create_kernel
from kernel.registries import ExperimentRegistry, ExperimentStatus


@pytest.fixture()
def registry() -> ExperimentRegistry:
    kernel = create_kernel()
    return ExperimentRegistry(kernel.state_machine, kernel.provenance)


def _create(
    registry: ExperimentRegistry,
    experiment_id: str = "exp-1",
    *,
    parent_id: str | None = None,
    hypothesis_id: str = "hyp-1",
) -> object:
    return registry.create(
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
        parent_id=parent_id,
    )


# ══════════════════════════════════════════════════════════════════════════
# A failure must carry its reason
# ══════════════════════════════════════════════════════════════════════════


def test_a_failure_records_its_reason(registry: ExperimentRegistry) -> None:
    """The single most important field in this module."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "deflated sharpe 0.31 below the 0.95 bar")
    run = registry.get("exp-1")
    assert run.status is ExperimentStatus.FAILED
    assert run.failure_reason == "deflated sharpe 0.31 below the 0.95 bar"
    assert run.failed_at


def test_a_failure_without_a_reason_is_refused(registry: ExperimentRegistry) -> None:
    """An unexplained failure is the failure mode the ledger prevents.

    Allowing an empty reason means a run can be recorded as failed with no
    record of why, which is the same as not having run it — except that it
    still counts toward the trial denominator.
    """
    _create(registry)
    registry.start("exp-1", "system")
    with pytest.raises(ValueError, match="requires a failure_reason"):
        registry.fail("exp-1", "system", "   ")


def test_the_error_appears_in_both_places(registry: ExperimentRegistry) -> None:
    """``result`` is what a report reads; ``failure_reason`` is what a query reads."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "contaminated split")
    run = registry.get("exp-1")
    assert run.result["error"] == "contaminated split"
    assert run.failure_reason == "contaminated split"


def test_failures_are_queryable(registry: ExperimentRegistry) -> None:
    """The question the ledger exists to answer."""
    _create(registry, "exp-1", hypothesis_id="h-momentum")
    _create(registry, "exp-2", hypothesis_id="h-momentum")
    _create(registry, "exp-3", hypothesis_id="h-carry")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo 0.62")
    registry.start("exp-2", "system")
    registry.fail("exp-2", "system", "net sharpe below gross by 40%")
    registry.start("exp-3", "system")
    registry.complete("exp-3", "system", {"sharpe": 1.2})

    failures = registry.failures()
    assert [f.experiment_id for f in failures] == ["exp-1", "exp-2"]
    assert {f.failure_reason for f in failures} == {
        "pbo 0.62",
        "net sharpe below gross by 40%",
    }


def test_a_failure_survives_being_read_again(registry: ExperimentRegistry) -> None:
    """A verdict that dies with the process means the same failure is paid for twice."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "capacity ceiling below the mandate")
    assert registry.get("exp-1").failure_reason == "capacity ceiling below the mandate"
    assert registry.get("exp-1").failure_reason == "capacity ceiling below the mandate"


# ══════════════════════════════════════════════════════════════════════════
# Lineage: parent_id
# ══════════════════════════════════════════════════════════════════════════


def test_a_child_records_its_parent(registry: ExperimentRegistry) -> None:
    _create(registry, "exp-1")
    child = _create(registry, "exp-2", parent_id="exp-1")
    assert child.parent_id == "exp-1"


def test_an_experiment_cannot_be_its_own_parent(registry: ExperimentRegistry) -> None:
    """A self-referential derivation tree is a cycle wearing a tree's clothes."""
    with pytest.raises(ValueError, match="cannot be its own parent"):
        _create(registry, "exp-1", parent_id="exp-1")


def test_a_dangling_parent_is_refused(registry: ExperimentRegistry) -> None:
    """A tree with a missing node is not queryable in the way that matters."""
    with pytest.raises(KeyError, match="parent experiment not found"):
        _create(registry, "exp-2", parent_id="does-not-exist")


def test_lineage_is_root_first(registry: ExperimentRegistry) -> None:
    _create(registry, "exp-1")
    _create(registry, "exp-2", parent_id="exp-1")
    _create(registry, "exp-3", parent_id="exp-2")
    assert [r.experiment_id for r in registry.lineage("exp-3")] == [
        "exp-1",
        "exp-2",
        "exp-3",
    ]


def test_a_root_has_a_single_element_lineage(registry: ExperimentRegistry) -> None:
    _create(registry, "exp-1")
    assert [r.experiment_id for r in registry.lineage("exp-1")] == ["exp-1"]


def test_children_are_queryable(registry: ExperimentRegistry) -> None:
    _create(registry, "exp-1")
    _create(registry, "exp-2", parent_id="exp-1")
    _create(registry, "exp-3", parent_id="exp-1")
    _create(registry, "exp-4", parent_id="exp-2")
    assert {c.experiment_id for c in registry.children("exp-1")} == {"exp-2", "exp-3"}
    assert [c.experiment_id for c in registry.children("exp-2")] == ["exp-4"]
    assert registry.children("exp-4") == []


def test_lineage_survives_a_failure_ancestor(registry: ExperimentRegistry) -> None:
    """The whole point: a dead branch is still a branch, and it is still recorded."""
    _create(registry, "exp-1")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "no edge after costs")
    _create(registry, "exp-2", parent_id="exp-1")
    assert [r.experiment_id for r in registry.lineage("exp-2")] == ["exp-1", "exp-2"]
    assert registry.get("exp-1").failure_reason == "no edge after costs"


# ══════════════════════════════════════════════════════════════════════════
# The trial denominator
# ══════════════════════════════════════════════════════════════════════════


def test_attempt_count_is_the_denominator_of_any_claimed_rate(registry: ExperimentRegistry) -> None:
    """A Sharpe quoted without the number of things tried is an anecdote.

    One hypothesis tried ten times and found once has a 10% hit rate, and that
    number has to be derivable from the ledger rather than remembered.
    """
    for index in range(10):
        _create(registry, f"exp-{index}", hypothesis_id="h-momentum")
    _create(registry, "exp-carry", hypothesis_id="h-carry")
    assert registry.attempt_count() == {"h-momentum": 10, "h-carry": 1}


def test_attempt_count_counts_failures_as_attempts(registry: ExperimentRegistry) -> None:
    """A failure is an attempt. Excluding them is how the denominator lies."""
    _create(registry, "exp-1", hypothesis_id="h-momentum")
    _create(registry, "exp-2", hypothesis_id="h-momentum")
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo too high")
    assert registry.attempt_count()["h-momentum"] == 2


# ══════════════════════════════════════════════════════════════════════════
# The reproducibility hash must not move when the result does
# ══════════════════════════════════════════════════════════════════════════


def test_the_reproducibility_hash_ignores_lineage(registry: ExperimentRegistry) -> None:
    """Lineage is navigational. Hashing it would make identical configurations
    hash differently because of how they were reached rather than what they are."""
    _create(registry, "exp-1")
    _create(registry, "exp-2", parent_id="exp-1")
    assert (
        registry.get("exp-1").reproducibility_hash
        == registry.get("exp-2").reproducibility_hash
    )


def test_the_reproducibility_hash_ignores_the_result(registry: ExperimentRegistry) -> None:
    """A result is an output. Including it would make the hash uncheckable,
    since you would need the result to verify the run that produced it."""
    _create(registry, "exp-1")
    _create(registry, "exp-2")
    registry.start("exp-1", "system")
    registry.complete("exp-1", "system", {"sharpe": 9.9})
    assert (
        registry.get("exp-1").reproducibility_hash
        == registry.get("exp-2").reproducibility_hash
    )


def test_the_reproducibility_hash_still_moves_with_the_configuration(
    registry: ExperimentRegistry,
) -> None:
    """The hash must remain sensitive to what actually determines the run."""
    kernel = create_kernel()
    other = ExperimentRegistry(kernel.state_machine, kernel.provenance)
    _create(registry, "exp-1", hypothesis_id="h")
    other.create(
        experiment_id="exp-1",
        hypothesis_id="h",
        strategy_version="s1",
        dataset_version="d1",
        actor_id="system",
        random_seed=43,
    )
    assert (
        registry.get("exp-1").reproducibility_hash
        != other.get("exp-1").reproducibility_hash
    )


# ══════════════════════════════════════════════════════════════════════════
# Verdicts are frozen onto the run
# ══════════════════════════════════════════════════════════════════════════


def test_a_verdict_is_attached_to_a_completed_run(registry: ExperimentRegistry) -> None:
    """The certification verdict is the most expensive artifact produced."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.complete("exp-1", "system", {"gross_sharpe": 2.1})
    registry.attach_verdict("exp-1", verdict="CERTIFIED", deflated_sharpe=1.98)
    run = registry.get("exp-1")
    assert run.certification_verdict == "CERTIFIED"
    assert run.deflated_sharpe == pytest.approx(1.98)


def test_a_verdict_cannot_be_attached_to_an_unfinished_run(
    registry: ExperimentRegistry,
) -> None:
    """Only a completed run has a result to certify."""
    _create(registry)
    registry.start("exp-1", "system")
    with pytest.raises(ValueError, match="only a completed run"):
        registry.attach_verdict("exp-1", verdict="CERTIFIED")


def test_a_verdict_cannot_be_attached_to_a_failed_run(registry: ExperimentRegistry) -> None:
    """A failed run has no result, and attaching one would invent a history."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "pbo 0.9")
    with pytest.raises(ValueError, match="only a completed run"):
        registry.attach_verdict("exp-1", verdict="CERTIFIED")


def test_a_rejected_verdict_is_recorded_too(registry: ExperimentRegistry) -> None:
    """Recording only the wins is the ledger's original sin."""
    _create(registry)
    registry.start("exp-1", "system")
    registry.complete("exp-1", "system", {"sharpe": 0.2})
    registry.attach_verdict("exp-1", verdict="REJECTED", deflated_sharpe=0.0)
    assert registry.get("exp-1").certification_verdict == "REJECTED"


# ══════════════════════════════════════════════════════════════════════════
# State machine
# ══════════════════════════════════════════════════════════════════════════


def test_a_failed_experiment_cannot_be_restarted(registry: ExperimentRegistry) -> None:
    """Terminal means terminal; a failure cannot be quietly retried in place."""
    from kernel.state_machine import TransitionError

    _create(registry)
    registry.start("exp-1", "system")
    registry.fail("exp-1", "system", "bad fill model")
    with pytest.raises(TransitionError):
        registry.start("exp-1", "system")
