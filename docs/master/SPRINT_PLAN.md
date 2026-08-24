# AIOS-0X Sprint Plan: Close the Credibility Gaps
Version 1.0.0 | 2026-08-24

## WHERE WE ARE

Strengths (moat): hash-chained audit, double-entry accounting, tax/CA pipeline,
constitution boot-pinning, RBAC console, prediction calibration, postmortem
engine, kill-switch lockout, reconciliation, hallucination detection, challenger
governance, compliance surveillance. Zero competitors have any of these.

Weaknesses: no broker execution, no Docker, no benchmark, no real-time
updates, no ML models, no RAG, no personality agents, no strategy evolution.

Sources: COMPETITIVE_ANALYSIS.md + OSS_INTEGRATION_REPORT.md

## SPRINT 1 - CREDIBILITY (3-4 days)

### 1.1 SPY Benchmark in P&L workspace
Gap: P&L numbers are meaningless without vs-buy-and-hold.
Steal: FinRL-Trading BacktestResult.benchmark_metrics
Do:
- Fetch SPY daily closes for replay window via CCXT or yfinance
- Compute buy-and-hold return over same period
- Add benchmark_return_pct and alpha_pct to RunSummary
- Display: "Your P&L: +$406 | SPY: +12.3% | Alpha: -11.9%"
- Add benchmark line on equity chart (gray)
Accept: P&L workspace shows alpha vs SPY; chart has benchmark line.

### 1.2 Docker Compose
Gap: No docker compose up deployment.
Steal: FinRL-Trading Dockerfile + docker-compose.yml
Do:
- Dockerfile: multi-stage, python:3.14-slim, non-root user
- docker-compose.yml: app + optional qdrant + optional nats
- Volume mounts: data/ for SQLite + golden CSVs
- Health check wired to /api/v1/health
- .dockerignore
Accept: docker compose up -d starts command center on port 8787.

### 1.3 Telegram kill-switch + fill alerts
Gap: Kill switch fires at 3am, operator has no idea.
Steal: Samvid telegram_alerts.py pattern
Do:
- core/notifications.py: TelegramNotifier (Bot API sendMessage)
- Settings: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (env, optional)
- Wire: kill switch, reconciliation failure, lockout, drawdown tiers
- Fire-and-forget (never block trading loop)
Accept: Kill switch fires, Telegram message arrives within 5s.

### 1.4 Paper graduation criteria display
Gap: Data exists but "is this ready for live?" is not surfaced.
Steal: Thales graduation (Sharpe>1.5, 50+ trades, WR>45%, DD<20%)
Do:
- PaperGraduation model: criteria list with current + threshold + pass/fail
- Compute from RunSummary: Sharpe, trade count, win rate, max DD
- Display in P&L workspace as a checklist with green/red indicators
- Gate: all criteria must pass before "READY FOR LIVE" badge shows
Accept: P&L workspace shows graduation checklist with live pass/fail.

## SPRINT 2 - INTELLIGENCE DEPTH (5-7 days)

### 2.1 Investor personality agents in debate
Gap: 1 bull + 1 bear is thin. Swarm Trader has 13 personalities.
Steal: crewAI role/goal/backstory pattern; Swarm Trader personalities
Do:
- Add 4 personality prompts to PromptRegistry:
  value_investor (Buffett: moats, margin of safety)
  growth_investor (Wood: disruption, TAM expansion)
  contrarian (Burry: deep value, against consensus)
  macro_analyst (Druckenmiller: rates, liquidity, geopolitics)
- Debate flow: personalities submit independent assessments BEFORE bull/bear
- Moderator synthesizes with personality-weighted context
Accept: Debate transcript shows 4+ personality assessments before bull/bear.

### 2.2 RAG news ingestion into Qdrant
Gap: Vector memory exists but nothing feeds it from news.
Steal: FinGPT_RAG multisource_retrieval pipeline
Do:
- Finnhub fetch -> embed via HashingEmbedder -> upsert to Qdrant "news"
- At debate time: retrieve top-k relevant news for symbol
- Inject into moderator context (same as MEMORY turn, different collection)
Accept: Debate transcript shows news context turn when relevant news exists.

