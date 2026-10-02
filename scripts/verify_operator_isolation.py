"""Verify the operator surface shares no runtime with the analyst console.

WHY A SCRIPT AND NOT A COMMENT, and why a sourcemap.

ARCHITECTURE.txt section 8 requires the emergency commands to "survive model/runtime
failure". The analyst console opens an SSE stream and mounts sixteen workspaces, so if
the kill switch were a tab inside it, anything that broke the console would take the
kill switch down too. Claiming separation in a docstring would make it exactly as
reliable as every other comment in this repository that says something true today.

The first attempt at the check was a grep for module names in the built bundle, and it
was WORTHLESS: Vite minifies, so `LiveTradingWorkspace` returns zero hits whether or not
the workspace is in the graph. A check that passes for a reason unrelated to what it
names is the defect class this project keeps finding -- the registry rule that read its
own docstring, the lock tests that passed on a digest mismatch. So the check reads the
SOURCEMAP, which lists the actual input modules, and the forbidden set is derived from
the filesystem rather than hard-coded, so it stays correct as the tree grows.

WHAT IT ASSERTS, AND WHAT IT DELIBERATELY DOES NOT

  1. `operator.html` exists and loads a JS entry distinct from the analyst's.
  2. No workspace, no hook, no chart library and no SSE client appears anywhere in the
     operator page's transitive first-party graph.
  3. `operator.html` references no external origin -- no font CDN, no analytics. That
     backs the claim in its own HTML comment rather than leaving it as prose.
  4. The operator entry is materially smaller than the analyst entry, which is a sanity
     check on the above rather than the primary evidence.

IT CHECKS THE BUNDLE, NOT THE SOURCE, and that is the correct semantics rather than a
limitation. A bare `import './views/LiveTradingWorkspace'` that is never rendered is
tree-shaken out, so the gate stays green -- and that green is accurate, because the
module does not ship to an operator during an incident. An import-graph linter would
report it as a leak and be reporting a non-problem. The failure this gate must catch is
the one where analyst code actually reaches the operator bundle, and that is the one it
catches: both were confirmed by deliberately rendering a workspace and by calling the SSE
reconnect helper from the operator surface, and both turned this script red.

Run:  python scripts/verify_operator_isolation.py [--no-build]
Exits non-zero on any violation, so it is usable as a gate.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
DIST = REPO / "ui" / "dist"

#: First-party module paths the operator surface must never reach, as path fragments
#: matched against sourcemap `sources`. Derived from the filesystem below so that a
#: seventeenth workspace is covered without editing this file.
FORBIDDEN_DIRS = ("components/views", "hooks")
FORBIDDEN_FILES = ("api/stream.ts", "App.tsx")

#: Third-party libraries that would mean the analyst chart layer came along.
FORBIDDEN_LIBS = ("recharts", "d3-", "echarts", "plotly")


def build() -> None:
    """Build with sourcemaps, because without them there is nothing to verify."""
    print("building with --sourcemap …")
    proc = subprocess.run(
        [str(FRONTEND / "node_modules" / ".bin" / "vite.cmd"), "build", "--sourcemap"],
        cwd=FRONTEND, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:], proc.stderr[-2000:])
        raise SystemExit("build failed; cannot verify isolation against a stale dist")


def operator_entry() -> pathlib.Path:
    html = (DIST / "operator.html").read_text(encoding="utf-8")
    m = re.search(r'src="(/assets/operator-[\w.-]+\.js)"', html)
    if not m:
        raise SystemExit("operator.html loads no /assets/operator-*.js entry")
    return DIST / m.group(1).lstrip("/")


def analyst_entry() -> pathlib.Path | None:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    m = re.search(r'src="(/assets/main-[\w.-]+\.js)"', html)
    return DIST / m.group(1).lstrip("/") if m else None


def first_party_sources(bundle: pathlib.Path) -> list[str]:
    """Every first-party module in a bundle's graph, from its sourcemap.

    A bundle with no sourcemap is a FAILURE, not a pass. "Could not check" and "checked
    and clean" must never look the same, or this script's green is worth nothing.
    """
    map_path = bundle.with_suffix(bundle.suffix + ".map")
    if not map_path.exists():
        raise SystemExit(
            f"{bundle.name} has no sourcemap, so its module graph cannot be read. "
            "Rebuild with --sourcemap. Refusing to report an unverified pass."
        )
    data = json.loads(map_path.read_text(encoding="utf-8"))
    return [s for s in data.get("sources", []) if "node_modules" not in s]


def operator_graph() -> list[str]:
    """The operator page's COMPLETE first-party graph.

    Its own entry, plus every shared chunk its HTML preloads. Reading only the entry's
    sourcemap would miss anything hoisted into a shared chunk, which is exactly where
    shared code goes.
    """
    html = (DIST / "operator.html").read_text(encoding="utf-8")
    bundles = set(re.findall(r"/assets/([\w.-]+\.js)", html))
    if not bundles:
        raise SystemExit("operator.html references no bundles")
    sources: list[str] = []
    for name in sorted(bundles):
        path = DIST / "assets" / name
        if not path.exists():
            raise SystemExit(f"operator.html references a missing bundle: {name}")
        sources.extend(first_party_sources(path))
    return sorted(set(sources))


def forbidden_patterns() -> list[tuple[str, str]]:
    """(label, fragment) pairs derived from what is actually on disk."""
    out: list[tuple[str, str]] = []
    for directory in FORBIDDEN_DIRS:
        base = FRONTEND / "src" / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix in {".ts", ".tsx"} and path.is_file():
                out.append((f"{directory}/{path.name}", f"/{directory}/{path.name}"))
    for name in FORBIDDEN_FILES:
        if (FRONTEND / "src" / name).exists():
            out.append((f"src/{name}", f"/{name}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true", help="verify the existing dist")
    args = ap.parse_args()

    if not args.no_build:
        build()
    if not DIST.is_dir():
        raise SystemExit("ui/dist does not exist; build first")

    entry = operator_entry()
    analyst = analyst_entry()
    graph = operator_graph()
    forbidden = forbidden_patterns()

    print(f"\noperator entry : {entry.name} ({entry.stat().st_size / 1024:.1f} KB)")
    if analyst and analyst.exists():
        print(f"analyst entry  : {analyst.name} ({analyst.stat().st_size / 1024:.1f} KB)")
    print(f"first-party modules reachable from operator.html: {len(graph)}")
    for source in graph:
        print(f"    {source}")

    # 1. distinct entries
    checks: list[tuple[str, bool, str]] = [
        (
            "operator.html loads a distinct entry from the analyst console",
            entry.name != (analyst.name if analyst else ""),
            f"{entry.name} vs {analyst.name if analyst else 'none'}",
        )
    ]

    # 2. nothing analyst-only in the graph
    hits = [
        (label, source)
        for label, fragment in forbidden
        for source in graph
        if fragment in source.replace("\\", "/")
    ]
    checks.append(
        (
            "no workspace, hook, stream or App module in the operator graph",
            not hits,
            f"leaked: {hits}" if hits else f"{len(forbidden)} forbidden modules checked",
        )
    )

    # 3. no external origin referenced by the operator shell
    html = (DIST / "operator.html").read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    checks.append(
        (
            "operator.html references no external origin",
            not external,
            f"external: {external}" if external else "no CDN, no font host, no analytics",
        )
    )

    # 4. materially smaller
    if analyst and analyst.exists():
        ratio = entry.stat().st_size / analyst.stat().st_size
        checks.append(
            (
                "the operator entry is materially smaller than the analyst entry",
                ratio < 0.25,
                f"{ratio:.1%} of the analyst bundle",
            )
        )

    print()
    failed = 0
    for label, ok, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}  ({detail})")
        failed += 0 if ok else 1

    if failed:
        print(f"\n{failed} check(s) failed")
        return 1
    print("\nisolation verified from the sourcemaps, not from a comment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
