"""Generate the reproducible dependency lock from pyproject.toml.

`pyproject.toml` is the ONE authoritative dependency model. This script derives
`requirements.lock` from the *installed* versions of the project's own dependency
closure, so a deployment can be reproduced exactly without a second hand-written
list drifting away from the first.

Resolution is offline and deterministic: it walks `importlib.metadata` starting
from the requirement names declared in pyproject (including the selected extras)
and records the installed version of every distribution reachable that way.
Unrelated packages that happen to live in the same environment are deliberately
excluded -- a lock file that contains a developer's personal tooling is not
reproducible anywhere else.

    python scripts/lock_dependencies.py                   # write requirements.lock
    python scripts/lock_dependencies.py --check           # the CI gate
    python scripts/lock_dependencies.py --check-installed # local drift report

WHAT `--check` VERIFIES, AND WHY IT IS NOT WHAT IT WAS

It used to compare the committed lock against a closure recomputed from
`importlib.metadata` -- that is, it asserted "the versions pip resolved on the
machine that generated the lock equal the versions in the lock". CI installs
whatever pip resolves *today* and then ran that comparison, so the gate could only
ever pass on one machine, and it began failing the moment any package in the closure
published a release. It was left failing for exactly that reason, and the one word
it printed gave nobody anything to act on.

It now verifies the lock against `pyproject.toml`, which is the declared source of
truth and does not vary by machine:

  1. every distribution pyproject declares is present in the lock;
  2. every locked version satisfies the specifier pyproject declares for it;
  3. every line is pinned with a double-equals version;
  4. no package appears twice;
  5. the resolved-digest line matches the digest of the package lines, so a
     hand-edited lock is caught;
  6. the extras line names the extras that were requested.

(2) is the one the old gate could not do at all: it asked only whether the lock
matched what was installed, so a lock pinning a version pyproject FORBIDS passed as
long as that version happened to be installed. (3), (4) and (6) are new.

NOT CHECKED -- ALL THREE NARROWINGS, FOUND BY REVIEW

1. COMPLETENESS of the transitive closure. Whether every reachable dependency is in
   the lock cannot be verified without the metadata of the packages in it, which is
   exactly the environment dependence this rewrite removes. A lock missing a
   transitive dependency therefore passes.

2. ADDED PACKAGES. The old gate was a byte-compare against a closure recomputed from
   the environment, so anything in the lock that no root reached was caught. That is
   no longer checked: inserting a distribution this project never asked for, with a
   correct digest, produces no problems.

3. TRANSITIVE VERSION AUTHENTICITY. A version can only be checked against a range
   pyproject states, and pyproject states ranges for 11 of the 52 locked packages.
   The other 41 -- 79% of the lock -- have no version anchor at all, so a
   `cryptography==3.0.1` passes despite known CVEs. This is inherent to a lock whose
   authority is a manifest that does not mention those packages, not a defect
   specific to this implementation.

Each of the three was disclosed by an independent review of the previous version, and
the first is the one I had written down -- which is the reason all three are here now.
A gate whose real scope is wider than what it checks is read as assurance it does not
provide, and a partial list is worse than none, because it reads as complete.

BLAST RADIUS, STATED PRECISELY

Nothing installs from `requirements.lock` in CI or in the Dockerfile: pyproject is
what gets installed, and the lock is derived from it. So the live exposure of
narrowings 1-3 is the SBOM and audit surface -- `sbom.parse_lock` certifies exactly
this file, and a package it should not have listed would be certified as part of the
build. That is a fact about the current shape of the build rather than a property of
the lock file, and it is labelled as such so nobody reads it as a guarantee that stops
applying the moment an installer is added.

WHY BOTH MODES EXIST

`--check-installed` keeps the environment comparison, because "does my environment
match the lock?" is a real question. It is simply not a CI gate: asking it in CI
asserts that one machine's resolution reproduces everywhere. It reports drift rather
than failing on it, so a local run says what changed instead of demanding a
regeneration."""

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


