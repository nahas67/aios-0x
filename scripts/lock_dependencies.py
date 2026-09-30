"""Generate the reproducible dependency lock from pyproject.toml.

`pyproject.toml` is the ONE authoritative dependency model. This script derives
`requirements.lock` from the *installed* versions of the project's own dependency
closure, so a deployment can be reproduced exactly without a second hand-written
list drifting away from the first.

Resolution is offline and deterministic: it walks `importlib.metadata` starting
from the requirement names declared in pyproject (including the selected extras)
and records the installed version of every distribution reachable that way.
Unrelated packages that happen to live in the same environment are deliberately
excluded — a lock file that contains a developer's personal tooling is not
reproducible anywhere else.

    python scripts/lock_dependencies.py            # write requirements.lock
    python scripts/lock_dependencies.py --check    # fail if the lock is stale

`--check` is what CI runs: a dependency that changes without the lock being
regenerated is a build failure, not a deploy-time surprise.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "requirements.lock"

#: Extras locked by default: everything a production or verification run needs.
DEFAULT_EXTRAS = ("dev", "postgres", "nats", "ccxt")

HEADER = (
    "# GENERATED FILE - do not edit by hand.\n"
    "# Source of truth: pyproject.toml. Regenerate with:\n"
    "#     python scripts/lock_dependencies.py\n"
    "# Contains ONLY this project's resolved dependency closure.\n"
)

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def requirement_name(spec: str) -> str | None:
    """Extract the distribution name from a PEP 508 requirement string."""
    match = _NAME.match(spec)
    return match.group(1) if match else None


def declared_requirements(extras: tuple[str, ...]) -> list[str]:
    """Root distribution names taken from pyproject (selected extras included).

    A root that requests extra packages (``psycopg[binary]``) also contributes
    the extra-providing distribution as a root, since the extra lives in OUR
    declaration rather than in the dependency's own marker set.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for extra in extras:
        specs.extend(optional.get(extra, []))

    names: set[str] = set()
    for spec in specs:
        base = requirement_name(spec)
        if not base:
            continue
        names.add(base)
        try:
            requirement = Requirement(spec)
        except Exception:  # noqa: BLE001 - unparseable spec contributes only its name
            continue
        for extra_name in requirement.extras:
            names.add(f"{base}-{extra_name}")
    return sorted(names, key=str.lower)


def _is_base_dependency(spec: str) -> str | None:
    """Name of a NON-extra dependency, or None when it is extra/marker-gated out.

    Environment markers are evaluated with ``extra`` unset, so a package needed
    only for somebody's `[dev]` extra (or for another platform) is excluded. A
    lock that lists packages this environment would never install is not a lock.
    """
    try:
        requirement = Requirement(spec)
    except Exception:  # noqa: BLE001 - an unparseable requirement is skipped
        return None
    if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
        return None
    return requirement.name


def resolve_closure(roots: list[str]) -> tuple[list[str], list[str]]:
    """BFS over installed metadata; returns (locked lines, missing names)."""
    installed: dict[str, tuple[str, tuple[str, ...]]] = {}
    for dist in md.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        key = name.lower().replace("_", "-")
        installed[key] = (f"{name}=={dist.version}", tuple(dist.requires or []))

    seen: set[str] = set()
    missing: list[str] = []
    queue = [name.lower().replace("_", "-") for name in roots]
    locked: set[str] = set()
    while queue:
        key = queue.pop()
        if key in seen:
            continue
        seen.add(key)
        entry = installed.get(key)
        if entry is None:
            missing.append(key)
            continue
        line, requires = entry
        locked.add(line)
        for spec in requires:
            dep = _is_base_dependency(spec)
            if dep:
                queue.append(dep.lower().replace("_", "-"))
    return sorted(locked, key=str.lower), sorted(missing)


def render(packages: list[str], digest: str, extras: tuple[str, ...]) -> str:
    return (
        f"{HEADER}# extras: {','.join(extras)}\n"
        f"# resolved-digest: {digest}\n" + "\n".join(packages) + "\n"
    )


def digest_of(packages: list[str]) -> str:
    return hashlib.sha256("\n".join(packages).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the lock is current")
    parser.add_argument(
        "--extras",
        default=",".join(DEFAULT_EXTRAS),
        help=f"comma-separated extras to lock (default: {','.join(DEFAULT_EXTRAS)})",
    )
    args = parser.parse_args(argv)

    extras = tuple(e.strip() for e in args.extras.split(",") if e.strip())
    roots = declared_requirements(extras)
    packages, missing = resolve_closure(roots)
    digest = digest_of(packages)
    expected = render(packages, digest, extras)

    if args.check:
        if not LOCK.exists():
            print("requirements.lock is missing; run scripts/lock_dependencies.py")
            return 1
        if LOCK.read_text(encoding="utf-8") != expected:
            print("requirements.lock is stale; regenerate it")
            return 1
        print(f"requirements.lock is current ({len(packages)} package(s), {digest[:12]})")
        return 0

    LOCK.write_text(expected, encoding="utf-8")
    print(f"wrote {LOCK.name}: {len(packages)} package(s), digest {digest[:12]}")
    if missing:
        # Not an error: an optional extra may legitimately be absent locally.
        print(f"not installed locally (excluded): {', '.join(missing)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
