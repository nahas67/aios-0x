"""Fail-closed local pre-production validation.

This command performs only local checks. It never contacts a broker, creates an
account, sends an order, or reads secret values. A non-zero exit means the
artifact must not be promoted.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MODULES = (
    "aios",
    "api",
    "communities",
    "core",
    "evaluation",
    "kernel",
    "research",
    "schemas",
    "simulation",
)
REQUIRED_FILES = ("Dockerfile", "docker-compose.yml", ".env.example", "CONSTITUTION.md")


def _check(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return condition


def main() -> int:
    failures = 0

    from core.constitution import verify

    failures += not _check("constitution", verify(), "pinned hash matches CONSTITUTION.md")

    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
            ok = True
            detail = "importable"
        except Exception as exc:  # noqa: BLE001 - checker must report all failures
            ok = False
            detail = f"{type(exc).__name__}: {exc}"
        failures += not _check(f"module:{module}", ok, detail)

    for filename in REQUIRED_FILES:
        failures += not _check(
            f"file:{filename}",
            (ROOT / filename).is_file(),
            "present in repository",
        )

    autonomy = os.environ.get("AUTONOMY_MODE", "SUPERVISED").upper()
    failures += not _check(
        "autonomy",
        autonomy in {"MANUAL", "ASSISTED", "SUPERVISED"},
        f"{autonomy}; autonomous mode requires an explicit operator action",
    )

    live = os.environ.get("AIOS_ALLOW_LIVE_EXECUTION", "").lower()
    failures += not _check(
        "live-execution-default",
        live not in {"1", "true", "yes", "on"},
        "live execution is disabled in the validation environment",
    )

    print("PRE-PRODUCTION CHECK: " + ("PASS" if failures == 0 else "FAIL"))
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
