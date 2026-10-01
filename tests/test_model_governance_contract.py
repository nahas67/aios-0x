"""The model-governance contract between the backend and the registry view.

`SystemSnapshotBuilder.models_registry_view` is what
`frontend/src/components/views/ModelGovernanceWorkspace.tsx` reads. That view
used to render four invented models, weights hashes, latency figures and a
"92.6% AVERAGE" benchmark accuracy while calling no endpoint at all, so the
backend's honesty was never exercised and never noticed.

The view has been rewritten to render this endpoint. That is only safe while the
endpoint keeps its side of the bargain, which is what these tests pin:

  - absence is answered as absence, never as a placeholder roster;
  - a failing registry reports its reason rather than being swallowed;
  - a real roster passes through with its metrics intact.

The failure this guards against is specific and plausible. Someone wanting the
view to "look populated" on a fresh deployment would find it tempting to return
a demo roster from the endpoint, and every honesty assertion in the frontend
would then pass while rendering the fiction. The backend is the only place that
can be lied in, so the backend is where the test belongs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from api.views import SystemSnapshotBuilder
from core.persistence import SqliteMemoryStore


@pytest.fixture
def builder(tmp_path: Path) -> SystemSnapshotBuilder:
    return SystemSnapshotBuilder(SqliteMemoryStore(tmp_path / "probe.db"))


def _bridge(registry: Any) -> Any:
    """A kernel bridge exposing `kernel.models = registry`."""

    class _Kernel:
        models = registry

    class _Bridge:
        kernel = _Kernel()

    return _Bridge()


class _RegistryWithVersions:
    def list_versions(self) -> list[dict[str, Any]]:
        return [
            {
                "model_id": "probe-model",
                "version": "1",
                "status": "CERTIFIED",
                "model_type": "direction",
                "artifact_hash": "sha256:probe",
                "created_at": "2026-10-01T00:00:00+00:00",
                "evaluation_metrics": {"accepted_n": 120},
            }
        ]


class _ExplodingRegistry:
    def list_versions(self) -> list[dict[str, Any]]:
        raise RuntimeError("registry offline")


def test_absence_is_answered_as_absence(builder: SystemSnapshotBuilder) -> None:
    """No kernel bridge is the common case on a plain deployment.

    The docstring already promises "never a fabricated roster"; this makes the
    promise executable.
    """
    payload = builder.models_registry_view()

    assert payload["available"] is False
    assert payload["models"] == []
    # Absence must not invent a reason either -- there was no failure to report.
    assert "reason" not in payload


def test_a_kernel_without_a_model_registry_is_absence(
    builder: SystemSnapshotBuilder,
) -> None:
    builder.kernel_bridge = _bridge(None)

    payload = builder.models_registry_view()

    assert payload["available"] is False
    assert payload["models"] == []


def test_a_failing_registry_reports_its_reason(
    builder: SystemSnapshotBuilder,
) -> None:
    """Swallowing the failure would leave the view unable to say what is wrong,
    which is the one case where a reason is genuinely owed."""
    builder.kernel_bridge = _bridge(_ExplodingRegistry())

    payload = builder.models_registry_view()

    assert payload["available"] is False
    assert payload["models"] == []
    assert payload["reason"] == "registry offline"


def test_a_real_roster_passes_through_with_its_metrics(
    builder: SystemSnapshotBuilder,
) -> None:
    """`evaluation_metrics` is the field the statistical claim gate reads, so it
    has to survive the reshape. Losing it here would make every claim in the
    view permanently NOT REPORTABLE for a reason that looks like honesty."""
    builder.kernel_bridge = _bridge(_RegistryWithVersions())

    payload = builder.models_registry_view()

    assert payload["available"] is True
    assert len(payload["models"]) == 1
    model = payload["models"][0]
    assert model["id"] == "probe-model@1"
    assert model["name"] == "probe-model"
    assert model["status"] == "CERTIFIED"
    assert model["artifact_hash"] == "sha256:probe"
    assert model["evaluation_metrics"] == {"accepted_n": 120}


def test_no_shape_ever_returns_a_roster_while_reporting_absence(
    builder: SystemSnapshotBuilder,
) -> None:
    """The invariant, stated over every branch rather than per-case.

    Written as a sweep so a future branch added to `models_registry_view`
    inherits the check instead of needing a new test written for it.
    """
    builders: list[SystemSnapshotBuilder] = [builder]
    for registry in (None, _ExplodingRegistry()):
        other = SystemSnapshotBuilder(
            SqliteMemoryStore(Path(tempfile.gettempdir()) / "contract_probe.db")
        )
        other.kernel_bridge = _bridge(registry)
        builders.append(other)

    for candidate in builders:
        payload = candidate.models_registry_view()
        if payload["available"] is False:
            assert payload["models"] == [], (
                "an endpoint reporting absence must not also ship a roster: "
                f"got {payload!r}"
            )
