"""The tree must import on the oldest supported Python, not just the newest.

This suite exists because of a defect the local environment could not see.
Python 3.14 made annotations lazy by default (PEP 649), so on 3.14 an
annotation naming a TYPE_CHECKING-only import never evaluates and the bug is
invisible. On 3.12 -- which pyproject declares as supported and which both CI
and the Docker image actually run -- the same annotation is evaluated at
definition time and the module raises NameError on import. Every local test
passed against a module that could not be imported in production.

Rather than assert against one interpreter's opinion, the property is checked
structurally: a name that only exists inside `if TYPE_CHECKING:` must never
appear unquoted in an annotation of a module that does not enable PEP 563. That
holds on every version, so the check does not itself need a second interpreter.

tests/test_python_version_compat.py additionally imports the previously-broken
modules under a subprocess whose annotations are forced eager, which
reproduces the 3.12 behaviour on any interpreter.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: First-party packages that must import everywhere.
PACKAGES = ("aios", "api", "communities", "core", "evaluation", "kernel",
            "research", "schemas", "simulation", "scripts")


def _type_checking_only(tree: ast.Module) -> set[str]:
    """Names bound inside `if TYPE_CHECKING:` and nowhere else in the module."""
    guarded: set[int] = set()
    guarded_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
            if node.test.id == "TYPE_CHECKING":
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        guarded.add(id(sub))
                        for alias in sub.names:
                            guarded_names.add(
                                (alias.asname or alias.name).split(".")[0]
                            )

    available: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if id(node) not in guarded:
                for alias in node.names:
                    available.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            available.add(node.name)
        elif isinstance(node, ast.Assign):
            available.update(
                t.id for t in node.targets if isinstance(t, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            available.add(node.target.id)
    return guarded_names - available


def _enables_pep563(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(a.name == "annotations" for a in node.names)
        for node in tree.body
    )


def _unquoted_uses(path: Path, names: set[str]) -> list[tuple[str, str]]:
    """Annotation sites naming `names` that are NOT string annotations."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if _enables_pep563(tree):
        return []

    hits: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        annotations: list[ast.expr] = []
        if isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in args.posonlyargs + args.args + args.kwonlyargs:
                if arg.annotation is not None:
                    annotations.append(arg.annotation)
            if args.vararg is not None and args.vararg.annotation is not None:
                annotations.append(args.vararg.annotation)
            if args.kwarg is not None and args.kwarg.annotation is not None:
                annotations.append(args.kwarg.annotation)
            if node.returns is not None:
                annotations.append(node.returns)

        for annotation in annotations:
            # A string annotation is lazy by construction: never evaluated.
            if isinstance(annotation, ast.Constant) and isinstance(
                annotation.value, str
            ):
                continue
            for sub in ast.walk(annotation):
                if isinstance(sub, ast.Name) and sub.id in names:
                    hits.append((f"{path.relative_to(ROOT).as_posix()}:{sub.lineno}", sub.id))
    return hits


def _first_party_modules() -> list[Path]:
    modules: list[Path] = []
    for package in PACKAGES:
        base = ROOT / package
        if base.is_dir():
            modules.extend(sorted(base.rglob("*.py")))
    return modules


def test_no_annotation_names_a_type_checking_only_import() -> None:
    """A TYPE_CHECKING-only name must appear quoted, or the module raises
    NameError on Python <=3.13 the moment it is imported.

    The failure mode this prevents is loud but misleading: pip install
    succeeds, the import check in the Dockerfile passes on 3.14 and fails on
    3.12, and the traceback points at an annotation rather than at the version
    gap that caused it.
    """
    violations: list[tuple[str, str]] = []
    for path in _first_party_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        guarded_only = _type_checking_only(tree)
        if not guarded_only:
            continue
        violations.extend(_unquoted_uses(path, guarded_only))

    assert violations == [], (
        "TYPE_CHECKING-only names used unquoted in annotations; these raise "
        f"NameError at import on Python <=3.13: {violations}"
    )


@pytest.mark.parametrize(
    "module",
    [
        "communities.c5_execution.execution",
    ],
)
def test_module_imports_with_eager_annotations(module: str) -> None:
    """Import the module in a subprocess where annotations evaluate eagerly.

    PEP 649 cannot be switched back on, so this simulates <=3.13 by compiling
    the source with annotations unquoted and evaluating it. On 3.14 the normal
    import path is lazy and would pass regardless; the check below forces the
    eager interpretation explicitly.
    """
    source_root = str(ROOT)
    probe = (
        "import sys, importlib, ast, pathlib\n"
        f"sys.path.insert(0, {source_root!r})\n"
        f"mod = importlib.import_module({module!r})\n"
        "path = pathlib.Path(mod.__file__)\n"
        "tree = ast.parse(path.read_text(encoding='utf-8'))\n"
        "# Re-evaluate every annotation eagerly in a namespace that has the\n"
        "# module's real globals, which is what CPython <=3.13 does at def time.\n"
        "import typing\n"
        "bad = []\n"
        "for node in ast.walk(tree):\n"
        "    anns = []\n"
        "    if isinstance(node, ast.AnnAssign):\n"
        "        anns.append(node.annotation)\n"
        "    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):\n"
        "        for a in (node.args.posonlyargs + node.args.args + node.args.kwonlyargs):\n"
        "            if a.annotation is not None:\n"
        "                anns.append(a.annotation)\n"
        "        if node.returns is not None:\n"
        "            anns.append(node.returns)\n"
        "    for ann in anns:\n"
        "        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):\n"
        "            continue  # string annotation: lazy on every version\n"
        "        try:\n"
        "            eval(compile(ast.Expression(ann), '<ann>', 'eval'), vars(mod), vars(mod))\n"
        "        except NameError as exc:\n"
        "            bad.append(f'{getattr(node, \"name\", \"?\")}: {exc}')\n"
        "if bad:\n"
        "    print('EAGER_ANNOTATION_FAILURES:', bad)\n"
        "    sys.exit(1)\n"
        "print('eager annotations OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{module} has annotations that fail when evaluated eagerly: "
        f"{result.stdout.strip()} {result.stderr.strip()[-400:]}"
    )


def test_minimum_supported_python_is_still_supported() -> None:
    """The declared floor must be a Python this project can actually run on.

    If requires-python claims 3.11 while the tree only imports under 3.14,
    every consumer on 3.11-3.13 gets a broken package. This asserts the floor
    is below the version where PEP 649 hides annotation errors, so the
    structural check above is load-bearing rather than theoretical.
    """
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = data["project"]["requires-python"]
    assert ">=3.11" in floor, (
        f"requires-python is {floor!r}; the annotation-eagerness check assumes "
        "the project supports a pre-PEP-649 interpreter"
    )
