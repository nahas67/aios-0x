# AIOS-0X — AI-Native Investment Institution

AIOS-0X is an **AI-native investment institution** built as an operating system:
multi-community intelligence (research, verification, strategy, execution),
deterministic financial state, and risk-governed authority — where every LLM and
agent proposes, and only deterministic, audited components decide.

**Status:** V1-A.2 landed — PostgreSQL financial tier, JetStream durable event
backbone, safety plane, mypy strict across the tree. 467 tests collected
(427 pass / 40 service-gated). Production deployment is gated behind five
human-held gates (see [CONSTITUTION.md](CONSTITUTION.md) and
[CHECKPOINT.md](CHECKPOINT.md)).

---

## Core Principles

1. **Deterministic authority outranks intelligence.** The Risk Firewall and
   RiskGovernor are deterministic code; they outrank every LLM and agent. All
   mutation flows through the kernel's authority gateway — fail closed.
2. **Honesty laws.** Never fabricate prices, fills, news, profit, or
   capability. Missing data ⇒ NO TRADE / UNKNOWN, never a default value.
   Simulated artifacts carry `is_simulated=true` end-to-end.
3. **Everything is receipts.** Every ALLOW/DENY decision, order hop, promotion,
   and operator action is recorded in a hash-chained, tamper-evident audit log.
4. **Exactly-once economic effects.** Financial mutation and its event commit
   are one transaction; the outbox/inbox pattern means a replayed fill is
   "already applied," never double-applied. The book is reconstructible from
   the ledger.
5. **The constitution is pinned.** [CONSTITUTION.md](CONSTITUTION.md) has its
   SHA-256 pinned in `core/constitution.py` and is verified at every boot; a
   mismatch halts the system until a human resolves it. Self-evolving
   components cannot rewrite it.
6. **Humans hold the gates.** Kill-switch lockouts, challenger promotions,
   tax filings, and live capital all require explicit human action through the
   audited control plane. The bot never holds authority.

## Architecture

Eleven communities plus the kernel, connected only by typed contracts and the
event bus (zero cross-community imports — machine-enforced by
`tests/test_architecture_boundaries.py`):

| Community | Role |
|---|---|
| C1 Data | Ingestion/normalization (CCXT live, replay CSVs, news failover chain) |
| C2 Research | Adversarial BULL→BEAR→QUANT→MODERATOR debate, hypothesis generation |
| C3 Verification | Evidence-grounded numeric hallucination detection |
| C4 Strategy | Strategy families (momentum, mean-reversion, ML challenger) + opportunity ranking |
| C5 Execution | Durable order management (OMS), broker reconciliation, adapters |
| C6 Observation | Evidence-bound postmortems, prediction ledger scoring |
| C7 Memory | Tiered memory retrieval (incl. vector memory) |
| C8 Evolution | Reflection, challenger trials, reputation |
| C9 Portfolio | Drawdown-tiered allocation proposals, half-Kelly sizing |
| C10 World | Regime/scenario/expectation engines, macro calendar |
| C11 Finance | Double-entry books, FIFO tax lots, CA review gates |

The full module → plane mapping (Experience / Control / Intelligence /
Research / Execution / Deterministic Authority / Data & State / Infrastructure)
lives in [ARCHITECTURE_PLANES.md](ARCHITECTURE_PLANES.md); the planes are
machine-checked invariants, not documentation.

### The deterministic financial kernel

- `core/financial_kernel.py` — durable orders/transitions/fills/cash
  postings/positions, transactional outbox + consumer inbox, seven
  machine-verified invariants (`verify_invariants()`).
- `core/pg_financial_store.py` — the PostgreSQL tier: `SELECT … FOR UPDATE`
  version hops, unique-fill idempotency, outbox claiming with
  `SKIP LOCKED`, refusal to run on an unmigrated schema.
- `core/ibor.py` — the Investment Book of Record, the single source of
  portfolio truth, rebuildable from the immutable fill ledger.
- `core/jetstream_bus.py` — durable streams, at-least-once delivery with
  exactly-once effects, DLQ, honest health.
- `core/safety_plane.py` — capital changes gated on durable state by a
  component no agent can reach; lockouts human-and-role gated.

## Quickstart

Requires Python ≥ 3.11 (CI targets 3.12).

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env    # optional — absent keys mean deterministic mode
```

```bash
# Prove the system stands up: constitution gate + kernel inventory
python -m aios boot

