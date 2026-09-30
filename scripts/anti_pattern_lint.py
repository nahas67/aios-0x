"""Anti-pattern lint: named, greppable, enforced at build time.

The vNext program reviewed 28 external repositories. Most of the useful ideas
were adopted, but four repos also demonstrated concrete failure modes that this
project must never reproduce. Those failure modes are recorded here as machine
checks rather than as prose warnings, because prose warnings are not a control.

Each rule names the repository that demonstrated the pattern. The name is not
accusatory: these are real projects, and several are excellent. The point is
that the specific mechanism, in a financial context, transfers badly.

Run::

    python scripts/anti_pattern_lint.py            # check, exit 1 on violation
    python scripts/anti_pattern_lint.py --json     # machine-readable

Design notes:

* Rules are static AST/regex checks over project source. They do not import the
  modules under test, so a violation cannot execute anything.
* Tests, docs, and the lint registry itself are exempt from the rules that
  would otherwise match their own fixtures and explanatory text.
* A ``# noqa: anti-pattern:<id>`` comment suppresses a single finding and is
  itself reported, so suppressions stay visible in review.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Directories that are never linted: they are excluded by .gitignore, are
#: third-party, or are generated.
EXCLUDED_PARTS = frozenset(
    {
        "__pycache__",
        ".venv-fresh",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".repowise",
        ".evidence",
        ".vt-study",
        "node_modules",
        "ui",
        "aios.egg-info",
    }
)

#: Extensions subject to the Python rules.
PY_SUFFIXES = frozenset({".py"})

#: Extensions subject to the generic secret/prompt rules.
TEXT_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yml", ".yaml"})

#: Paths exempt from every rule. The lint's own registry names the patterns in
#: prose and must not be a violation of itself.
SELF_EXEMPT = frozenset(
    {
        "scripts/anti_pattern_lint.py",
    }
)

#: Directories where the rules do not apply: docs describe the anti-patterns in
#: order to forbid them, and tests deliberately construct violating fixtures.
EXEMPT_PREFIXES = ("docs/", "tests/", "research/benchmarks/")


@dataclass(frozen=True)
class Finding:
    """One violation of one rule."""

    rule_id: str
    path: str
    line: int
    message: str
    suppressed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule_id,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "suppressed": self.suppressed,
        }


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _exempt(path: Path) -> bool:
    rel = _rel(path)
    if rel in SELF_EXEMPT:
        return True
    return rel.startswith(EXEMPT_PREFIXES)


def iter_files(suffixes: frozenset[str]) -> Iterator[Path]:
    """Yield project files with the given suffixes, skipping vendored trees."""
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if EXCLUDED_PARTS & set(path.parts):
            continue
        yield path


def _has_suppression(source_lines: list[str], index: int, rule_id: str) -> bool:
    """True when the offending line carries a targeted noqa for this rule."""
    marker = f"noqa: anti-pattern:{rule_id}"
    return marker in source_lines[index]


# ────────────────────────────────────────────────────────────────────────────
# AP1: environment-sourced signing key on an agent-reachable path
#
# Demonstrated by The-Swarm-Corporation/AutoHedge, whose tool layer reads
# SOLANA_PRIVATE_KEY from the environment and signs a transaction inside an
# agent-invoked function. The variable name is irrelevant; the mechanism is a
# signing helper reachable from a tool handler.
# ────────────────────────────────────────────────────────────────────────────

_AP1_ENV_SIGNING_NAMES = re.compile(
    r"\b[A-Z0-9_]*(?:PRIVATE_KEY|SECRET_KEY|SIGNING_KEY|SEED_PHRASE|MNEMONIC)\b"
)
_AP1_SIGNING_CALL = re.compile(r"\.\s*(sign_transaction|sign_tx|sign|sign_message)\s*\(")
_AP1_KEY_SOURCE = re.compile(r"(?:os\.environ|os\.getenv|getenv)\s*\(")


def rule_env_signing_key() -> Iterator[Finding]:
    rule = "AP1"
    for path in iter_files(PY_SUFFIXES):
        if _exempt(path):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        # A signing call is only a violation when a private-key name and an
        # environment read appear within the same enclosing function.
        try:
            tree = ast.parse("\n".join(lines), filename=str(path))
        except SyntaxError:  # pragma: no cover - ruff/pytest own syntax errors
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = ast.get_source_segment("\n".join(lines), node) or ""
            if not _AP1_SIGNING_CALL.search(segment):
                continue
            if not (_AP1_ENV_SIGNING_NAMES.search(segment) and _AP1_KEY_SOURCE.search(segment)):
                continue
            yield Finding(
                rule,
                _rel(path),
                node.lineno,
                (
                    f"{node.name}: reads a private-key material from the environment and signs "
                    "in the same function. Move key custody to a secrets boundary "
                    "(OpenBao) and keep signing out of agent-reachable code."
                ),
                _has_suppression(lines, node.lineno - 1, rule),
            )


# ────────────────────────────────────────────────────────────────────────────
# AP2: capital-sizing terms inside prompt text
#
# Demonstrated by AutoHedge, where the position size, stop loss, and take
# profit are requested as prose from a language model and returned as strings.
# The same terms legitimately appear in deterministic risk code, so the rule is
# scoped to strings that are clearly prompt-like.
# ────────────────────────────────────────────────────────────────────────────

_AP2_PROMPT_MARKERS = (
    "you are",
    "your task",
    "respond",
    "return json",
    "output json",
    "system prompt",
    "instructions:",
    "role:",
)
_AP2_SIZING_TERMS = re.compile(
    r"\b(position[_ ]siz\w*|siz\w* the position|stop[_ ]loss|take[_ ]profit|"
    r"how much (?:to|should)|amount to (?:buy|sell))\b",
    re.IGNORECASE,
)
_AP2_ASSIGNED_TO_PROMPT = re.compile(
    r"\b(prompt|system_prompt|system_message|instruction|template|text)\b\s*[:=]"
)


def rule_prompt_expresses_size() -> Iterator[Finding]:
    rule = "AP2"
    for path in iter_files(frozenset({".py", ".ts", ".tsx"})):
        if _exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not _AP2_ASSIGNED_TO_PROMPT.search(line):
                continue
            lowered = line.lower()
            if not any(marker in lowered for marker in _AP2_PROMPT_MARKERS):
                continue
            match = _AP2_SIZING_TERMS.search(line)
            if not match:
                continue
            yield Finding(
                rule,
                _rel(path),
                index + 1,
                (
                    f"prompt text asks the model for '{match.group(0).strip().lower()}'. "
                    "Sizing is portfolio mathematics; it must not be requested from a model."
                ),
                _has_suppression(lines, index, rule),
            )


# ────────────────────────────────────────────────────────────────────────────
# AP3: fail-open default on a control decision
#
# The GenAI-Security-Project/agent-control-standard reference Guardian defaults
# to "proceed" when a decision cannot be obtained, so a broken governance path
# silently stops governing. The failure posture of a control must be explicit.
# ────────────────────────────────────────────────────────────────────────────

_AP3_FAIL_OPEN = re.compile(
    r"(?:default|fallback|on_error|on_failure)\w*\s*[=:]\s*"
    r"[\"'](?:allow|proceed|permit|accept|open|pass|ignore)[\"']",
    re.IGNORECASE,
)


def rule_fail_open_control() -> Iterator[Finding]:
    rule = "AP3"
    for path in iter_files(PY_SUFFIXES):
        if _exempt(path):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = _AP3_FAIL_OPEN.search(line)
            if not match:
                continue
            yield Finding(
                rule,
                _rel(path),
                index + 1,
                (
                    f"control default resolves to permissive ({match.group(0).strip()}). "
                    "A control whose failure posture is 'allow' is not a control."
                ),
                _has_suppression(lines, index, rule),
            )


# ────────────────────────────────────────────────────────────────────────────
# AP4: LLM output used directly as a numeric order parameter
#
# An LLM returning a number that flows into a quantity, notional, or price
# field without passing through deterministic validation. Caught structurally:
# a model-gateway call assigned to a name that then reaches an order argument.
# ────────────────────────────────────────────────────────────────────────────

_AP4_MODEL_CALL = re.compile(
    r"\b(?:model_gateway|model_router|llm|chat|complete|generate|invoke_model)\s*\(",
    re.IGNORECASE,
)
_AP4_SIZE_VARIABLE = re.compile(
    r"\b(quantity|notional|size|leverage|amount|position_size_pct|units)\b",
    re.IGNORECASE,
)
_AP4_ORDER_SINK = re.compile(
    r"\.(?:submit|create_order|place_order|send_order|submit_order)\s*\(",
    re.IGNORECASE,
)


def rule_model_number_to_order() -> Iterator[Finding]:
    rule = "AP4"
    for path in iter_files(PY_SUFFIXES):
        if _exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:  # pragma: no cover
            continue
        # Collect the names bound from a model call anywhere in the file.
        model_bound: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None or not isinstance(value, ast.Call):
                continue
            func = value.func
            name = getattr(func, "attr", None) or getattr(func, "id", None) or ""
            if not _AP4_MODEL_CALL.search(f"{name}(") and not _AP4_MODEL_CALL.search(
                ast.unparse(func)
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    model_bound.add(target.id)
        if not model_bound:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node.func)
            if not _AP4_ORDER_SINK.search(rendered):
                continue
            for argument in [*node.args, *[kw.value for kw in node.keywords]]:
                if not isinstance(argument, ast.Name):
                    continue
                if argument.id not in model_bound:
                    continue
                if not _AP4_SIZE_VARIABLE.search(argument.id):
                    continue
                yield Finding(
                    rule,
                    _rel(path),
                    node.lineno,
                    (
                        f"{argument.id!r} comes from a model call and reaches {rendered} as a "
                        "size parameter. An authorization envelope must be the only source."
                    ),
                    _has_suppression(lines, node.lineno - 1, rule),
                )


# ────────────────────────────────────────────────────────────────────────────
# AP5: marketing claim without a citation to a test
#
# AutoHedge markets itself as a risk-first architecture while shipping no risk
# enforcement code. Documentation drift of this kind is invisible until an
# operator trusts it. A claim in a docstring that asserts a safety property must
# name the test that enforces it.
# ────────────────────────────────────────────────────────────────────────────

_AP5_SAFETY_CLAIM = re.compile(
    r"\b(risk[- ]first|fail[- ]safe|failsafe|production[- ]ready|"
    r"battle[- ]tested|guaranteed|never fails|bulletproof)\b",
    re.IGNORECASE,
)
_AP5_TEST_REFERENCE = re.compile(r"tests?/[a-z0-9_]+\.py|test_[a-z0-9_]+")


def rule_unsourced_safety_claim() -> Iterator[Finding]:
    rule = "AP5"
    for path in iter_files(PY_SUFFIXES):
        if _exempt(path):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = _AP5_SAFETY_CLAIM.search(line)
            if not match or line.lstrip().startswith("#"):
                continue
            window = " ".join(lines[index : index + 12])
            if _AP5_TEST_REFERENCE.search(window):
                continue
            yield Finding(
                rule,
                _rel(path),
                index + 1,
                (
                    f"safety claim {match.group(0)!r} with no test cited nearby. Name the test "
                    "that enforces the property, or remove the claim."
                ),
                _has_suppression(lines, index, rule),
            )


# ────────────────────────────────────────────────────────────────────────────
# AP6: in-sample backtest presented as a profitability result
#
# Demonstrated by sopersone/cabbage-trading-machine, whose own VALIDATION.md is
# admirably honest and whose README nonetheless carries a promotional return
# figure its backtest does not produce. A numeric performance claim in a
# docstring or module comment must state net-of-cost and out-of-sample status.
# ────────────────────────────────────────────────────────────────────────────

_AP6_RETURN_CLAIM = re.compile(
    r"(\$[\d,]+(?:\.\d+)?\s*(?:profit|gain|return|PnL)|"
    r"\b\d+(?:\.\d+)?%\s*(?:annualized\s*)?(?:return|Sharpe|profit))",
    re.IGNORECASE,
)
_AP6_QUALIFIER = re.compile(
    r"\b(in[- ]sample|not verified|unverified|illustrative|synthetic|"
    r"net[- ]of[- ]cost|out[- ]of[- ]sample|backtest|projected|estimate)\b",
    re.IGNORECASE,
)


def rule_unsourced_return_claim() -> Iterator[Finding]:
    rule = "AP6"
    for path in iter_files(PY_SUFFIXES):
        if _exempt(path):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = _AP6_RETURN_CLAIM.search(line)
            if not match:
                continue
            window = " ".join(lines[index : index + 6])
            if _AP6_QUALIFIER.search(window):
                continue
            yield Finding(
                rule,
                _rel(path),
                index + 1,
                (
                    f"performance figure {match.group(0)!r} with no in-sample / net-of-cost / "
                    "out-of-sample qualifier within reach."
                ),
                _has_suppression(lines, index, rule),
            )


RULES = {
    rule_env_signing_key,
    rule_prompt_expresses_size,
    rule_fail_open_control,
    rule_model_number_to_order,
    rule_unsourced_safety_claim,
    rule_unsourced_return_claim,
}

RULE_CATALOGUE = {
    "AP1": "Environment-sourced signing key on an agent-reachable path (AutoHedge)",
    "AP2": "Prompt text requests position size, stop loss, or take profit (AutoHedge)",
    "AP3": "Control decision defaults to permissive on failure (agent-control-standard)",
    "AP4": "Model output flows directly into an order size parameter",
    "AP5": "Safety claim asserted without citing the test that enforces it (AutoHedge)",
    "AP6": "Return figure presented without in-sample or out-of-sample qualification",
}


def collect() -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule())
    findings.sort(key=lambda f: (f.path, f.line, f.rule_id))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    findings = collect()
    active = [f for f in findings if not f.suppressed]
    suppressed = [f for f in findings if f.suppressed]

    if args.json:
        print(
            json.dumps(
                {
                    "violations": [f.as_dict() for f in active],
                    "suppressed": [f.as_dict() for f in suppressed],
                    "rules": RULE_CATALOGUE,
                },
                indent=2,
            )
        )
        return 1 if active else 0

    if not active:
        print(f"anti-pattern lint: clean ({len(RULES)} rules)")
    else:
        print(f"anti-pattern lint: {len(active)} violation(s)\n")
        for finding in active:
            print(f"  {finding.rule_id}  {finding.path}:{finding.line}")
            print(f"        {finding.message}")
        print()
    if suppressed:
        print(f"  ({len(suppressed)} suppressed finding(s) reported below)")
        for finding in suppressed:
            print(f"  {finding.rule_id}  {finding.path}:{finding.line}  [suppressed]")
    return 1 if active else 0


if __name__ == "__main__":
    sys.exit(main())
