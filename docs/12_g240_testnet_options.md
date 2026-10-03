# G240 -- Free exchange testnet options

**Purpose.** G240 (Long Shadow Validation) is `BLOCKED` on "a validated broker testnet
connection". This note answers the part answerable without a human decision: **which free
sandbox could the code actually use.** It provisions nothing, opens no account, places no
order, and does not move G240 past `BLOCKED`.

**Status of the goal.** Still `BLOCKED`. Credentials, a full shadow cycle, and the five
human-held Phase 5.0 gates are untouched. What changes is that the first of them is now a
choice with a documented shortlist rather than an open question.

**Provenance rule for this note.** Every figure is tagged *measured* (probed here,
2026-10-02), *documented* (quoted from a source opened here, with the retrieval method), or
*unverified*. A claim inherited from a research lane that I could not independently reach is
marked as such rather than presented as fact. Two known cases: Gate's entire doc site
returns HTTP 403 to automated requests, and Binance's Spot demo-mode page returns HTTP 202.

**Evidence base (measured 2026-10-02, not recalled).** Primary, local: ccxt in
`.venv-fresh` (probed as 4.5.78) driven through ccxt itself with the adapter's own
activation calls. `requirements.lock:15` pins `ccxt==4.5.74`; PyPI latest is 4.5.85. The
4.5.74 wheel was downloaded and every load-bearing mechanism fact below was confirmed in
**both** versions, so the conclusions are version-robust and the locked version is the
baseline. Primary, remote: unauthenticated public + private-route probes against each
sandbox. Authoritative spec: Deribit's OpenAPI
(`https://docs.deribit.com/specifications/deribit_openapi.json`). Venue docs via raw HTTP
and CMS endpoints; Gate's web docs returned HTTP 403 to all automated requests.

---

## 1. What the code actually requires

Read from `communities/c5_execution/adapters.py:269`, class `CcxtExecutionAdapter`.

| requirement | consequence |
|---|---|
| `create_order`, `fetch_positions`, `cancel_all_orders` | **`fetch_positions` is a derivatives call.** No spot sandbox qualifies. |
| credentials as `apiKey` + `secret` only | every venue needing `password`, `privateKey`, `walletAddress`, `accountId` is out |
| `MAX_ORDER_NOTIONAL_USD = 100.0` (`adapters.py:281`) | venue minimums must sit below $100 |
| live routing refused in `__init__` (`adapters.py:312`) | `CONSTITUTION.md:22` -- testnet is the only constructible venue |
| `_venue_symbol` = `symbol_map.get(symbol, symbol)` (`adapters.py:335`) | caller must supply **ccxt unified symbols**; `StrategySpecification.symbol` documents `"BTC/USD"` (`schemas/contracts.py:107`), which ccxt cannot resolve |

### The funnel (104 exchanges, measured)

| step | count |
|---|---|
| all three calls defined **below** `ccxt.Exchange` | **52** |
| ...and credentials exactly `apiKey`+`secret` | **34** |
| ...and `urls['test']` is a genuinely different host | **24** |
| `urls['test']` is `null` (ccxt declares no sandbox) | 16 |
| `urls['test']` **equals the production host** | 1 -- `weex` |
| need more than `apiKey`+`secret` despite a good sandbox | 11 -- `apex`, `coinbaseinternational`, `derive`, `extended`, `grvt`, `lighter`, `modetrade`, `nado`, `pacifica`, `paradex`, `woofipro` |

### Method, and what it cost to get right

The probe failed **four** times before it was right, and each failure produced a confident
wrong number -- which is why the method is written down at all:

1. `hasattr(exchange, "set_sandbox_mode")` gives **104/104** (inherited from
   `ccxt.base.exchange.BaseExchange`, where each raises `NotSupported`). Only **20**
   exchanges actually override it, and finding that required walking the MRO *and breaking
   before the base* -- a generator that forgot the `break` also returned 104.
2. Collecting class names where method names were needed gives **0/104**.
3. Reading nested `urls` dicts as strings reports Gate's sandbox as **absent**.
4. Dimensional: `amount = notional / contractSize` is wrong for a linear contract.

---

## 2. Shortlist -- what was actually proved