# Run one honest replay over the golden dataset
python -m aios replay --symbols SPY

# Machine-readable summary
python -m aios summary-json --symbols SPY

# Live command center (SSE) after a replay; serves the UI from ui/dist
python -m aios serve
```

`python -m aios replay` **exits non-zero if the audit chain is broken** — a
tampered log is a failed run, not a warning.

### Operator CLI

| Command | Purpose |
|---|---|
| `aios boot` | Constitution SHA gate + kernel inventory (actors, capabilities, authority) |
| `aios replay` | Full honest replay; summary table; refuses a broken chain |
| `aios summary-json` | Machine-readable `RunSummary` |
| `aios serve` | Replay → live command center with SSE |
| `aios events` | Durable event recovery (read log after a cursor) |
| `aios tail` | Independent consumer process following the log (`--follow`, cursor persistence) |
| `aios db status \| migrate` | Versioned financial schema: migrate is the explicit operator action |
| `aios finance recover \| invariants` | Cold-start recovery / verify the seven financial invariants |

## Configuration

All configuration is environment-driven ([.env.example](.env.example)).
Without model keys the system runs in **deterministic mode** — it never
pretends an LLM contributed. Execution is paper/shadow by default;
credentials alone never enable live routing (`AIOS_ALLOW_LIVE_EXECUTION=1` +
audited approval + constitution amendment required).

Backends are optional extras selected by `DATABASE_URL` / NATS URL:

```bash
pip install -e ".[postgres]"   # server-grade financial state plane
pip install -e ".[nats]"       # durable JetStream event backbone
pip install -e ".[all]"        # + ccxt, qdrant
```

## Testing & CI

```bash
# Hermetic suite (SQLite + in-memory bus) — what CI runs by default
PYTHONPATH=. pytest -m "not integration" --timeout=120

# With real services (docker-compose.test.yml stands Postgres + NATS up)
docker compose -f docker-compose.test.yml up -d
AIOS_TEST_PG_DSN=postgresql://... pytest tests/test_v1a2_postgres.py
AIOS_TEST_NATS_URL=nats://127.0.0.1:4222 pytest tests/test_v1a2_jetstream.py

# Gates
ruff check .
mypy --python-version 3.12 --follow-imports=silent core api communities schemas
```

CI (`.github/workflows/ci.yml`) runs: lint, strict types, the hermetic suite,
PostgreSQL parity + 4-process concurrency races, JetStream integration,
frontend typecheck + build, a secrets scan, and a Docker smoke test.

## Repository Layout

```
aios/            CLI entrypoint (boot / replay / serve / events / tail / db / finance)
api/             Read-only HTTP views + SSE server (Experience plane — zero authority)
communities/     C1–C11 domain agents (intelligence plane; proposals only)
core/            Kernel services: financial kernel, stores, bus, risk, config…
kernel/          Identity, capabilities, authority gateway, registries, provenance
research/        Model lab, evaluation gates, walk-forward, integrity linters
schemas/         Pydantic contracts — the only shared vocabulary
simulation/      Replay runner (composition root), paper engine, golden data
frontend/        TypeScript/Vite command center (built to ui/dist)
tests/           467 collected tests; integration suites env-gated
docs/            Architecture, per-community specs, ADRs, runbook, system map
```

## Documentation

- [docs/00_system_map.md](docs/00_system_map.md) — master navigation map
- [CHECKPOINT.md](CHECKPOINT.md) — progress tracker with measured evidence
- [CONSTITUTION.md](CONSTITUTION.md) — the supreme authority (capital limits, authority boundaries, honesty laws)
- [ARCHITECTURE_PLANES.md](ARCHITECTURE_PLANES.md) — module → plane manifest
- [docs/PRODUCTION_RUNBOOK.md](docs/PRODUCTION_RUNBOOK.md) — operator procedures
- [docs/adrs/](docs/adrs/) — architecture decision records

## Production Gates (human-held)

1. Broker testnet credentials + shadow validation on a real venue
2. Tier-1 benchmark completion → formal selection ADRs
3. Licensed real-market data replacing synthetic goldens
4. Tax rules signed by a licensed professional for target jurisdiction(s)
5. Principal records `APPROVE_LIVE_CAPITAL` and amends the constitution via ADR

## License

Proprietary. All rights reserved.
