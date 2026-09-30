# AIOS-0X Production Runbook

## Release rule

AIOS must remain in paper or shadow mode until every constitution gate is
approved. No software setting, model output, or automated process may bypass
`CONSTITUTION.md`.

## Pre-production validation

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install --editable .
python scripts/production_check.py
ruff check .
pytest -q
```

The production check is fail-closed. It confirms the constitution, package
imports, required deployment files, non-autonomous default, and disabled live
execution.

## Local service

Copy `.env.example` to `.env` and configure a high-entropy `API_AUTH_TOKEN`.
Keep these settings until the approval process is complete:

```text
AUTONOMY_MODE=SUPERVISED
AIOS_ALLOW_LIVE_EXECUTION=0
AIOS_EXCHANGE_TESTNET=1
```

Start paper/shadow service only:

```bash
docker compose up --build
```

Health is public for probes at `/api/v1/health`. All other routes require:

```text
Authorization: Bearer <API_AUTH_TOKEN>
```

The Compose port is bound to localhost. Place a separately reviewed TLS
reverse proxy in front of it before any remote access.

## Database backup and restore drill

Verify and back up a SQLite database:

```bash
python scripts/backup_sqlite.py data/command_center.db backups/command_center.db
```

Verify the restored database before use:

```bash
python -m aios events --db backups/command_center.db --after 0 --limit 1
```

A corrupted or invalid hash chain must never be backed up for promotion.
Production PostgreSQL requires an independently tested backup, restore, and
point-in-time recovery procedure.

## Incident procedure

1. Trigger the kill switch from an authenticated `RISK_ADMIN` operator.
2. Confirm positions are flattened and the emergency state is locked.
3. Preserve the database and audit log; do not delete or rewrite evidence.
4. Run `python scripts/production_check.py` and inspect `/api/v1/health`.
5. Resume only after a human reset with an operator identity and a documented
   incident review.

## Required gates before limited live capital

- Broker testnet order, cancel, reject, partial-fill, reconnect, and
  reconciliation tests passed.
- Shadow run completed with zero unexplained reconciliation failures.
- Licensed market-data source validated and failover tested.
- Tax and compliance rules reviewed by a qualified professional.
- Dependency, secret, package, and container checks pass in CI.
- PostgreSQL backup/restore and event-replay recovery drills pass.
- Principal records `APPROVE_LIVE_CAPITAL` through the audited control plane.
- Constitution is amended through an approved ADR before live routing is enabled.

## Never do

- Never put broker secrets in source, logs, prompts, or audit payloads.
- Never use production broker credentials during testing.
- Never expose the unauthenticated development server to the internet.
- Never interpret synthetic replay performance as evidence of live alpha.
