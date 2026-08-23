"""SYSTEM CONSTITUTION integrity enforcement.

The constitution file is pinned by SHA-256. Every runner boot verifies the
on-disk file against the pin; a mismatch raises ConstitutionViolationError
and the system refuses to operate until a human resolves the discrepancy
(amendment procedure: CONSTITUTION.md section 4).
"""

import hashlib
from pathlib import Path

CONSTITUTION_PATH = Path(__file__).resolve().parents[1] / "CONSTITUTION.md"

# Pinned at ratification of v1.0.0 (2026-08-23). Update ONLY together with a
# ratified amendment ADR in the same commit (procedure: CONSTITUTION.md §4).
_PINNED_SHA256 = "310bc83f61c8876291c740311f06cacaf4bbccac49d42f0fbb4f2a54faca563c"


def compute_sha256(path: str | Path = CONSTITUTION_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path: str | Path = CONSTITUTION_PATH, pinned: str | None = None) -> bool:
    expected = pinned if pinned is not None else _PINNED_SHA256
    return compute_sha256(path) == expected


class ConstitutionViolationError(RuntimeError):
    """Raised when the on-disk constitution does not match the pinned hash."""


def enforce_at_boot(path: str | Path = CONSTITUTION_PATH) -> str:
    """Verify and return the current hash; raise on any mismatch."""
    current = compute_sha256(path)
    if not _PINNED_SHA256:
        # First-boot bootstrap: accept and instruct pinning (dev convenience),
        # but make the gap loud - this must never silently pass in production.
        raise ConstitutionViolationError(
            "constitution pin is EMPTY; run scripts/pin_constitution.py after "
            "ratifying the document, then commit the pin"
        )
    if current != _PINNED_SHA256:
        raise ConstitutionViolationError(
            f"CONSTITUTION MISMATCH: on-disk sha256={current} != pinned {_PINNED_SHA256}. "
            "System refuses to start. Resolve via amendment procedure (§4)."
        )
    return current