### 2.3 SSE live updates (replace 5s polling)
Gap: UI polls every 5s; real trading needs push.
Steal: twelvedata TDWebSocket self-heal pattern (adapted to SSE)
Do:
- Add SSE endpoint /api/v1/stream to stdlib server
- Stream: executive snapshot every 5s + event notifications on publish
- UI: EventSource instead of setInterval
- Reconnect with exponential backoff on connection loss
Accept: UI updates without polling; reconnects after server restart.

### 2.4 AutoResearch scheduled challenger
Gap: Challenger trials exist but require manual triggering.
Steal: qlib RollingStrategy + Swarm Trader AutoResearch pattern
Do:
- Parameterize: RR ratio, stop distance, sentiment threshold, debate rounds
- Scheduled run: mutate params -> run replay -> compare vs champion
- Persist results as CHALLENGER_EVALUATION events
- Surface in UI: "AutoResearch found 2 improvements pending review"
Accept: System autonomously proposes parameter changes with evidence.

## SPRINT 3 - PRODUCTION READINESS (5-7 days)

### 3.1 Broker testnet validation
Gap: CCXT execution suite is code-complete but unvalidated.
Do:
- Binance testnet account (free signup)
- Validate: market order, cancel, positions, reconciliation
- Run supervised replay against testnet
Accept: Testnet fill appears in our ledger with correct reconciliation.

### 3.2 Short selling support
Gap: PaperEngine supports SELL but no margin/borrow model.
Steal: Lean IShortableProvider, qstrader long_short.py order sizer
Do:
- Borrow rate lookup (hardcoded 5% annual for crypto CFDs initially)
- Margin requirement tracking in PaperEngine
- Short position P&L calculation (already works via side-aware ObservationAgent)
Accept: SELL trade opens short position with borrow cost accrued daily.

### 3.3 Constitution amendment for live capital
Gap: CONSTITUTION section 1 forbids live routing.
Do:
- Draft ADR: evidence from testnet validation + paper graduation metrics
- Human principal reviews and approves
- Update CONSTITUTION.md, re-pin hash, commit
- Record APPROVE_LIVE_CAPITAL control action
Accept: Live routing unblocked by governance process, not by code bypass.

## SPRINT 4 - SCALE AND DEPTH

### 4.1 ML price prediction model
Steal: qlib model zoo, FinGPT Forecaster prompt format
- Start with simple: rolling linear regression on momentum + volatility
- Add to StrategyAgent as third family alongside momentum + mean_reversion
- Score via prediction ledger (same Brier calibration as other families)

### 4.2 Multi-asset expansion
- Alpaca paper for equities (free, same API as live)
- Add equity-specific compliance rules (PDT rule, settlement T+1)
- Portfolio governor: cross-asset class exposure tracking

### 4.3 Advanced order types
- Limit orders with GTC/Day TimeInForce
- Bracket orders (entry + stop + target as atomic unit)
- Trailing stop (activation price + trail amount)

### 4.4 Dashboard customization
- Widget show/hide/reorder per user
- Saved layouts (localStorage)
- Default layouts: Executive, Trading, Risk, Research

## DEPENDENCY GRAPH

Sprint 1 (Credibility) -----> Sprint 2 (Intelligence) -----> Sprint 3 (Production)
  1.1 Benchmark                   2.1 Personalities              3.1 Testnet
  1.2 Docker                      2.2 RAG News                   3.2 Short Selling
  1.3 Telegram                    2.3 SSE Live                   3.3 Constitution
  1.4 Graduation                  2.4 AutoResearch
                           |
                           v
                      Sprint 4 (Scale)
                        4.1 ML Models
                        4.2 Multi-asset
                        4.3 Order types
                        4.4 Customization

## SUCCESS METRICS (from competitive analysis)

After Sprint 1: "Looks like a serious project" - Docker, benchmark, alerts
After Sprint 2: "Intelligence depth matches TradingAgents" - personalities, RAG, evolution
After Sprint 3: "Ready for controlled live" - testnet validated, constitution amended
After Sprint 4: "Competitive with Nexus/Thales" - ML models, multi-asset, advanced orders
