# AIOS-0X Security Model
Version 0.1.0 | Current state: NO security layer exists (verified). This is the target + immediate minimums.

## 1. Current State (verified)
- No authn/authz anywhere; no secrets handling code; no encryption; no RBAC.
- No broker credentials exist yet (nothing to leak) - this is the window to build it right.
- .cursorrules mandates env-only secrets via pydantic-settings - not yet implemented.

## 2. Threat Model (top risks for this system)
1. Prompt injection -> agent exfiltrates credentials or triggers trades. Mitigation: agents never hold
   credentials; execution service is sole credential holder; structured outputs only; content provenance.
2. Memory poisoning -> false belief drives capital allocation. Mitigation: verification pipeline before
   belief promotion; raw immutability; contradiction tracking (Memory Model section 3).
3. Compromised dependency (73 OSS candidates). Mitigation: pin+lock, hash verify, SBOM, no direct imports
   (ABC adapters only), dependency scanning in CI.
4. Insider/agent overreach -> unauthorized orders. Mitigation: capability permissions, RiskGovernor
   independence, human approvals for live capital, full audit trail.
5. Data provider manipulation -> poisoned market signals. Mitigation: multi-source cross-validation,
   anomaly detection, quality states.

## 3. Capability Permission System (enforcement points)
| Layer | Mechanism |
|---|---|
| Event bus | topic-level publish/subscribe ACL per agent_id |
| Data APIs | scope tags on fetchers (asset class, region) |
| Execution | only EXECUTION_SERVICE role can submit; requires risk_decision_ref |
| Memory | append vs supersede rights separated |
| Admin | human-only operations behind explicit allowlist (Directive 80) |

Agent identity: every message carries agent_id + version; unsigned/unknown senders rejected.

## 4. Secrets Management
Phase A (local): .env via pydantic-settings, gitignored; no secrets in DB or logs (log scrubber).
Phase B: OpenBao-class vault container; dynamic short-lived broker API tokens; AES-256-GCM at-rest for
stored keys (per Doc 11); rotation schedule; break-glass procedure documented.
Rule: LLM context windows must never contain secret values; tools fetch credentials server-side at call time.

## 5. Audit & Tamper Evidence
Append-only audit log with hash chain (each record includes prev_hash) - detects deletion/reordering.
Constitution file SHA-256 pinned; boot refuses mismatch. Deployment artifacts signed (Phase C).

## 6. Compliance Hooks
OPA-class policy engine evaluates: restricted assets, jurisdiction rules, trade surveillance patterns,
record retention. Policies versioned; violations emit COMPLIANCE_ALERT (Tier-0).
AI interpretations of law are advisory; filings require human/professional authorization (Directives 42/45/47).

## 7. Immediate Minimums (Slice 0)
1. pydantic-settings BaseSettings for all config; example.env committed, real .env ignored.
2. git repo with .gitignore covering .env, data/, caches.
3. Log scrubber utility (mask key-like patterns) wired into logging config.
4. Agent identity fields added to bus envelope (agent_id, agent_version).