All eight were driven **through ccxt itself** with the adapter's activation call, ending at
each venue's auth boundary -- as far as one gets without credentials.

| venue | activation (verified) | min notional (measured live) | verdict |
|---|---|---|---|
| **binance** (`binanceusdm`) | `enable_demo_trading(True)` -> `demo-fapi.binance.com` | $50 BTC / $20 ETH / **$5 SOL** | **primary** -- 4511 markets, headroom under the cap |
| **bybit** | `enable_demo_trading(True)` -> `api-demo.bybit.com` | $5 min-notional; `minOrderQty` 0.001 BTC ~**$85** binds | **fidelity cross-check** -- best measured realism |
| **deribit** | `set_sandbox_mode(True)` -> `test.deribit.com` | **$10** (`BTC/USD:BTC`, `contract_size` 10) | easiest plumbing; worst venue for defect #71 |
| **gate** | `set_sandbox_mode(True)` -> `api-testnet.gateapi.io` | $8.48 BTC / $27.03 ETH / $0.94 DOGE / **$118.69 SOL exceeds cap** | 6595 markets incl. options; `amount` is integer contracts |
| krakenfutures | `set_sandbox_mode(True)` | -- | **do not build on this** -- see below |
| bitmex | `set_sandbox_mode(True)` | ~$96 (1300 contracts) | only 15 markets; contract unit in satoshis |
| bingx | `set_sandbox_mode(True)` -> `open-api-vst` | ~$93 | prices track live; sandbox undocumented publicly |
| okx | header-only (`x-simulated-trading: 1`) | ~$8.48 | **out** -- `has['cancelAllOrders'] is False`, verified against the V5 docs |

**Kraken Futures demo is measured broken from here, and documented unsuitable regardless.**
Unauthenticated `demo-futures.kraken.com/derivatives/api/v3/accounts` returns HTTP 200 with
an HTML app shell, and ccxt `load_markets()` returns **zero markets instead of raising** --
the failure surfaces later as `BadSymbol`, far from the cause. Production
`futures.kraken.com/derivatives/api/v3/instruments` returned clean JSON on the same probe, so
this is specific to the demo host, not the research path. Independently, Kraken documents at
`docs.kraken.com/home/guides/quickstart.md`: *"The Futures demo environment **resets
periodically. It is intended for integration validation, not persistent backtesting.**"*
(verified verbatim 2026-10-02; the sibling `exchange/guides/futures/introduction.md` does
**not** contain this sentence, so the citation is to the quickstart specifically). A
resets-periodically demo is incompatible with a **long** shadow cycle. Its support page
(updated 2026-07-07) also carries an unresolved decommissioning notice for
`demo-futures.kraken.com` that cannot be reconciled with the live docs -- and that notice
came from a research lane, **not** from a page I opened, so it is recorded as unverified.
Not recommended regardless of reachability.

### Ruled out, with the reason

- **`weex` -- actively hazardous.** `set_sandbox_mode(True)` succeeds, sets
  `isSandboxModeEnabled = True`, and leaves the active host on **`api-spot.weex.com`**.
  The constitutional rails are satisfied *because* `testnet` is true. It also needs a
  `password` the adapter never passes.
- **`okx` -- no backing endpoint.** `has['cancelAllOrders'] is False` is **measured** here.
  That ccxt flag is accurate rather than a ccxt bug, and the research lane's enumeration of
  the V5 trade routes (no general cancel-all-orders; `mass-cancel` is options-only with MMP
  privilege; `cancel-all-after` is a delayed countdown, not symbol-scoped) is consistent
  with it -- but the route enumeration is **documented, not independently re-opened here**.
  OKX also needs a KYC-verified account per its API Agreement §2.2, which its own changelog
  exempts only from the KYC-L2 *ordering* bar.
- **`poloniex` -- sandbox is spot-only** (`sand-spot-api-gateway.poloniex.com`) and the host
  does not resolve.
- **Coin-margined Binance variants** (`binancecoinm`, `binanceus`) -- clear every mechanical
  check; excluded on the constitution's *no margin* posture, not on ccxt.

---

## 3. The finding that reframes the goal

