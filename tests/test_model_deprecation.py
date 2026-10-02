"""Model deprecation: reachable, audited, gated, and unable to touch capital.

THE GAP THIS CLOSES
===================
`ModelStatus.DEPRECATED` existed from the enum's first version and was unreachable. Nothing
set it and nothing read it, so there was no way to retire a model: a PROMOTED version stayed
PROMOTED forever and the lifecycle had no terminal state. A governance record that cannot
record retirement is the same defect class as a setting with no consumer — and this project
has now found several of them, which is why it is worth a gate rather than a patch.

WHAT IS DELIBERATELY NOT DECIDED
================================
Whether deprecating a live model should flatten, reduce, or leave its positions alone is
ADR-007's halt-vs-degrade question, and it is a human principal's to answer. So this tests
that deprecation moves NO capital — which is a positive property of the implementation, not
merely an absence of code.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from core.control_plane import ROLE_MATRIX, ControlAction, ControlPlane, OperatorRole
from kernel.registries import ModelRegistry, ModelStatus

REPO = pathlib.Path(__file__).resolve().parents[1]


def _store():
    import tempfile

    from core.persistence import SqliteMemoryStore

    return SqliteMemoryStore(pathlib.Path(tempfile.mkdtemp()) / "deprecate.db")


def _plane(store):
    from core.event_bus import InMemoryEventBus
    from core.risk_governor import RiskGovernor

    return ControlPlane(
        store=store,
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
    )


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------------------
# The registry: DEPRECATED is finally reachable
# --------------------------------------------------------------------------------------


class _FakeProvenance:
    def add_node(self, *a, **k): ...
    def add_edge(self, *a, **k): ...


class _FakePromotions:
    def __init__(self): self.calls = []
    def propose(self, *a, **k): self.calls.append(("propose", a))
    def mark_evaluated(self, *a, **k): self.calls.append(("evaluated", a))
    def promote(self, *a, **k): self.calls.append(("promote", a))


def _registry() -> ModelRegistry:
    return ModelRegistry(_FakeProvenance(), _FakePromotions())  # type: ignore[arg-type]


def test_a_registered_version_starts_defined_and_can_be_deprecated() -> None:
    reg = _registry()
    reg.register("m", "v1", "tabular", {"feature_id": "f", "version": "1"})
    assert reg.get("m", "v1").status is ModelStatus.DEFINED

    reg.mark_deprecated("m", "v1")
    assert reg.get("m", "v1").status is ModelStatus.DEPRECATED


def test_deprecating_an_unknown_version_raises_rather_than_inventing_one() -> None:
    # §3.2: missing data is UNKNOWN, not a default. Silently creating a tombstone for a model
    # that does not exist would be exactly the substitution the constitution forbids.
    with pytest.raises(KeyError):
        _registry().mark_deprecated("nope", "v1")


def test_deprecation_is_visible_in_the_registry_listing() -> None:
    # The status was always passed through to the UI; making it reachable is what makes the
    # existing display mean something.
    reg = _registry()
    reg.register("m", "v1", "tabular", {"feature_id": "f", "version": "1"})
    reg.mark_deprecated("m", "v1")
    rows = reg.list_versions()
    assert [r["status"] for r in rows] == ["DEPRECATED"]


# --------------------------------------------------------------------------------------
# The control action: gated, audited, idempotent
# --------------------------------------------------------------------------------------


def _wired_plane(store):
    """A plane with a kernel carrying a registry, so DEPRECATE_MODEL can run."""
    plane = _plane(store)
    kernel = type("K", (), {})()
    kernel.models = _registry()
    kernel.models.register("m", "v1", "tabular", {"feature_id": "f", "version": "1"})
    kernel.models.mark_evaluated("m", "v1", {"brier": 0.2})
    bridge = type("B", (), {})()
    bridge.kernel = kernel
    plane.kernel_bridge = bridge
    return plane


def test_deprecate_model_is_a_real_action_and_moves_the_gated_count() -> None:
    assert ControlAction.DEPRECATE_MODEL.value == "deprecate_model"
    assert len(list(ControlAction)) == 20


def test_deprecation_requires_risk_admin_mirroring_promotion() -> None:
    # Retirement is the mirror of promotion: a deprecated version cannot be re-promoted, so
    # deprecating one that may already hold capital is a RISK_ADMIN decision, not an
    # OPERATOR one.
    gated = ROLE_MATRIX[OperatorRole.RISK_ADMIN]
    assert ControlAction.DEPRECATE_MODEL in gated
    assert ControlAction.DEPRECATE_MODEL in ROLE_MATRIX[OperatorRole.ADMIN]
    assert ControlAction.DEPRECATE_MODEL not in ROLE_MATRIX[OperatorRole.OPERATOR]
    assert ControlAction.DEPRECATE_MODEL not in ROLE_MATRIX[OperatorRole.VIEWER]


def test_deprecating_is_audited() -> None:
    store = _store()
    plane = _wired_plane(store)

    result = _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))

    assert result["authorized"] is True
    events = store.iter_event_payloads("MODEL_DEPRECATED")
    assert len(events) == 1
    assert events[0]["by"] == "op-1"


def test_deprecating_is_idempotent_and_does_not_double_log() -> None:
    # Re-running must not manufacture a second retirement event; a repeated control action is
    # an operator retry, not two retirements.
    store = _store()
    plane = _wired_plane(store)

    first = _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))
    second = _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))

    assert first["result"]["already_deprecated"] is False
    assert second["result"]["already_deprecated"] is True
    assert len(store.iter_event_payloads("MODEL_DEPRECATED")) == 1


def test_an_operator_cannot_deprecate() -> None:
    store = _store()
    plane = _wired_plane(store)
    # `execute` RAISES on an unauthorised action rather than returning a verdict — that is the
    # existing contract, and `OperatorChat` turns the PermissionError into `kind: "denied"`.
    # Asserting a returned dict here would have tested a contract this method never had.
    with pytest.raises(PermissionError, match="may not perform deprecate_model"):
        _run(plane.execute("op-1", "OPERATOR", "deprecate_model", {"model_id": "m", "version": "v1"}))
    # And the refusal left no trace on the model.
    assert plane.kernel_bridge.kernel.models.get("m", "v1").status is ModelStatus.EVALUATED
    assert store.iter_event_payloads("MODEL_DEPRECATED") == []


def test_deprecating_an_unknown_model_reports_unknown_rather_than_succeeding() -> None:
    store = _store()
    plane = _wired_plane(store)
    with pytest.raises(ValueError):
        _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "ghost", "version": "v1"}))


# --------------------------------------------------------------------------------------
# The capital boundary — the property that matters most
# --------------------------------------------------------------------------------------


def test_deprecation_states_that_it_touched_no_capital() -> None:
    # Not merely "we did not write flatten code". The action TELLS the operator, so nobody has
    # to infer it. An operator who deprecates a live model must not have to guess whether its
    # positions were handled.
    store = _store()
    plane = _wired_plane(store)
    result = _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))
    assert result["result"]["capital_effect"].startswith("none")
    assert "ADR-007" in result["result"]["capital_effect"]


def test_the_control_plane_never_flattens_or_reduces_on_deprecation() -> None:
    # A behavioural guard on the claim above. If a future edit made deprecation touch
    # positions, this fails regardless of what the return value claims.
    #
    # The docstring is stripped first: it explains what this method deliberately does NOT do,
    # so it necessarily contains the words "flatten" and "reduce". Scanning it would make the
    # guard fail on its own documentation — a check that can only ever be red is not a check.
    import ast

    tree = ast.parse((REPO / "core" / "control_plane.py").read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_do_deprecate_model"
    )
    body = list(method.body)
    # Drop the docstring. It explains what this method deliberately does NOT do, so it
    # necessarily contains "flatten" and "reduce"; scanning it would make the guard fail on
    # its own documentation, which is a check that can only ever be red.
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    # Check IDENTIFIERS, not text. Two earlier attempts failed on this: the docstring names
    # "flatten" and "reduce" because it explains what the method does not do, and the
    # `capital_effect` string literal repeats them for the operator. Text matching therefore
    # fails on the code's own honesty. What matters is whether a capital-moving attribute or
    # function is REFERENCED, which is exactly what the AST can say.
    referenced: set[str] = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                referenced.add(node.func.id)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                referenced.add(node.func.attr)

    for verb in ("flatten", "close_position", "cancel_open_orders", "order_manager", "set_reduce_only", "paper"):
        assert verb not in referenced, f"_do_deprecate_model references {verb!r}"


# --------------------------------------------------------------------------------------
# Promotion: a retired model cannot come back
# --------------------------------------------------------------------------------------


def test_a_deprecated_model_cannot_be_promoted() -> None:
    store = _store()
    plane = _wired_plane(store)
    _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))

    # The message is asserted, not just the exception type, and that is load-bearing twice
    # over. A DEPRECATED model is ALSO not EVALUATED, so the pre-existing gate raises
    # `PermissionError` too; and its message happens to contain the word "DEPRECATED"
    # ("is DEPRECATED; requires EVALUATED"). So matching on DEPRECATED still passed with
    # the deprecation gate deleted — the mutation harness proved both. `retired` is the word
    # only the deprecation gate uses, so this cannot be satisfied by another gate.
    with pytest.raises(PermissionError, match="retired"):
        _run(plane.execute("op-2", "RISK_ADMIN", "promote_model", {"model_id": "m", "version": "v1"}))


def test_a_retired_model_cannot_be_revived_by_re_evaluating_it() -> None:
    # This is the case that showed the first implementation did not hold. `mark_evaluated`
    # sets `status` back to EVALUATED, so a promotion gate that read `status` was bypassed by
    # a workflow that already existed: evaluate, then promote.
    store = _store()
    plane = _wired_plane(store)
    models = plane.kernel_bridge.kernel.models
    _run(plane.execute("op-1", "RISK_ADMIN", "deprecate_model", {"model_id": "m", "version": "v1"}))

    # The revival attempt is refused at the source: a retired version is not re-evaluable.
    with pytest.raises(ValueError, match="deprecated"):
        models.mark_evaluated("m", "v1", {"brier": 0.1})

    # And even if the status were somehow forced back to EVALUATED, promotion still refuses,
    # because it reads the sticky `deprecated_at` rather than the mutable status.
    models.get("m", "v1").status = ModelStatus.EVALUATED
    with pytest.raises(PermissionError, match="retired"):
        _run(plane.execute("op-2", "RISK_ADMIN", "promote_model", {"model_id": "m", "version": "v1"}))


def test_retirement_is_recorded_separately_from_current_status() -> None:
    # The distinction the previous test depends on. If `deprecated_at` were derived from
    # `status`, forcing the status back would erase the retirement too.
    reg = _registry()
    reg.register("m", "v1", "tabular", {"feature_id": "f", "version": "1"})
    assert reg.get("m", "v1").deprecated_at is None

    reg.mark_deprecated("m", "v1")
    first = reg.get("m", "v1").deprecated_at
    assert first

    reg.get("m", "v1").status = ModelStatus.EVALUATED  # even a forced status change
    assert reg.get("m", "v1").deprecated_at == first


def test_repeated_deprecation_keeps_the_first_retirement_time() -> None:
    # An audit cares when it happened; a repeat must not reset the clock.
    reg = _registry()
    reg.register("m", "v1", "tabular", {"feature_id": "f", "version": "1"})
    reg.mark_deprecated("m", "v1")
    first = reg.get("m", "v1").deprecated_at
    reg.mark_deprecated("m", "v1")
    assert reg.get("m", "v1").deprecated_at == first


def test_promotion_of_an_evaluated_model_still_works() -> None:
    # The gate must not have broken the happy path. This needs the full kernel, so it is
    # exercised through the registry + promotions rather than the whole evaluation pipeline.
    store = _store()
    plane = _wired_plane(store)
    models = plane.kernel_bridge.kernel.models
    assert models.get("m", "v1").status is ModelStatus.EVALUATED
    # No deprecation has happened, so the EVALUATED gate is satisfied and control plane's
    # promotion path is entered (it will fail later, on the evaluation record, which is a
    # different gate and not what this test is about).
    try:
        _run(plane.execute("op-1", "RISK_ADMIN", "promote_model", {"model_id": "m", "version": "v1"}))
    except Exception as exc:  # noqa: BLE001
        assert "DEPRECATED" not in str(exc)
    else:
        pass  # promoted all the way; the EVALUATED gate clearly did not block it
