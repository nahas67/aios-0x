"""Capability Model: AIOS owns capabilities; OSS provides implementations.

The capability router resolves a named capability (e.g. AIOS.backtest) to a
registered implementation. Implementations are versioned and swappable without
changing callers. This is what prevents OSS lock-in at the platform level.
"""

from abc import ABC
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CapabilitySpec(BaseModel):
    """Declares a named capability with its interface contract."""

    name: str = Field(..., min_length=1, description="e.g. 'AIOS.backtest'")
    version: str = "v1"
    description: str = ""
    interface: type  # The ABC that implementations must satisfy


class CapabilityRegistration(BaseModel):
    """A registered implementation of a capability."""

    spec: CapabilitySpec
    implementation_id: str
    implementation: Any  # The actual class/instance
    is_default: bool = False


class CapabilityRouter:
    """Resolves named capabilities to registered implementations.

    Callers request capabilities by name. The router returns the registered
    implementation (default or explicitly requested). This is what prevents
    lock-in: swapping implementations doesn't change callers.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilitySpec] = {}
        self._implementations: dict[str, dict[str, Any]] = {}
        self._defaults: dict[str, str] = {}

    def declare(
        self, name: str, interface: type, description: str = "", version: str = "v1"
    ) -> None:
        """Declare a capability with its interface contract."""
        if name in self._capabilities:
            raise ValueError(f"capability already declared: {name!r}")
        if not (isinstance(interface, type) and issubclass(interface, ABC)):
            raise TypeError(f"interface must be an ABC subclass, got {interface}")
        self._capabilities[name] = CapabilitySpec(
            name=name, version=version, description=description, interface=interface
        )

    def register(
        self, name: str, implementation_id: str, implementation: Any, is_default: bool = False
    ) -> None:
        """Register an implementation for a declared capability."""
        spec = self._capabilities.get(name)
        if spec is None:
            raise ValueError(f"capability not declared: {name!r}")
        if not (isinstance(implementation, type) and issubclass(implementation, spec.interface)):
            raise TypeError(
                f"implementation must implement {spec.interface.__name__}, "
                f"got {type(implementation)}"
            )
        self._implementations.setdefault(name, {})[implementation_id] = implementation
        if is_default or name not in self._defaults:
            self._defaults[name] = implementation_id

    def is_declared(self, name: str) -> bool:
        return name in self._capabilities

    def resolve(self, name: str, implementation_id: str | None = None) -> Any:
        """Resolve a capability to its implementation (class or instance)."""
        if name not in self._capabilities:
            raise ValueError(f"capability not declared: {name!r}")
        impls = self._implementations.get(name)
        if not impls:
            raise ValueError(f"no implementations registered for {name!r}")
        impl_id = implementation_id or self._defaults.get(name)
        if impl_id is None or impl_id not in impls:
            raise ValueError(
                f"implementation {impl_id!r} not found for {name!r}; "
                f"available: {sorted(impls.keys())}"
            )
        return impls[impl_id]

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "version": spec.version,
                "description": spec.description,
                "interface": spec.interface.__name__,
                "implementations": sorted(self._implementations.get(spec.name, {}).keys()),
                "default": self._defaults.get(spec.name),
            }
            for spec in self._capabilities.values()
        ]
