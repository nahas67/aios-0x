"""No settings field may exist that nothing reads.

THE PATTERN THIS EXISTS TO STOP
===============================

Four separate controls were found in this repo that were present, plausible, and inert:

    accentTheme            a 4-option picker; wrote a field the backend never defined
    highDensityMode        a live toggle; zero consumers anywhere
    numberFont             declared and defaulted; never rendered at all
    defaultExecutionMode   TWO controls (a TopSystemBar toggle and a settings button
                           pair) writing a field with no backend field, while rendering
                           "LIVE" in amber

All four shared one shape: a field on `SystemSettings`, a default in the adapter, and no
consumer. An operator could select "LIVE GATEWAY" and reasonably conclude the system was
pointed at a live venue. It was not — venue selection is governed by
`AIOS_ALLOW_LIVE_EXECUTION` and `AIOS_EXCHANGE_TESTNET` in
`communities/c5_execution/adapters.py`, which no UI could reach. That is `CONSTITUTION.md`
§3.1: never fabricate capability, and a control that asserts a capability it does not have
is the fabrication.

WHY A GATE AND NOT A LINT
=========================
Nothing type-checks this. A field with no consumers is perfectly valid TypeScript, so
`tsc`, vitest, the build and the operator-isolation gate are ALL green while a control lies.
Every one of the four was found by hand, and three of them shipped that way for months.

WHY THE ALLOWLIST, AND WHY IT SELF-CLEARS
==========================================
Seventeen further fields have no consumer today (see KNOWN_INERT). Most are reserved
capital-governance parameters — `var95DailyLimitUsd`, `maxSectorBetaCap`,
`mandatoryChallengerGate` — and deleting those is a product decision, not a bug fix. So
they are listed with a reason rather than silently ignored.

The list SHRINKS ITSELF: if an allowlisted field ever gains a consumer, this fails and the
entry must be deleted. The debt is therefore visible and monotonically decreasing, and
"we'll get to it" cannot quietly become permanent.

Run:  python scripts/verify_no_dead_settings.py
Exits non-zero on any UNLISTED dead field, or on an allowlisted field that is now wired.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
SRC = REPO / "frontend" / "src"

#: Files that DECLARE or DEFAULT a field without consuming it. Counting these as consumers
#: is precisely the mistake that let the four dead controls look alive: a default in the
#: adapter is the other half of the pattern, not evidence of a consumer.
DECLARATION_ONLY = {"types.ts", "settings.ts"}

#: Fields with no consumer today, each with why it is tolerated for now.
KNOWN_INERT: dict[str, str] = {
    "maxGrossLeverage": "capital parameter; §1 forbids leverage outright, so a control "
    "for it would contradict the constitution rather than implement it",
    "maxCorrelationCap": "paired with the C9 correlation matrix, which is not built",
    "var95DailyLimitUsd": "VaR not implemented; RiskFirewall uses fixed bounds",
    "mandatoryChallengerGate": "depends on the Challenger Arena screen (L25, unbuilt)",
    "dynamicReputationWeighting": "reputation is computed but not yet weighted",
    "agentLearningRate": "no online-learning loop consumes it",
    "macroAgentBaseWeight": "agent base weights are not yet used for allocation",
    "quantAgentBaseWeight": "agent base weights are not yet used for allocation",
    "sentimentAgentBaseWeight": "agent base weights are not yet used for allocation",
    "riskSentinelBaseWeight": "agent base weights are not yet used for allocation",
    "preTradeLatencyTimeoutMs": "no pre-trade latency gate exists",
    "enableDarkPoolCrossing": "dark pools are out of scope for spot-only execution",
    "fiscalYearEnd": "tax rules are a human-held production gate (Phase 5.0)",
    "maxSectorBetaCap": "sector exposure is not modelled",
    "hardwareKeyFido2Required": "FIDO2 enforcement is a security-plane item, not built",
    "pagerDutyIntegration": "integration is configured nowhere",
    "tradingViewClientId": "third-party widget not integrated",
}

FIELD = re.compile(r"^\s{2}([a-zA-Z][a-zA-Z0-9_]*)\??\s*:", re.M)


def main() -> int:
    types = (SRC / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"export interface SystemSettings \{(.*?)\n\}", types, re.S)
    if match is None:
        print("could not find the SystemSettings interface in frontend/src/types.ts")
        return 1

    fields = FIELD.findall(match.group(1))
    if not fields:
        print("SystemSettings parsed as having no fields; refusing to pass on a bad parse")
        return 1

    corpus_parts: list[str] = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"} or not path.is_file():
            continue
        if path.name in DECLARATION_ONLY or path.name.endswith(".test.ts"):
            continue
        corpus_parts.append(path.read_text(encoding="utf-8", errors="replace"))
    corpus = "\n".join(corpus_parts)

    dead = [f for f in fields if not re.search(rf"\b{re.escape(f)}\b", corpus)]
    unknown_dead = sorted(set(dead) - set(KNOWN_INERT))

    # The self-clearing half: an allowlist entry whose field now HAS a consumer is stale
    # debt, and leaving it would quietly forgive it forever.
    now_wired = sorted(
        f for f in KNOWN_INERT
        if f in fields and re.search(rf"\b{re.escape(f)}\b", corpus)
    )
    stale = sorted(set(KNOWN_INERT) - set(fields))

    print(f"SystemSettings fields           : {len(fields)}")
    print(f"with no consumer (documented)   : {len(set(dead) & set(KNOWN_INERT))}")
    print(f"with no consumer (UNDOCUMENTED) : {len(unknown_dead)}")
    print(f"inert share of the settings API: {len(set(dead)) / len(fields):.0%}")
    print()

    failures: list[str] = []
    for field in unknown_dead:
        failures.append(
            f"{field!r} has no consumer and is not on KNOWN_INERT: add it with a reason, "
            f"or wire it, or delete it"
        )
    for field in now_wired:
        failures.append(
            f"{field!r} is on KNOWN_INERT but now HAS a consumer — delete its entry, "
            f"the debt is paid"
        )
    for field in stale:
        failures.append(
            f"{field!r} is on KNOWN_INERT but is no longer a SystemSettings field — "
            f"delete its entry"
        )

    if failures:
        for failure in failures:
            print(f"  FAIL {failure}")
        print(f"\n{len(failures)} check(s) failed")
        return 1

    print(
        f"dead-settings gate green: {len(fields)} fields, "
        f"{len(set(dead))} documented as inert, 0 undocumented"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