def parse_lock(text: str) -> tuple[list[str], str | None, str | None]:
    """Split a lock file into (package lines, extras header, digest header).

    Refuses anything it cannot read unambiguously. A lock this function silently
    misparses would produce a verdict about a file nobody wrote -- the failure mode
    is a gate that passes, which is worse than one that fails noisily.
    """
    lines: list[str] = []
    extras: str | None = None
    digest: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("# extras:"):
                extras = line[len("# extras:"):].strip()
            elif line.startswith("# resolved-digest:"):
                digest = line[len("# resolved-digest:"):].strip()
            continue
        if "==" not in line:
            raise ValueError(f"unpinned lock entry: {line!r}")
        lines.append(line)
    return lines, extras, digest


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_specifiers(
    extras: tuple[str, ...],
) -> dict[str, list[str]]:
    """Distribution name -> the requirement strings pyproject declares for it.

    Keyed by normalized name so `PyJWT`, `pyjwt` and `py_jwt` are one entry; a
    lookup that missed those would report a satisfied dependency as absent.

    An extras-PROVIDING distribution (`psycopg-binary`, from `psycopg[binary]`) is
    included as a key with an EMPTY list, which means "must be present, no range
    declared". It was missing entirely before an independent review pointed out
    that `--check` passed with `psycopg-binary` deleted from the lock: generation
    resolved extras via `declared_requirements`, but this function -- which drives
    the presence and specifier checks -- recorded only `requirement.name`. The two
    halves of this module disagreed about what pyproject declares and the gate
    consulted only one.

    The empty list is not a shortcut. pyproject states a range for the package
    carrying the extra and none for the distribution providing it, so the two
    obligations differ. Inheriting the parent's range would invent a constraint
    pyproject does not declare, and would pass a psycopg-binary incompatible with
    the psycopg beside it -- a false assurance manufactured by the check itself.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for extra in extras:
        specs.extend(optional.get(extra, []))

    table: dict[str, list[str]] = {}
    for spec in specs:
        try:
            requirement = Requirement(spec)
        except Exception:  # noqa: BLE001 - an unparseable spec keeps its name only
            base = requirement_name(spec)
            if base:
                table.setdefault(_normalize(base), []).append(spec)
            continue
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        table.setdefault(_normalize(requirement.name), []).append(spec)
        # The extra's PROVIDING distribution, if it is not already a declared
        # dependency in its own right. Presence is required; no range is invented.
        for extra_name in requirement.extras:
            table.setdefault(_normalize(f"{requirement.name}-{extra_name}"), [])
    return table


def verify_lock(
    lines: list[str],
    extras_header: str | None,
    digest_header: str | None,
    extras: tuple[str, ...],
) -> list[str]:
    """Every reason the lock does not match pyproject, or [] if it does.

    Returns ALL problems rather than the first, because a contributor fixing a
    lock should see the whole list once. The old gate reported only "stale", which
    is what made this file unreadable when it started failing.
    """
    problems: list[str] = []

    # (4) no duplicates
    seen: dict[str, int] = {}
    for line in lines:
        name = _normalize(line.split("==", 1)[0])
        seen[name] = seen.get(name, 0) + 1
    for name, count in sorted(seen.items()):
        if count > 1:
            problems.append(f"{name} appears {count} times; a lock lists each package once")

    # (1) and (2) every declared dependency present, at a satisfying version
    locked = {_normalize(line.split("==", 1)[0]): line.split("==", 1)[1] for line in lines}
    for name, specs in sorted(declared_specifiers(extras).items()):
        version = locked.get(name)
        if version is None:
            problems.append(f"{name} is declared in pyproject but absent from the lock")
            continue
        if not specs:
            # An extras provider: required to be present, with no declared range.
            # The presence check above already ran, so this is complete.
            continue
        try:
            requirement = Requirement(specs[0])
        except Exception:  # noqa: BLE001 - name-only entries cannot be range-checked
            continue
        if requirement.specifier and not requirement.specifier.contains(
            version, prereleases=True
        ):
            wanted = ", ".join(specs)
            problems.append(
                f"{name}=={version} does not satisfy pyproject ({wanted}); "
                "the lock and the declaration disagree"
            )

    # (5) the digest must match the lines it claims to cover
    if digest_header is None:
        problems.append("the lock has no # resolved-digest line")
    else:
        actual = digest_of(sorted(lines, key=str.lower))
        if actual != digest_header:
            problems.append(
                "the resolved-digest does not match the package lines; the lock "
                "was edited without being regenerated"
            )

    # (6) the extras header must name what was requested
    if extras_header is None:
        problems.append("the lock has no # extras line")
    elif tuple(e.strip() for e in extras_header.split(",") if e.strip()) != tuple(extras):
        problems.append(
            f"the lock was generated for extras {extras_header!r}, not "
            f"{','.join(extras)!r}"
        )

    return problems


def render(packages: list[str], digest: str, extras: tuple[str, ...]) -> str:
    return (
        f"{HEADER}# extras: {','.join(extras)}\n"
        f"# resolved-digest: {digest}\n" + "\n".join(packages) + "\n"
    )


def digest_of(packages: list[str]) -> str:
    return hashlib.sha256("\n".join(packages).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the lock agrees with pyproject (environment-independent; this is the CI gate)",
    )
    parser.add_argument(
        "--check-installed",
        action="store_true",
        help="report how this environment's installed versions differ from the lock",
    )
    parser.add_argument(
        "--extras",
        default=",".join(DEFAULT_EXTRAS),
        help=f"comma-separated extras to lock (default: {','.join(DEFAULT_EXTRAS)})",
    )
    args = parser.parse_args(argv)

    extras = tuple(e.strip() for e in args.extras.split(",") if e.strip())

    if args.check:
        # The environment-independent gate: pyproject is the declared source of
        # truth, and this check must give the same verdict on every machine.
        if not LOCK.exists():
            print("requirements.lock is missing; run scripts/lock_dependencies.py")
            return 1
        try:
            lines, extras_header, digest_header = parse_lock(
                LOCK.read_text(encoding="utf-8")
            )
        except ValueError as exc:
            print(f"requirements.lock is not readable: {exc}")
            return 1
        problems = verify_lock(lines, extras_header, digest_header, extras)
        if problems:
            print(f"requirements.lock does not match pyproject ({len(problems)}):")
            for problem in problems:
                print(f"  - {problem}")
            print("  regenerate it: python scripts/lock_dependencies.py")
            return 1
        print(
            f"requirements.lock agrees with pyproject ({len(lines)} package(s), "
            f"digest {(digest_header or '')[:12]})"
        )
        return 0

    roots = declared_requirements(extras)
    packages, missing = resolve_closure(roots)
    digest = digest_of(packages)
    expected = render(packages, digest, extras)

    if args.check_installed:
        # Kept, and kept separate. "Does my environment match the lock?" is a real
        # question, but it is not a CI gate: CI installs whatever pip resolves
        # today, so asking it there asserts that one machine's resolution
        # reproduces everywhere. Drift is reported, not failed on -- a local run
        # should tell you what changed, not demand a regeneration.
        if not LOCK.exists():
            print("requirements.lock is missing; run scripts/lock_dependencies.py")
            return 1
        try:
            lines, _, _ = parse_lock(LOCK.read_text(encoding="utf-8"))
        except ValueError as exc:
            # A flag whose contract is "report, do not fail" must not raise. An
            # unpinned entry is a fact about the lock worth reporting, not a
            # reason to hand the caller a traceback; `--check` is the flag that
            # refuses it.
            print(f"the lock is not readable: {exc}")
            print("  --check will refuse it; --check-installed only reports")
            return 0
        locked = {
            _normalize(line.split("==", 1)[0]): line.split("==", 1)[1]
            for line in lines
        }
        here = {line.split("==", 1)[0].lower(): line.split("==", 1)[1] for line in packages}
        drifted = [
            f"{name}: locked {locked[name]} installed {here[name]}"
            for name in sorted(set(locked) & set(here))
            if locked[name] != here[name]
        ]
        absent = sorted(set(locked) - set(here))
        present = sorted(set(here) - set(locked))
        if drifted or absent or present:
            print(f"environment differs from the lock ({len(drifted)} version(s)):")
            for line in drifted:
                print(f"  - {line}")
            for name in absent:
                print(f"  - {name} is locked but not installed here")
            for name in present:
                print(f"  - {name} is installed here but not locked")
            if missing:
                print(f"  not installed locally: {', '.join(missing)}")
            print("  this is drift, not a lock failure -- `--check` is the gate")
            return 0
        print(f"environment matches the lock ({len(locked)} package(s))")
        return 0

    LOCK.write_text(expected, encoding="utf-8")
    print(f"wrote {LOCK.name}: {len(packages)} package(s), digest {digest[:12]}")
    if missing:
        # Not an error: an optional extra may legitimately be absent locally.
        print(f"not installed locally (excluded): {', '.join(missing)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
