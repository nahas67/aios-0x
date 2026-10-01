"""Supply chain: billed materials, sealed releases, no committed secrets (G230).

SBOM, release integrity, and secret hygiene are the parts of supply-chain
security this environment can actually enforce: no network for scanners, no
HSM for authority signatures. What lands here is what is checkable locally —
a generated bill of materials covering exactly the lock, a self-verifying
release archive, and a tree with no secrets in it — with the deferred parts
(scanner runs, authority signing in CI, OpenBao) stated as deferred rather
than pretended.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import shutil
import tarfile
from pathlib import Path

import pytest

from scripts import sbom as sbom_module
from scripts.package_release import MANIFEST_NAME, should_exclude, verify_archive

ROOT = Path(__file__).resolve().parents[1]


# ══════════════════════════════════════════════════════════════════════════
# SBOM: generated, exact, byte-stable
# ══════════════════════════════════════════════════════════════════════════


def test_sbom_covers_exactly_the_lock() -> None:
    """Every pinned distribution present once, nothing else. An SBOM that
    omits a dependency hides attack surface; one that adds phantom entries
    sends scanners chasing ghosts."""
    entries = sbom_module.parse_lock()
    assert len(entries) > 10
    document = sbom_module.build_sbom(entries)
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.5"
    names = [component["name"] for component in document["components"]]
    assert names == sorted(names)
    lock_names = sorted(name for name, _ in entries)
    assert names == lock_names
    for component in document["components"]:
        assert component["purl"].startswith("pkg:pypi/")
        assert component["type"] == "library"


def test_sbom_is_byte_stable(tmp_path: Path) -> None:
    """Two generations diff empty: a diff between SBOMs must mean the
    closure changed, not that dict ordering wandered."""
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    sbom_module.write_sbom(out_a, sbom_module.build_sbom(sbom_module.parse_lock()))
    sbom_module.write_sbom(out_b, sbom_module.build_sbom(sbom_module.parse_lock()))
    assert out_a.read_bytes() == out_b.read_bytes()


def test_unpinned_lock_lines_are_refused(tmp_path: Path) -> None:
    """A lock file with a bare package name is not locked. Building an SBOM
    from it would certify versions nobody resolved."""
    lock = tmp_path / "requirements.lock"
    lock.write_text("aiohttp==3.14.3\nrequests\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unpinned entry"):
        sbom_module.parse_lock(lock)


def test_duplicate_lock_lines_are_refused(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("aiohttp==3.14.3\naiohttp==3.14.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate entries"):
        sbom_module.parse_lock(lock)


def test_sbom_main_writes_the_default_file(tmp_path: Path) -> None:
    """The CLI entry point honors --out and reports the component count."""
    out = tmp_path / "custom.json"
    assert sbom_module.main(["--out", str(out)]) == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert len(document["components"]) == len(sbom_module.parse_lock())


# ══════════════════════════════════════════════════════════════════════════
# Release integrity: manifest completeness and hash agreement
# ══════════════════════════════════════════════════════════════════════════


def _archive(tmp_path: Path, members: dict[str, bytes], manifest: str | None) -> Path:
    """Hand-built tiny archive: the format contract under test without
    building the whole repo."""
    path = tmp_path / "rel.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        if manifest is not None:
            data = manifest.encode()
            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _manifest_for(members: dict[str, bytes]) -> str:
    lines = [
        f"{hashlib.sha256(payload).hexdigest()}  {name}"
        for name, payload in sorted(members.items())
    ]
    return "\n".join(lines) + "\n"


def test_clean_archive_with_matching_manifest_verifies(tmp_path: Path) -> None:
    members = {"core/a.py": b"print(1)\n", "README.md": b"hi\n"}
    assert verify_archive(_archive(tmp_path, members, _manifest_for(members))) is True


def test_member_names_are_posix_slashed_not_native() -> None:
    """tar member names are POSIX paths by specification; the manifest must
    agree with them byte for byte.

    `str(Path.relative_to(...))` yields backslashes on Windows, so the manifest
    recorded `data\\golden\\X.csv` while the archive member was
    `data/golden/X.csv`. verify_archive compares the two, so it reported every
    nested file as an unlisted member -- the integrity check could never pass for
    any path containing a directory separator, which is most of the repository.
    """
    from scripts.package_release import arcname_of

    nested = ROOT / "core" / "capital_firewall.py"
    assert nested.exists()
    arc = arcname_of(nested)
    assert arc == "core/capital_firewall.py"
    assert "\\" not in arc, f"archive member name must not contain backslashes: {arc!r}"


def test_a_nested_file_is_not_reported_as_unlisted(tmp_path: Path) -> None:
    """The end-to-end form of the same property, using a nested member."""
    members = {"core/pkg/mod.py": b"x = 1\n", "core/a.py": b"y = 2\n"}
    assert verify_archive(_archive(tmp_path, members, _manifest_for(members))) is True


def test_manifest_and_member_names_are_the_same_string(tmp_path: Path) -> None:
    """Both sides of the integrity check must derive the name the same way, so
    read the manifest back out of the archive and compare against the member
    names rather than trusting that they were built from the same variable."""
    import tarfile

    members = {"core/deep/nested/mod.py": b"z = 3\n"}
    path = _archive(tmp_path, members, _manifest_for(members))
    with tarfile.open(path, "r:gz") as tar:
        names = {n for n in tar.getnames() if n != MANIFEST_NAME}
        raw = tar.extractfile(MANIFEST_NAME).read().decode()  # type: ignore[union-attr]
    listed = {line.split("  ", 1)[1] for line in raw.splitlines() if line}
    assert names == listed, f"member names {names} and manifest names {listed} disagree"


def test_archive_missing_its_manifest_fails(tmp_path: Path) -> None:
    assert verify_archive(_archive(tmp_path, {"core/a.py": b"x"}, None)) is False


def test_archive_with_tampered_member_fails(tmp_path: Path) -> None:
    """Same names, different bytes: the hash check is what makes the
    manifest integrity rather than inventory."""
    members = {"core/a.py": b"print(1)\n"}
    forged = {"core/a.py": b"print(2)\n"}
    manifest = _manifest_for(members)
    assert verify_archive(_archive(tmp_path, forged, manifest)) is False


def test_archive_with_unlisted_member_fails(tmp_path: Path) -> None:
    """A member the manifest never mentions is unaudited payload, whether
    appended by mistake or by malice."""
    members = {"core/a.py": b"x", "extra/evil.py": b"y"}
    manifest = _manifest_for({"core/a.py": b"x"})
    assert verify_archive(_archive(tmp_path, members, manifest)) is False


def test_archive_with_a_secret_fails(tmp_path: Path, capsys) -> None:
    members = {"core/a.py": b"x", ".env": b"KEY=live"}
    assert verify_archive(_archive(tmp_path, members, _manifest_for(members))) is False
    assert "SECRET" in capsys.readouterr().out


# ══════════════════════════════════════════════════════════════════════════
# Packaging exclusions: negations must actually override, and only exactly
# ══════════════════════════════════════════════════════════════════════════


def test_negation_overrides_a_pattern_listed_before_it() -> None:
    """`*md` is listed before `!README.md`, so an order-dependent matcher
    excludes README.md and the negation never runs. README.md is named in
    INCLUDE_FILES, so it silently never shipped in any release archive."""
    assert should_exclude(Path("README.md"), "README.md") is False
    assert should_exclude(Path("CONSTITUTION.md"), "CONSTITUTION.md") is False


def test_other_markdown_is_still_excluded() -> None:
    """Re-including two files must not have re-included all of prose. The
    default `*.md` exclusion is the reason an archive is code, not docs."""
    for rel in ("docs/DEPENDENCY_POLICY.md", "ARCHITECTURE_PLANES.md", "CHECKPOINT.md"):
        assert should_exclude(Path(rel), rel) is True, f"{rel} must stay out"


def test_a_negation_does_not_widen_into_a_prefix_match() -> None:
    """The negations are exact, so they re-include only what they name.

    The previous implementation compared with `startswith`, so a negation
    written as `!README.md` would also rescue `README.md.bak` -- quietly
    widening an allowlist. This checks the negation helper directly, against
    names that `*.md` genuinely excludes, so a prefix regression is visible
    rather than masked by the fact that `.bak` is not itself excluded.
    """
    from scripts.package_release import _negation_matches

    assert _negation_matches("README.md", "README.md") is True
    for rel in ("README.md.bak", "docs/README.md", "README.mdx"):
        assert _negation_matches(rel, "README.md") is False, (
            f"the README negation must not match {rel!r} by prefix or basename"
        )

    # End to end: the root README ships, and a same-named file in a subdirectory
    # does not ride in on the root's negation.
    assert should_exclude(Path("README.md"), "README.md") is False
    assert should_exclude(Path("docs/README.md"), "docs/README.md") is True


def test_secrets_and_caches_remain_excluded() -> None:
    """The negations are narrow; the exclusions they sit beside are not."""
    for rel in (
        ".env",
        ".env.production",
        "node_modules/react/index.js",
        "core/__pycache__/x.pyc",
        "data/aios.db",
        "logs/serve.err.log",
    ):
        assert should_exclude(Path(rel), rel) is True, f"{rel} must stay out"


# ══════════════════════════════════════════════════════════════════════════
# The CI secret gate itself
# ══════════════════════════════════════════════════════════════════════════


def _ci_key_pattern() -> re.Pattern[str]:
    """The exact pattern CI greps for, read out of the workflow.

    Extracted rather than restated so the test cannot drift from the gate it
    polices: editing the workflow without editing here fails this test, which
    is the only way the claim "the gate is accurate" stays true.
    """
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r"grep -rEn \"([^\"]*sk-[^\"]*)\"", text)
    assert match is not None, "CI workflow no longer greps for API keys"
    return re.compile(match.group(1))


def test_ci_key_gate_ignores_words_that_end_in_sk() -> None:
    """The gate once matched any "sk-" plus one character, so it fired on
    "risk-bot", "risk-governor", and "task-tier" — ordinary source. A gate that
    fails on a hundred false hits is a gate that gets read past, which is
    worse than no gate: it looks like a check that isn't really running.
    """
    pattern = _ci_key_pattern()
    decoys = [
        'registry.begin_validation("momentum-1", "v1", "risk-bot")',
        'self.risk_governor = RiskGovernor(event_bus=self._scoped("risk-governor"))',
        '"""Model router v0: task-tier based routing with honest unavailability.',
        'RISK_ADMIN_TOKEN = "token-risk-admin"',
        'playbook_id="pb-risk-off",',
        '(60, -0.0008, 0.012),  # risk-off drift',
        'regime: string; // e.g. "Expansionary", "Mean-Reverting", "Risk-Off"',
    ]
    for decoy in decoys:
        assert pattern.search(decoy) is None, f"CI key gate false-positives on {decoy!r}"


