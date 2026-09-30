"""Architecture boundary tests: the plane manifest is machine-enforced.

ARCHITECTURE_PLANES.md declares the module → plane mapping; these tests make
the invariants non-negotiable. The plane re-housing is enforced here rather than
expressed as thousands of lines of file churn.

A note on injected dependencies, because the rule has a cost and the cost has a
known shape. When Community 5 began routing every venue call through the tool
guardian, the obvious implementation imported ``kernel.tool_governance`` and
this test failed. Both easy fixes were wrong: dropping the governance left the
execution path unguarded, and relaxing the boundary made the plane manifest a
suggestion. The resolution was to split the wire types into
``schemas/governance.py`` and inject the implementation. Expect the same shape
of problem for any future control-plane dependency reaching a community.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _py_files(rel: str) -> list[Path]:
    base = ROOT / rel
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------- communities isolation


def test_communities_never_import_the_kernel() -> None:
    """Business logic never touches the OS directly — mutation flows only
    through composition roots (runner/bridge)."""
    violations: list[str] = []
    for path in _py_files("communities"):
        src = _source(path)
        if re.search(r"^\s*(from|import)\s+kernel\b", src, re.MULTILINE):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == [], f"communities import kernel: {violations}"


def test_no_cross_community_imports() -> None:
    """Communities communicate exclusively via schema contracts + bus topics."""
    violations: list[str] = []
    for path in _py_files("communities"):
        owner = path.relative_to(ROOT).parts[1]  # communities.<cX>_*
        for match in re.finditer(
            r"from\s+(communities\.[a-z0-9_]+)|import\s+communities\.([a-z0-9_]+)",
            _source(path),
        ):
            target = match.group(1) or match.group(2)
            if target.split(".")[1] != owner.split("_")[0]:
                # tolerate intra-community imports (same cX package)
                same = path.relative_to(ROOT).parts[1].startswith(target.replace("communities.", "").split("_")[0])
                if not same:
                    violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert violations == [], f"cross-community imports: {violations}"


# ------------------------------------------------------------- experience read-only


def test_experience_plane_never_mutates_stores() -> None:
    """api/ is a read-only view layer (original architecture §3A)."""
    forbidden = ("append_event", "save_prediction", "save_observation", "save_postmortem")
    violations: list[str] = []
    for path in _py_files("api"):
        src = _source(path)
        for call in forbidden:
            if re.search(rf"\.\s*{call}\s*\(", src):
                # server.py must not mutate either; views aggregate only
                violations.append(f"{path.relative_to(ROOT)} calls .{call}(")
    assert violations == [], violations


def test_views_module_has_no_store_write_imports() -> None:
    src = _source(ROOT / "api" / "views.py")
    assert "append_event" not in src
    assert "INSERT INTO" not in src


# ------------------------------------------------------- private-state hygiene


def test_no_private_state_access_outside_owners() -> None:
    """Patterns like `_objects[` belong to kernel internals; recovery and
    composition use public APIs. Enforced outside kernel/simulation/tests."""
    owners = ("kernel", "simulation", "tests")
    patterns = (r"\._objects\[", r"\._receipts\[", r"\._versions\[", r"\._runs\[")
    violations: list[str] = []
    for rel in ("core", "research", "api", "aios", "communities"):
        for path in _py_files(rel):
            src = _source(path)
            for pattern in patterns:
                if re.search(pattern, src):
                    violations.append(
                        f"{path.relative_to(ROOT)} uses {pattern}"
                    )
    _ = owners
    assert violations == [], violations


# ------------------------------------------------------------------- manifest


def test_plane_manifest_exists_and_covers_all_communities() -> None:
    manifest = _source(ROOT / "ARCHITECTURE_PLANES.md")
    assert "Plane Manifest" in manifest
    for community_pkg in sorted((ROOT / "communities").iterdir()):
        if community_pkg.is_dir() and not community_pkg.name.startswith("__"):
            assert community_pkg.name in manifest, (
                f"{community_pkg.name} missing from ARCHITECTURE_PLANES.md"
            )


def test_composition_roots_are_declared() -> None:
    manifest = _source(ROOT / "ARCHITECTURE_PLANES.md")
    for root_module in ("simulation/replay_runner.py", "simulation/kernel_bridge.py", "aios/cli.py"):
        assert root_module in manifest, f"{root_module} must be declared as composition root"
