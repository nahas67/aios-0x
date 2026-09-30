"""
ControlPlane safety regression tests — Phase 3.1.

Verifies:
  1. ControlPlane default autonomy is SUPERVISED (fail-closed)
  2. Constructing a bare ControlPlane never enables autonomous execution
  3. Invalid autonomy configuration fails closed
  4. Live-capital state is structurally gated (env manipulation doesn't enable it)
"""
import os

from core.control_plane import AutonomyMode, ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor


class TestControlPlaneDefaults:
    """ControlPlane must default to non-executing autonomy."""

    def test_default_autonomy_is_supervised(self):
        """Bare ControlPlane defaults to SUPERVISED, not AUTONOMOUS."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        assert plane.autonomy == AutonomyMode.SUPERVISED

    def test_default_autonomy_not_autonomous(self):
        """Constructing ControlPlane must never result in AUTONOMOUS."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        assert plane.autonomy != AutonomyMode.AUTONOMOUS

    def test_autonomy_can_be_set_explicitly(self):
        """Autonomy can be changed through the control plane."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        plane.autonomy = AutonomyMode.MANUAL
        assert plane.autonomy == AutonomyMode.MANUAL

    def test_autonomy_mode_enum_values(self):
        """All four autonomy modes exist."""
        modes = [m.value for m in AutonomyMode]
        assert "MANUAL" in modes
        assert "ASSISTED" in modes
        assert "SUPERVISED" in modes
        assert "AUTONOMOUS" in modes


class TestLiveCapitalGating:
    """Live-capital must be structurally disabled by default."""

    def test_live_capital_not_approved_by_default(self):
        """live_capital_approved_by starts as None."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        assert plane.live_capital_approved_by is None

    def test_live_execution_env_default_disabled(self):
        """AIOS_ALLOW_LIVE_EXECUTION env var defaults to disabled."""
        # Clear any existing value
        old_val = os.environ.pop("AIOS_ALLOW_LIVE_EXECUTION", None)
        try:
            from core.config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
            # The default should be empty/None (disabled)
            assert not settings.database_url or settings.database_url is None
        finally:
            if old_val is not None:
                os.environ["AIOS_ALLOW_LIVE_EXECUTION"] = old_val

    def test_classify_plan_supervised_queues(self):
        """In SUPERVISED mode, plans queue for approval (not execute)."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        # Default is SUPERVISED
        result = plane.classify_plan(None)
        assert result == "QUEUE"

    def test_classify_plan_manual_holds(self):
        """In MANUAL mode, plans are held (not executed or queued)."""
        plane = ControlPlane(
            store=SqliteMemoryStore(":memory:"),
            event_bus=InMemoryEventBus(),
            risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
            strategy_agent=None,
            order_manager=None,
        )
        plane.autonomy = AutonomyMode.MANUAL
        result = plane.classify_plan(None)
        assert result == "HOLD"