def test_ci_key_gate_still_catches_real_key_shapes() -> None:
    """Tightening the gate must not disarm it. OpenAI keys are sk- plus 48
    base62 chars, sk-proj- plus longer; Anthropic's carry sk-ant-. Samples are
    assembled from parts so this test file does not itself contain the pattern
    the CI gate greps for — a test that failed its own gate would be its own
    defect."""
    pattern = _ci_key_pattern()
    head = "s" + "k-"
    body = "A1b2C3d4E5f6G7h8J9k0L1m2N3o4P5q6R7s8T9u0V1w2X3y4Z5"
    realistic = [
        head + body,                                  # legacy OpenAI shape
        head + "proj-" + body + body,                 # project-keyed OpenAI
        head + "ant-api03-" + body + body,            # Anthropic
        head + "ant-api03-" + body,                    # shorter but still long
    ]
    for sample in realistic:
        assert pattern.search(sample) is not None, "CI key gate would miss a real key shape"


def test_ci_key_gate_finds_no_keys_in_this_tree() -> None:
    """The gate's own verdict on the actual repository: clean. If a real key
    ever landed here, this fails on the commit that introduced it rather than
    three reviews later."""
    import subprocess

    pattern = _ci_key_pattern()
    offenders: list[str] = []
    for include in ("*.py", "*.ts", "*.tsx", "*.js"):
        result = subprocess.run(
            [
                "git", "grep", "-lE", pattern.pattern,
                "--", f"*.{include.split('.')[1]}",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        offenders.extend(line for line in result.stdout.splitlines() if line)
    assert offenders == [], f"key-shaped strings in tracked sources: {sorted(set(offenders))}"


# ══════════════════════════════════════════════════════════════════════════
# Secrets: none tracked, env ignored, examples valueless
# ══════════════════════════════════════════════════════════════════════════


def test_no_env_file_is_tracked() -> None:
    """A committed .env is a published secret. .env.example ships; .env
    never does. Checked via git so the test sees what a clone would."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    env_files = [
        line
        for line in tracked.stdout.splitlines()
        if line == ".env"
        or line.endswith("/.env")
        or ("/.env." in line and not line.endswith(".env.example"))
    ]
    assert env_files == [], f"secret files tracked: {env_files}"


def test_gitignores_env_everywhere() -> None:
    """The ignore rule is what keeps the next .env out, not vigilance."""
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content


def test_no_private_key_material_in_the_tree() -> None:
    """Key files and key blocks have no legitimate place in this tree.
    Scanned by name and by content head, excluding environments and caches
    that are not shipped. Markers are assembled, never literal: the test
    must not itself contain the pattern it scans for."""
    skip = {".venv-fresh", ".venv", "node_modules", "__pycache__", ".git", "frontend"}
    begin = "-----BEGIN "
    tail = "PRIVATE KEY-----"
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix in {".pem", ".key"} or path.name in {"id_rsa", "id_ed25519"}:
            offenders.append(str(path))
            continue
        if path.suffix in {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".txt"}:
            try:
                head = path.read_text(encoding="utf-8", errors="strict")[:2000]
            except (OSError, UnicodeError):
                continue
            if (begin + tail) in head or (begin + "RSA " + tail) in head:
                offenders.append(str(path))
    assert offenders == [], f"private key material in tree: {offenders}"


def test_env_example_carries_no_secret_values() -> None:
    """The example documents names, not secrets: variables whose names say
    KEY, TOKEN, SECRET, or PASSWORD must be empty or placeholder. Config
    values (model names, URLs, modes) are fine — the failure mode is a real
    credential shipping in every clone, not a default being opinionated."""
    example = ROOT / ".env.example"
    assert example.exists(), "expected .env.example to exist and be valueless"
    secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    allowed = {"", "changeme", "your-key-here", "xxx", "placeholder"}
    for lineno, line in enumerate(example.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if not any(marker in name.upper() for marker in secret_markers):
            continue
        assert value.strip().strip("\"'") in allowed, (
            f".env.example:{lineno} assigns {name.strip()} what looks like a real value"
        )

# ══════════════════════════════════════════════════════════════════════════
def test_an_extras_providing_distribution_missing_from_the_lock_fails(
    sandbox: Path,
) -> None:
    """`psycopg[binary]` declares TWO distributions, and both must be locked.

    Found by independent review: `--check` passed with `psycopg-binary` deleted from
    the lock, with the digest recomputed so the lock was otherwise internally
    perfect. `declared_requirements` contributed a `base-extra` root so GENERATION
    resolved it, while `declared_specifiers` -- which drives the presence and
    specifier checks -- recorded only `requirement.name`. The two halves of the
    module disagreed about what pyproject declares and the gate consulted one.

    It matters more than an ordinary missing package: this is the database driver's
    binary, so a lock without it installs a psycopg that cannot connect to anything,
    and the lock is what a deployment installs from.
    """
    def drop_binary(text: str) -> str:
        header, packages = _split_lock(text)
        packages = [line for line in packages if not line.startswith("psycopg-binary==")]
        return _rebuild(header, packages)

    _rewrite(sandbox, drop_binary)

    problems = _verify(sandbox)
    assert any("psycopg-binary" in p and "absent" in p for p in problems), (
        f"removing an extras-provided distribution must fail; got {problems}"
    )


def test_an_extras_provider_is_required_without_inventing_a_range(
    sandbox: Path,
) -> None:
    """pyproject declares a range for `psycopg`, and none at all for `psycopg-binary`.

    So the provider is required to be PRESENT and has no range to satisfy. Giving
    it the parent's range would be inventing a constraint pyproject does not
    declare, and would pass a `psycopg-binary` incompatible with the `psycopg`
    beside it -- a false assurance manufactured by the check itself. Asserted on
    the real lock: the provider is present, and no specifier is claimed for it.
    """
    table = lockdep.declared_specifiers(EXTRAS)
    assert "psycopg-binary" in table, (
        "the extras provider must be among the checked names"
    )
    assert table["psycopg-binary"] == [], (
        "the extras provider must be required-present with no invented range, "
        f"got {table['psycopg-binary']}"
    )
    assert table["psycopg"], "psycopg itself must still carry its declared range"


def test_check_installed_reports_an_unreadable_lock_without_raising(
    sandbox: Path, capsys
) -> None:
    """A flag whose contract is "report, do not fail" must not raise.

    `--check-installed` documents that it reports drift rather than failing on it,
    because the honest answer to "how does my environment differ" is never an
    exception. An unpinned entry is a fact about the lock worth reporting, exactly
    like a version difference, so it takes the same path. `--check` remains the flag
    that refuses such a lock.
    """
    (sandbox / "requirements.lock").write_text(
        "aiohttp==3.14.3\nrequests\n", encoding="utf-8"
    )

    code = lockdep.main(["--check-installed"])
    out = capsys.readouterr().out

    assert code == 0, f"the reporting flag must not fail: exit {code}"
    assert "not readable" in out, out
    assert "unpinned lock entry" in out, out


def test_check_refuses_the_same_lock_the_reporting_flag_only_reports(
    sandbox: Path,
) -> None:
    """The two flags disagree on purpose, and the disagreement is the point.

    One refuses a lock that is not a lock; the other reports on it. A reader who
    collapses them gets either a gate that cries wolf or a report that fails a
    build, so the difference is pinned rather than left to be inferred from the
    code.
    """
    (sandbox / "requirements.lock").write_text(
        "aiohttp==3.14.3\nrequests\n", encoding="utf-8"
    )

    assert lockdep.main(["--check"]) == 1, "the gate must refuse an unpinned lock"
    assert lockdep.main(["--check-installed"]) == 0, "the reporter must not fail"



# Dependency lock gate (environment-independent)
# ══════════════════════════════════════════════════════════════════════════


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"


def _load_module():
    """Import scripts/lock_dependencies.py as a module.

    It is a script, not a package module, so it is loaded by path. Loading it once
    per module keeps the tests honest about it being importable at all.
    """
    path = ROOT / "scripts" / "lock_dependencies.py"
    spec = importlib.util.spec_from_file_location("_lockdep_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lockdep = _load_module()
EXTRAS = lockdep.DEFAULT_EXTRAS


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository copy where the lock and pyproject can be corrupted freely.

    `verify_lock` reads pyproject through a module-level constant, so it is
    redirected rather than the real file being touched. The real `requirements.lock`
    is never written by any test here.
    """
    (tmp_path / "requirements.lock").write_text(
        LOCK.read_text(encoding="utf-8"), encoding="utf-8"
    )
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    monkeypatch.setattr(lockdep, "ROOT", tmp_path)
    monkeypatch.setattr(lockdep, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(lockdep, "LOCK", tmp_path / "requirements.lock")
    return tmp_path


def _split_lock(text: str) -> tuple[list[str], list[str]]:
    """(header lines, package lines).

    `verify_lock` digests the PACKAGE lines only, so any test that rebuilds a lock
    has to hash the same lines. An earlier version of the version-violation test
    hashed the headers too, so its digest never matched and the test passed because
    of a digest mismatch rather than because it detected the thing it names.
    """
    header, packages = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        (header if line.startswith("#") else packages).append(line)
    return header, packages


def _rebuild(header: list[str], packages: list[str]) -> str:
    """A well-formed lock from parts, digest computed exactly as verify_lock does.

    `digest_of` hashes `\n`.join(packages) over lines sorted by `str.lower`. Matching
    that exactly is what makes "the digest is correct" mean something here rather
    than meaning "a different digest, also wrong".
    """
    ordered = sorted(packages, key=str.lower)
    digest = hashlib.sha256("\n".join(ordered).encode()).hexdigest()
    head = [line for line in header if not line.startswith("# resolved-digest")]
    return "\n".join(head + [f"# resolved-digest: {digest}"] + ordered) + "\n"


def _rewrite(sandbox: Path, transform) -> None:
    text = (sandbox / "requirements.lock").read_text(encoding="utf-8")
    (sandbox / "requirements.lock").write_text(transform(text), encoding="utf-8")


def _verify(sandbox: Path):
    lines, extras, digest = lockdep.parse_lock(
        (sandbox / "requirements.lock").read_text(encoding="utf-8")
    )
    return lockdep.verify_lock(lines, extras, digest, EXTRAS)


# ══════════════════════════════════════════════════════════════════════════
# The committed lock passes. Everything below is about failing.
# ══════════════════════════════════════════════════════════════════════════


def test_the_committed_lock_agrees_with_pyproject(sandbox: Path) -> None:
    """The actual repository lock, checked with the actual pyproject.

    Read as bytes rather than generated, so this cannot pass by the test and the
    script agreeing on a bug.
    """
    assert _verify(sandbox) == [], "the committed lock must satisfy the new gate"


def test_the_gate_is_environment_independent(sandbox: Path) -> None:
    """The verdict must not depend on what is installed here.

    This is the property the old gate lacked and the whole reason for the rewrite.
    It is asserted structurally -- `verify_lock` takes no environment input at all
    -- rather than by simulating another machine, which is not expressible here. The
    companion assertion is that the module no longer imports `importlib.metadata`
    on the check path.
    """
    import inspect

    source = inspect.getsource(lockdep.verify_lock)
    assert "md." not in source and "importlib" not in source, (
        "verify_lock must not consult the installed environment; that is what made "
        "the previous gate machine-dependent"
    )


# ══════════════════════════════════════════════════════════════════════════
# A dependency declared in pyproject but missing from the lock
# ══════════════════════════════════════════════════════════════════════════


def test_a_declared_dependency_missing_from_the_lock_fails(sandbox: Path) -> None:
    """The drift the gate exists to catch: pyproject moved, the lock did not."""

    def drop_pydantic(text: str) -> str:
        header, packages = _split_lock(text)
        packages = [line for line in packages if not line.startswith("pydantic==")]
        return _rebuild(header, packages)

    _rewrite(sandbox, drop_pydantic)

    problems = _verify(sandbox)
    assert problems, "a missing declared dependency must fail"
    assert any("pydantic" in p and "absent" in p for p in problems), problems


def test_a_locked_version_violating_pyproject_fails(sandbox: Path) -> None:
    """The property the OLD gate could not detect at all.

    The previous implementation asked only whether the lock matched what was
    installed, so a lock pinning a version outside the declared range passed as
    long as that version happened to be installed. Here the lock is internally
    consistent -- digest recomputed so it is a plausible-looking lock -- and still
    wrong, because it contradicts pyproject.
    """

    def pin_illegal(text: str) -> str:
        # A version pyproject forbids, in a lock that is otherwise internally
        # perfect: correct digest, correct extras header, everything pinned.
        # The only thing wrong with it is that it contradicts the declaration,
        # which is the property the OLD gate could not detect at all.
        header, packages = _split_lock(text)
        packages = [line for line in packages if not line.startswith("pydantic==")]
        packages.append("pydantic==1.0.0")
        return _rebuild(header, packages)

    _rewrite(sandbox, pin_illegal)

    problems = _verify(sandbox)
    assert problems, "a version violating pyproject must fail"
    assert any("pydantic" in p and "disagree" in p for p in problems), problems


# ══════════════════════════════════════════════════════════════════════════
# A lock that is not a lock
# ══════════════════════════════════════════════════════════════════════════


def test_an_unpinned_entry_is_refused() -> None:
    """A bare name is not a pin, and a lock of bare names installs whatever it finds.

    The SBOM builder refuses these too (`sbom.parse_lock`); the gate must agree,
    because a lock that the SBOM refuses and the gate accepts is a gate that is not
    reading the same file.
    """
    with pytest.raises(ValueError, match="unpinned lock entry"):
        lockdep.parse_lock("aiohttp==3.14.3\nrequests\n")


def test_a_duplicate_package_is_refused(sandbox: Path) -> None:
    """Two versions of one package make the install order decide which wins."""

    def duplicate(text: str) -> str:
        header, packages = _split_lock(text)
        packages.append("packaging==1.0")  # a second version of one package
        return _rebuild(header, packages)

    _rewrite(sandbox, duplicate)

    problems = _verify(sandbox)
    assert any("appears 2 times" in p for p in problems), problems


# ══════════════════════════════════════════════════════════════════════════
# Hand-editing the lock
# ══════════════════════════════════════════════════════════════════════════


def test_a_hand_edited_lock_fails_on_the_digest(sandbox: Path) -> None:
    """Changing a version without regenerating must be caught.

    The digest covers the package lines, so an edit that leaves the digest alone is
    detectable without knowing anything about the environment -- which is what makes
    it useful in CI.
    """

    def bump_one(text: str) -> str:
        # Change a version WITHOUT touching the digest: the hand-edit case.
        header, packages = _split_lock(text)
        bumped = [
            line.replace("packaging==", "packaging==9", 1)
            if line.startswith("packaging==")
            else line
            for line in packages
        ]
        return "\n".join(header + bumped) + "\n"

    _rewrite(sandbox, bump_one)

    problems = _verify(sandbox)
    assert any("resolved-digest does not match" in p for p in problems), problems


def test_a_lock_without_a_digest_fails(sandbox: Path) -> None:
    """A missing digest means no tamper evidence at all, so it is a failure rather
    than a pass-with-one-less-check."""

    def strip_digest(text: str) -> str:
        return "\n".join(
            line for line in text.splitlines() if not line.startswith("# resolved-digest")
        )

    _rewrite(sandbox, strip_digest)

    problems = _verify(sandbox)
    assert any("no # resolved-digest" in p for p in problems), problems


def test_an_extras_header_mismatch_fails(sandbox: Path) -> None:
    """A lock generated for fewer extras is missing those packages.

    Reported rather than silently accepted, because the omission is invisible
    otherwise: the file looks complete, and `pip install -r` would install a
    closure that lacks, say, the database driver.
    """

    def drop_an_extra(text: str) -> str:
        return text.replace("# extras: dev,postgres,nats,ccxt", "# extras: dev")

    _rewrite(sandbox, drop_an_extra)

    problems = _verify(sandbox)
    assert any("extras" in p for p in problems), problems


# ══════════════════════════════════════════════════════════════════════════
# The reported problems are actionable
# ══════════════════════════════════════════════════════════════════════════


def test_all_problems_are_reported_not_just_the_first(sandbox: Path) -> None:
    """A contributor fixing a lock should see the whole list once.

    The previous gate printed one word, "stale", which is why the file became
    unreadable when it started failing -- there was nothing to act on.
    """

    def break_several(text: str) -> str:
        header, packages = _split_lock(text)
        packages = [line for line in packages if not line.startswith("pydantic==")]
        packages.append("packaging==1.0")  # a duplicate of packaging==26.0
        header = [
            "# extras: dev" if line.startswith("# extras:") else line
            for line in header
        ]
        return _rebuild(header, packages)

    _rewrite(sandbox, break_several)

    problems = _verify(sandbox)
    assert len(problems) >= 3, f"expected several problems, got {problems}"
    assert any("pydantic" in p for p in problems)
    assert any("extras" in p for p in problems)
    assert any("appears 2 times" in p for p in problems)