**Prices are not the problem. The book is.** BTC, same moment, 2026-10-02:

| venue | sandbox | production | apart |
|---|---|---|---|
| Deribit `BTC-PERPETUAL` | 84,761.00 | 84,759.00 | 0.002% |
| Binance `BTCUSDT` | 84,755.40 | 84,722.60 | 0.039% |
| Bybit `BTCUSDT` | 84,705.50 | 84,705.50 | **0.000%** |
| Gate `BTC_USDT` | 84,753.00 | 84,686.70 | 0.078% |

| order book, top 50 levels | sandbox | production |
|---|---|---|
| Deribit bid notional | $1.49 **trillion** (top level a round `1,000,000`) | $305 billion |
| Binance spread | 3.60 (0.0042%) | 0.10 (0.0001%) -- **36x wider** |
| Binance bid notional | $1.06 billion | $1.90 million -- **~500x deeper** |

Deribit says so in writing (verified verbatim 2026-10-02 via the Zendesk JSON API; the HTML
page 403s to automated clients): *"Clients should avoid using the testnet as a realistic
simulation of live market behavior, **particularly when testing trading bots or automated
strategies.**"* Binance's demo FAQ, retrieved via its own CMS endpoint, admits *"There may
be discrepancies in the chart data, **actual order book pricing, and trade order
execution** when compared to the live trading environment."* The stronger line often quoted
for it -- *"Realistic market data is not equal to 'real' market data"* -- is on the **Spot**
demo-mode page, which returned HTTP 202 (a JS challenge) to an automated fetch here, so it is
**not** treated as verified. Bybit's demo is the fidelity pick: `lastPrice` was **byte-identical** to mainnet on re-probe
(85,762.10 both), and the top-of-book sizes tracked production closely (1.960/3.130/0.002
demo vs 2.824/3.130/0.002 prod). But it keeps demo orders only **7 days** and refreshes the
account after **30 days** without access, clearing its data.

A free sandbox validates **plumbing, governance, the reconciliation path and the capital
firewall**. It cannot validate **execution realism** -- depth is synthetic, fills are not the
venue's. Combined with the **$100 cap** forcing near-dust orders, "long shadow validation
against realistic conditions" is not achievable on a free sandbox as written. That is a
question for whoever owns the decision.

**`amount` is not portable -- measured, not asserted.** The same ~$100 of BTC exposure needs,
per venue, from each sandbox's own market metadata (`contractSize`, `amountPrecision`,
`limits.amount.min`) plus a live ticker:

| venue | symbol | convention | `amount` | precisionified | resulting notional |
|---|---|---|---|---|---|
| binance | `BTC/USDT:USDT` | linear, base units | 0.00118 | `0.0011` | ~$93 |
| bybit | `BTC/USDT:USDT` | linear, base units | 0.00118 | `0.001` | ~$85 |
| bingx | `BTC/USDT:USDT` | linear, base units | 0.00118 | `0.0011` | ~$93 |
| deribit | `BTC/USDC:USDC` | linear, base units | 0.00118 | `0.0011` | ~$93 |
| deribit | `BTC/USD:BTC` | **inverse, USD per contract** | 10.0 | `10` | **$100** |
| gate | `BTC/USDT:USDT` | **integer contracts** (`minQty` 1, `quanto_multiplier` 0.0001) | 11.81 | `11` | ~$93 |
| bitmex | `BTC/USDT:USDT` | **integer contracts** (`contractSize` 1e-6) | 1351.4 | `1300` | ~$96 |

A **1.3-million-fold spread** for one economic intent (0.00118 to 1300). `0.0011` and `10` are
not interchangeable, and on gate/bitmex a sub-1 value is rejected outright rather than
rounded -- `InvalidOrder: amount must be greater than minimum amount precision`. Deribit's
testnet carries **both** conventions at once (`BTC/USD:BTC` inverse and `BTC/USDC:USDC`
linear), so even one venue needs the branch.

---

## 4. Venue notes that constrain the choice

