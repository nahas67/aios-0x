#!/usr/bin/env python3
"""Build a clean release archive from the repository.

Creates a tar.gz archive containing only release-safe files:
  - Python source (aios/, api/, communities/, core/, etc.)
  - Scripts
  - Configuration examples (.env.example)
  - Documentation
  - Requirements
  - Dockerfile + docker-compose
  - Compiled frontend (ui/dist/)
  - Tests (for verification)
  - Golden data

Excludes:
  - .env (secrets)
  - .git/
  - node_modules/
  - __pycache__/
  - *.pyc
  - SQLite databases
  - Logs, PID files, status files
  - UI audit captures
  - Development caches

Run: python scripts/package_release.py [--version VERSION]
"""

import argparse
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patterns to ALWAYS exclude (forbidden in release)
FORBIDDEN_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    ".git/",
    ".gitignore",
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "*.egg-info/",
    "data/*.db",
    "data/*.log",
    "data/command_center_server.log",
    "data/command_center_server.pid",
    "data/command_center_status.json",
    "data/ui_audit/",
    "data/pytest_*.txt",
    "data/figma_*.json",
    "*.md",  # exclude except README
    "!README.md",
    ".cursorrules",
    ".gitattributes",
    "TAG",
    "frontend/node_modules/",
    "frontend/.cache/",
]

# Directories to include
INCLUDE_DIRS = [
    "aios",
    "api",
    "communities",
    "core",
    "evaluation",
    "kernel",
    "research",
    "schemas",
    "scripts",
    "simulation",
    "tests",
    "data/golden",
]

# Files to include at root
INCLUDE_FILES = [
    # pyproject.toml is the single dependency authority; there is no
    # requirements.txt to keep in sync (see docs/DEVELOPMENT.md).
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
    ".env.example",
    "ui/index.html",
]


def should_exclude(path: Path, rel: str) -> bool:
    """Check if a relative path should be excluded from the archive."""
    rel_fwd = rel.replace("\\", "/")

    for pattern in FORBIDDEN_PATTERNS:
        if pattern.startswith("!"):
            # Negation — this pattern is allowed
            allowed = pattern[1:]
            if rel_fwd == allowed or rel_fwd.startswith(allowed):
                return False
        elif pattern.endswith("/"):
            # Directory match
            if rel_fwd.startswith(pattern) or f"/{pattern}" in rel_fwd:
                return True
        elif "*" in pattern:
            # Glob match
            import fnmatch
            if fnmatch.fnmatch(rel_fwd, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        else:
            # Exact file match
            if rel_fwd == pattern:
                return True

    return False


def build_archive(version: str = "latest") -> Path:
    """Build a clean release archive."""
    archive_name = f"aios-0x-{version}.tar.gz"
    archive_path = ROOT / "dist" / archive_name
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Building release archive: {archive_name}")

    included_count = 0

    with tarfile.open(archive_path, "w:gz") as tar:
        # Add directories
        for dir_name in INCLUDE_DIRS:
            dir_path = ROOT / dir_name
            if not dir_path.exists():
                print(f"  SKIP (not found): {dir_name}/")
                continue
            for file in sorted(dir_path.rglob("*")):
                if file.is_file() and not should_exclude(file, str(file.relative_to(ROOT))):
                    tar.add(file, arcname=str(file.relative_to(ROOT)))
                    included_count += 1

        # Add root files
        for file_name in INCLUDE_FILES:
            file_path = ROOT / file_name
            if file_path.exists() and not should_exclude(file_path, file_name):
                tar.add(file_path, arcname=file_name)
                included_count += 1

        # Add ui/dist if it exists (compiled frontend)
        ui_dist = ROOT / "ui" / "dist"
        if ui_dist.exists():
            for file in ui_dist.rglob("*"):
                if file.is_file():
                    rel = str(file.relative_to(ROOT))
                    tar.add(file, arcname=rel)
                    included_count += 1

    print(f"  Included: {included_count} files")
    print(f"  Archive: {archive_path} ({archive_path.stat().st_size / 1024:.1f} KB)")
    return archive_path


def verify_archive(archive_path: Path) -> bool:
    """Verify the archive contains no forbidden files."""
    print("\nVerifying archive...")
    violations = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name

            # Check for forbidden patterns
            if name.endswith(".env") and name != ".env.example":
                violations.append(f"SECRET: {name}")
            if ".env." in name and not name.endswith(".env.example"):
                violations.append(f"SECRET: {name}")
            if "figd_" in name.lower():
                violations.append(f"SECRET: {name}")
            if "__pycache__" in name:
                violations.append(f"DEV: {name}")
            if name.endswith(".pyc"):
                violations.append(f"DEV: {name}")
            if ".git/" in name:
                violations.append(f"DEV: {name}")
            if "node_modules" in name:
                violations.append(f"DEV: {name}")
            if name.endswith(".db"):
                violations.append(f"STATE: {name}")
            if name.endswith(".log"):
                violations.append(f"STATE: {name}")
            if name.endswith(".pid"):
                violations.append(f"STATE: {name}")

    if violations:
        print("  VIOLATIONS FOUND:")
        for v in violations:
            print(f"    ❌ {v}")
        return False
    else:
        print("  ✅ No forbidden files found")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AIOS-0X release archive")
    parser.add_argument("--version", default="latest", help="Release version label")
    args = parser.parse_args()

    archive_path = build_archive(args.version)
    clean = verify_archive(archive_path)

    if not clean:
        print("\n⚠ Archive contains forbidden files — review before release!")
        return 1
    else:
        print("\n✅ Release archive is clean")
        return 0


if __name__ == "__main__":
    exit(main())
