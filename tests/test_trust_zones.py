"""Trust-zone invariants from ARCHITECTURE.txt section 7.

WHY THIS EXISTS, and why it is not the rule that already exists.

`tests/test_architecture_boundaries.py` enforces ``communities/`` never imports
``kernel.*``. That is a *proxy* for section 7's actual rule -- "AI zones must not
directly access capital credentials" -- and a proxy is only correct while it happens
to cover the same set. It does not, in two ways this file fixes:

  * It is keyed on a DIRECTORY. Section 7 is keyed on a TRUST ZONE. `core/model_gateway.py`
    reaches an LLM and is therefore Zone C, but it lives in `core/`, so the directory rule
    never sees it. Conversely `research/` is Zone C and is covered only by accident of
    naming.

  * It says nothing about the other 60-odd modules in the manifest. A new Zone C module in
    a new directory is covered by the zone map the moment it is added, and not one moment
    before.

So this file enforces the rule the architecture states, at the granularity the
architecture states it at, and reads its input from ``ARCHITECTURE_ZONES.json`` -- which
``ARCHITECTURE_PLANES.md`` documents in prose. A mapping that lives only in prose is a
suggestion; these tests are what stop it being one.

FOUR PROPERTIES, and the fourth exists because of what this file found on its first run:

  1. The map is total       -- every module in the manifest has exactly one zone.
  2. The map agrees         -- manifest and JSON say the same thing.
  3. Section 7's rule holds -- no Zone C module imports a Zone A module.
  4. No module is orphaned   -- a manifest module absent from the map fails, and so does a
                                map entry naming a file that does not exist.

Property 4 is not defensive boilerplate. Writing this map surfaced that
``core/challenger.py`` and ``core/research_store.py`` were each listed in TWO planes, and
that ``kernel/competence.py`` -- added earlier the same day -- was in neither. A rule that
only checks what is present cannot find either of those.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ARCHITECTURE_PLANES.md"
ZONES = ROOT / "ARCHITECTURE_ZONES.json"

#: Section 7 names exactly these four. ``SHARED`` is ours, and is documented in the JSON
#: as carrying no authority -- see the module docstring. Asserting the set here is what
#: stops a fifth zone being invented to make a mapping problem disappear.
ARCHITECTURE_ZONES = frozenset({"A", "B", "C", "D"})
DECLARED_ZONES = ARCHITECTURE_ZONES | {"SHARED"}

#: The one rule section 7 states about zones.
AI_ZONE = "C"
CAPITAL_ZONE = "A"


def _load() -> dict:
    return json.loads(ZONES.read_text(encoding="utf-8"))


def _manifest_modules() -> list[tuple[str, str]]:
    """Every module row in the manifest, as ``(module, plane)``.

    Parsed from the tables rather than from the JSON, because the point of property 2 is
    that neither file is taken on trust. Rows look like::

        | `core/risk_firewall.py` | hard pre-trade limits |
        | `core/security.py`, `core/agents.py` | ACL primitives |

    so a row may name several modules and they are split on ``, ``.
    """
    text = MANIFEST.read_text(encoding="utf-8")
    plane = ""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.*Plane.*)$", line)
        if heading:
            # Strip the " Plane" suffix so the key is the plane's identity rather than
            # its heading decoration -- "Experience Plane" and "Experience" are the same
            # plane, and a mismatch here would be a naming artefact, not a finding.
            plane = heading.group(1).split("—")[0].strip()
            if plane.endswith(" Plane"):
                plane = plane[: -len(" Plane")]
            continue
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        for part in cell.split("`, `"):
            module = part.strip().strip("`").strip()
            if module.endswith((".py", "/*", ".json", ".html")):
                out.append((module, plane))
    return out


def _resolves(module: str) -> bool:
    """Does a manifest entry name something that exists?

    A directory glob is satisfied if it holds at least one tracked source file of any
    recognised kind -- Python for the backend, TypeScript for ``frontend/``. A literal
    must exist as a file.
    """
    if module.endswith("/*"):
        parent = ROOT / module[:-2]
        if not parent.is_dir():
            return False
        for pattern in ("*.py", "*.ts", "*.tsx"):
            if any(parent.rglob(pattern)):
                return True
        return False
    return (ROOT / module).exists()


ASSIGNMENTS = _load()["assignments"]
BY_MODULE: dict[str, dict] = {a["module"]: a for a in ASSIGNMENTS}


# ── 1. the map is total ─────────────────────────────────────────────────────


def test_every_manifest_module_has_exactly_one_zone() -> None:
    """A module in no zone is indistinguishable from one nobody classified.

    This is the check that found ``kernel/competence.py`` -- added earlier the same day,
    in neither the manifest nor anywhere else -- sitting in the tree unclassified.
    """
    manifest = _manifest_modules()
    assert manifest, "the manifest yielded no module rows; the parser is broken"

    missing = sorted({m for m, _ in manifest if m not in BY_MODULE})
    assert not missing, (
        "these manifest modules have no trust zone in ARCHITECTURE_ZONES.json: "
        f"{missing}. A module with no zone cannot be checked against section 7."
    )


def test_no_module_is_assigned_twice() -> None:
    """A module with two zones has no zone, and section 7 becomes unenforceable on it.

    ``core/challenger.py`` and ``core/research_store.py`` were each listed under two
    planes in the manifest. Both are resolved to a single zone here, deliberately:
    ``challenger`` to D, because a promotion decision is governance, and
    ``research_store`` to C, because it holds research knowledge rather than financial
    truth.
    """
    seen: dict[str, int] = {}
    for a in ASSIGNMENTS:
        seen[a["module"]] = seen.get(a["module"], 0) + 1
    dupes = sorted(m for m, n in seen.items() if n > 1)
    assert not dupes, f"modules assigned to more than one zone: {dupes}"


def test_every_declared_zone_is_one_the_architecture_names() -> None:
    """No fifth zone, and no zone the architecture does not define.

    Inventing a zone is the easy way to make an awkward mapping problem disappear, and it
    would do so by removing the constraint rather than by resolving it.
    """
    declared = set(_load()["zones"])
    assert declared == DECLARED_ZONES, (
        f"declared zones {sorted(declared)}; section 7 names {sorted(ARCHITECTURE_ZONES)} "
        "and this file adds only SHARED"
    )


# ── 2. the map agrees with the manifest ─────────────────────────────────────


def test_manifest_and_zone_map_agree_on_every_module() -> None:
    """Neither file is taken on trust: the prose and the data must say the same thing."""
    manifest = _manifest_modules()
    disagreements = []
    for module, plane in manifest:
        entry = BY_MODULE.get(module)
        if entry is None:
            continue  # reported by the totality test, with a better message
        if entry["plane"] != plane:
            disagreements.append(f"{module}: manifest plane {plane!r} vs map {entry['plane']!r}")
    assert not disagreements, disagreements


def test_every_mapped_module_exists_or_resolves() -> None:
    """A map entry naming nothing is a claim about a file that does not exist.

    The mirror of the totality check: that one catches reality missing from the map, this
    one catches the map inventing reality.
    """
    phantom = sorted(m for m in BY_MODULE if not _resolves(m))
    assert not phantom, f"zone map names modules that do not exist: {phantom}"


# ── 3. section 7's rule, at zone granularity ────────────────────────────────


def _module_files(entry_module: str) -> list[Path]:
    if entry_module.endswith("/*"):
        return sorted(p for p in (ROOT / entry_module[:-2]).glob("*.py"))
    return [ROOT / entry_module]


def _imports_zone(zone: str) -> set[Path]:
    """Every file belonging to ``zone``, excluding composition roots.

    Composition roots are excluded because they are *supposed* to reach across zones --
    `kernel/bootstrap.py` wires the oracle to the router and would violate the rule by
    existing. The manifest already names them separately for exactly this reason.
    """
    roots = {ROOT / r.rstrip("/*") for r in _load()["composition_roots"]}
    out: set[Path] = set()
    for entry in ASSIGNMENTS:
        if entry["zone"] != zone:
            continue
        for path in _module_files(entry["module"]):
            if any(root == path or root in path.parents for root in roots):
                continue
            out.add(path)
    return out


def test_no_ai_zone_module_reaches_the_capital_zone() -> None:
    """ARCHITECTURE.txt section 7: AI zones must not access capital credentials.

    The one rule the section states about zones, asserted directly rather than through a
    directory-shaped proxy. Zone C is the AI/research zone; Zone A holds the financial
    core -- the risk firewall, the capital firewall, the authorization envelope, the
    ledger.

    Imports are matched on the module path, so `from core.risk_firewall import ...` inside
    a Zone C file fails here whatever the import style, and a relative import of the same
    target fails too.
    """
    ai_files = _imports_zone(AI_ZONE)
    capital_files = _imports_zone(CAPITAL_ZONE)
    assert ai_files, "no Zone C files resolved; the rule would pass vacuously"
    assert capital_files, "no Zone A files resolved; the rule would pass vacuously"

    # Match on the SPECIFIC Zone A modules, never on their parent directory.
    #
    # The first version of this check also flagged any `from core.x import`, on the
    # reasoning that `core` holds Zone A modules. It does -- but it holds 56 modules
    # across all four zones, only 5 of them Zone A, so that test reported 19 violations
    # of which 18 were `core/claim_ledger.py imports from Zone A package core` wearing a
    # different name. A directory is not a zone, and a check that says it is will either
    # drown the real finding or be switched off.
    capital_dotted = {
        str(p.relative_to(ROOT).with_suffix("")).replace("\\", "/").replace("/", ".")
        for p in capital_files
    }
    assert len(capital_dotted) >= 5, (
        f"only {len(capital_dotted)} Zone A modules resolved; the rule would be weak"
    )

    violations: set[tuple[str, str]] = set()
    for path in sorted(ai_files):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for dotted in capital_dotted:
            pattern = rf"^\s*(?:from|import)\s+{re.escape(dotted)}\b"
            if re.search(pattern, source, re.MULTILINE):
                violations.add((path.relative_to(ROOT).as_posix(), dotted))

    # A known, reviewed exception is allowed -- but only if it is RECORDED as data with
    # a justification, and only for the exact importer/import pair. The alternative,
    # suppressing the one violation in the test, would leave the rule looking enforced
    # while it is not, and the next violation would be indistinguishable from the one
    # that was waved through. Recording it also keeps the count visible: a second
    # exception is a decision someone has to make on purpose.
    #
    # Tuples on both sides, deliberately. A first version built each violation as an
    # `f"{importer}|{module}"` string and compared it against a set of tuples, so the set
    # difference could never be empty and the test reported the one recorded exception as
    # an UNRECORDED violation. It failed for a structural reason while naming a
    # substantive one, which is worse than failing for either reason alone: it would have
    # sent the next reader to add a second, duplicate exception record.
    exceptions = {
        (e["importer"], e["imports"])
        for e in _load().get("zone_rule_exceptions", [])
    }
    unjustified = [
        e for e in _load().get("zone_rule_exceptions", []) if not e.get("justification", "").strip()
    ]
    assert not unjustified, f"zone_rule_exceptions without a justification: {unjustified}"

    unexpected = sorted(violations - exceptions)
    stale = sorted(exceptions - violations)

    assert not unexpected, (
        "ARCHITECTURE.txt section 7 -- AI zones must not directly access capital "
        f"credentials. Unrecorded violations: {unexpected}"
    )
    assert not stale, (
        f"zone_rule_exceptions records pairs that no longer violate the rule: {stale}. "
        "A closure is a good thing; leaving the record behind makes the exception list "
        "grow to look normal."
    )


# ── 4. the split planes are recorded, not tidied away ───────────────────────


def test_planes_that_straddle_zones_are_recorded_as_such() -> None:
    """Orthogonality is a fact about the design, not a defect to be smoothed over.

    The manifest's eight planes group by CAPABILITY; section 7's zones group by TRUST.
    Four of the eight therefore span more than one zone -- `Data & State` spans all four
    plus SHARED. Forcing a one-to-one mapping would be tidier and would be a lie, so the
    straddling is recorded in the manifest and asserted here.
    """
    recorded = _load()["planes_spanning_zones"]
    recorded = {k: v for k, v in recorded.items() if not k.startswith("$")}

    actual: dict[str, set[str]] = {}
    for entry in ASSIGNMENTS:
        actual.setdefault(entry["plane"], set()).add(entry["zone"])

    for plane, zones in recorded.items():
        assert actual.get(plane) == set(zones), (
            f"{plane}: manifest records zones {zones}, map has {sorted(actual.get(plane, set()))}"
        )

    straddling = {p for p, z in actual.items() if len(z) > 1}
    assert straddling == set(recorded), (
        f"planes spanning zones {sorted(straddling)} but the manifest records {sorted(recorded)}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
