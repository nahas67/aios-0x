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
import io
import json
import re
import tarfile
from pathlib import Path

import pytest

from scripts import sbom as sbom_module
from scripts.package_release import MANIFEST_NAME, verify_archive

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