- **Deribit KYC: explicitly NOT required.** *"Verification is not required on the testnet.
  Please do not upload any documents"* and *"KYC processes are not supported on the testnet
  environment."* Registration mirrors production; testnet accounts are separate. Its article
  also states *"Both the production and test environments use the same default Rate Limits"*
  and that both are hosted in LD4, adding the caveat *"no formal latency comparison has been
  made"*. `min_trade_amount` is USD-denominated for inverse perps: BTC-PERPETUAL $10
  (= 1 contract), ETH-PERPETUAL $1. Testnet and production instrument specs re-verified
  identical today for both (`contract_size`/`min_trade_amount`/`lot_size`/`tick_size`).
- **Deribit `size` sign is undocumented -- read `direction`.** **Measured:** the OpenAPI
  `position.size` description never mentions a sign -- *"Position size for futures size in
  quote currency (e.g. USD), for options size is in base currency"* -- while `direction` is a
  separate enum (`buy`/`sell`/`zero`) and both are `required`. **From the research lane, not
  independently reproduced here:** in practice `size`/`size_currency` arrive signed (negative
  for shorts; cf. ccxt issue #16606, where the maintainer applied `string_abs` because the raw
  value was negative). Treat `direction` as authoritative, and assert
  `sign(size) == (-1 if direction == "sell" else +1)` at the boundary rather than trusting
  either alone (defect #71).
- **Binance demo KYC is contested.** **Documented, verified via the CMS endpoint:** the demo
  FAQ states *"Users who have not completed identity verification (KYC) or do not have a
  Futures Account can access Demo Trading"*, which contradicts the live API-management page's
  *"You will not be able to create an API Key if KYC is not completed."* Unresolved -- needs a
  hands-on check, most likely explained by demo keys being minted in the demo context. No
  official statement found that a demo key is rejected by `fapi.binance.com` (real-fund blast
  radius **unverified**); test in a throwaway account first. Country list unpublished (*"in
  certain countries and regions only"*). The lane also reported demo `MAX_NUM_ORDERS` diverging
  from live on some symbols -- plausible and unremarkable, **not** reproduced here.
- **Gate testnet KYC and realism: NOT VERIFIED -- the whole doc site is unreachable.** All
  `gate.com`/`gate.io` doc routes 403 to automated requests. **Measured:** reachable and
  route-verified (`MISSING_REQUIRED_HEADER`, i.e. the auth layer, not 404) for place-order,
  positions, cancel-all and accounts; perps live (63 contracts); options and spot market data
  live; delivery futures timed out twice; BTC-settled futures `NOT_FOUND`. From the lane, not
  reproduced: a second host alias (`fx-api-testnet.gateio.ws`) and the perps/options/spot
  market-type map. **A human browser session is the only way to close this row.**
- **Bybit demo is the fidelity pick with a retention trap.** **Documented and verified:**
  *"Identity Verification is not required for Demo Trading"*, demo is *"an independent account
  ... with its own user ID"*, *"Orders generated in demo trading keep 7 days"*, and the account
  *"will be refreshed and its data will be cleared"* after 30 days without access. **Measured:**
  `api-demo.bybit.com` is reached via `bybit`'s **overridden** `enable_demo_trading` (it reads
  `urls['demotrading']`, so no manual URL patch is needed) with 3793 markets loaded and
  `lastPrice` byte-identical to mainnet. The FAQ's *"simulated environment that mimics real
  trading conditions"* is a claim about the environment, not a guarantee about depth or fills.

---

## 5. Recommended sequence

1. **Fix the adapter before choosing a venue** (defects #69--#72). Make sandbox activation a
   per-venue configuration value, replace the `hasattr` guard with a check the exchange
   declares a sandbox, branch `positions_snapshot` on `side`, and pass a `clientOrderId`.
2. **Binance demo (`binanceusdm` + `enable_demo_trading`) first** for plumbing: widest
   coverage, SOLUSDT at ~$5.93 leaves headroom under the cap.
3. **Bybit demo second** as the higher-fidelity cross-check, accepting the retention limits.
4. **Deribit testnet third** for the no-KYC path -- after the #71 fix, since inverse perps are
   where the sign defect bites hardest.
5. **Before writing any of it**, run a three-call smoke test once credentials exist:
   `load_markets()` -> `fetch_balance()` -> `fetch_positions()`. `fetch_positions()` is the
   one that matters and the one no remote check substitutes for.

---

## 6. Explicit unknowns

Ordered by how much each one would change the recommendation.

1. **`fetch_positions()` has never been executed** -- every private call needs credentials, so
   this is the single highest-value first test and the only thing standing between this note
   and a validated connection. Closest evidence: unauthenticated calls reach the auth layer on
   each sandbox rather than 404ing (`deribit` returns `code 13009 invalid_token` with
   `"testnet": true`; Gate `MISSING_REQUIRED_HEADER: Timestamp`; Binance/Bybit `401 -2014`).
2. **Binance demo real-fund blast radius** -- no official statement found that a demo key is
   rejected by `fapi.binance.com`. Unverified, and the one unknown with money attached.
3. **Binance demo key creation without KYC** -- documented FAQ and API-management page
   contradict each other; needs a hands-on check.
4. **Gate testnet KYC and realism** -- genuinely unknown; the entire doc site 403s automated
   requests, so only a human browser session closes it.
5. **Deribit `size` sign convention** -- undocumented in the OpenAPI spec. The recommendation
   does not depend on it (defect #71 says read `direction` and assert agreement), but a smoke
   order would settle it.
6. **ETH-PERPETUAL `lot_size: 10` vs `min_trade_amount: 1`** on Deribit -- both measured today
   and identical test vs production, but the docs describe `lot_size` as fee-counting only,
   and a $1 floor is suspiciously small. One smoke order resolves it.
7. **Kraken demo decommissioning notice** -- from the research lane, page not opened here.
   Kraken is not recommended regardless, so this does not gate anything.

**Claims inherited from a research lane and NOT independently reproduced here** (each is
consistent with what was measured, but none should be treated as first-hand): the OKX V5
trade-route enumeration, the Kraken decommissioning notice, Binance demo `MAX_NUM_ORDERS`
divergence, Gate's second host alias and market-type map, and the claim that Deribit's `size`
arrives signed.

---

## 7. Sources

**Primary, local:** ccxt 4.5.78 in `.venv-fresh` (class MRO, `describe()`, `set_sandbox_mode`
/ `enable_demo_trading` sources); ccxt 4.5.74 wheel (mechanism facts re-verified);
PyPI `https://pypi.org/pypi/ccxt/json` (4.5.74 uploaded 2026-08-17, 4.5.78 on 2026-09-07,
latest 4.5.85). **Authoritative spec:** Deribit OpenAPI
`https://docs.deribit.com/specifications/deribit_openapi.json` (`position.size`,
`position_direction`, `contract_size`, `min_trade_amount` descriptions). **Venue docs:**
Deribit testnet article via Zendesk JSON API (KYC exemption + realism warning, verbatim
2026-10-02); Binance USDS-M futures `general-info` + demo FAQ `9be58f73e5e14338809e3b705b9687dd`
+ Spot demo-mode `general-info`; Bybit V5 demo `bybit-exchange.github.io/docs/v5/demo` +
FAQ-Demo-Trading (2025-11-25) + transact-parameters; OKX docs-v5 Demo Trading Services +
`59113`/changelog 2026-04-07 + API Agreement §2.2; Kraken `docs.kraken.com/exchange/guides/futures/introduction.md`,
`home/guides/quickstart.md`, `futures/ratelimits.md`, support `360024809011` (2026-07-07);
Gate `gateio/rest-v4` README + `gateapi-python/docs/FuturesApi.md`. **Live probes:**
Deribit `public/test`, `get_instruments`, `ticker`, `get_order_book` (test + prod);
Binance `demo-fapi`/`fapi` `ping`, `exchangeInfo`, `depth`, `ticker/price`, `positionRisk`,
`allOpenOrders` (auth-layer 401s); Bybit `api-demo`/`api` `instruments-info`, `tickers`;
Gate testnet/prod `futures/usdt/contracts`, `tickers`, `positions`, `orders`, `accounts`;
Kraken futures prod `instruments`, `openpositions`, `accounts`; ccxt `v4.5.78` tag for
`bybit.py` (`demotrading` key + override), `binanceusdm.py` (inherits `demo`), `okx.py`
(`cancelAllOrders: False`).
