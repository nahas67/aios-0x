# G240 -- Free exchange testnet options

**Purpose.** G240 (Long Shadow Validation) is `BLOCKED` on "a validated broker testnet
connection". This note answers the part of that which is answerable without a human
decision: **which free sandbox could the code actually use.** It does not provision
credentials, open an account, or place an order.

**Status of the underlying goal.** Still `BLOCKED`. The blockers named in
`docs/goals/CHECKPOINT.md` -- testnet credentials, a full shadow cycle, and five human-held
Phase 5.0 gates -- are untouched by this note. What changes is that the first of them is now
a choice with a documented shortlist rather than an open question.

---

## 1. What the code actually requires

Requirements are read from `communities/c5_execution/adapters.py`, class
`CcxtExecutionAdapter`, not assumed. It makes exactly four ccxt calls:

| call | status | note |
|---|---|---|
| `create_order(symbol, type, side, amount)` | required | order entry |
| `fetch_positions()` | required | **a derivatives API in ccxt, not a spot API** |
| `cancel_all_orders(symbol)` | required | derivatives-oriented |
| `set_sandbox_mode(True)` | optional by intent | see defect #69 -- the guard is ineffective |

Credentials are passed as ccxt's unified keys, `apiKey` and `secret`, with
`enableRateLimit: True`. **No `password` key is passed**, and no private key, which rules
out every venue requiring a passphrase or wallet signing.

Two further constraints from the same file:

* `MAX_ORDER_NOTIONAL_USD = 100.0` -- venue minimum order sizes must sit well below $100.
* Real-money routing is refused in `__init__` regardless of credentials (`CONSTITUTION.md`
  §1). Testnet is the only supported venue.

**The binding discovery is that `fetch_positions` is a derivatives call.** A spot sandbox
cannot satisfy this adapter. "Paper trading" -- the intuitive answer -- does not work:
`alpaca` has a paper API but no `fetch_positions`.

---

## 2. Method, and what it cost to get right

Evidence base is **ccxt 4.5.78 as installed in this repository's virtualenv** -- primary,
offline, and free. Venue-side facts come from each exchange's own documentation.

This analysis took six passes and five of them produced confident wrong answers, which are
recorded because a note showing only the conclusion would hide that:

| pass | did | said | why wrong |
|---|---|---|---|
| 1 | grepped `def fetchPositions(` | 0 of 104 | ccxt's **Python** port is snake_case; camelCase is the JS side |
| 2 | `hasattr(cls, method)` | 104 of 104 | inherited from the base class, where each raises `NotSupported` |
| 3 | `describe()` on the class | "0 qualifying" | it is an **instance** method; the fabricated 0 came from an unchecked `TypeError` |
| 4 | filtered urls on any non-`api` key | 44 qualify | `test` and `referral` exist on **every** exchange -- `referral` is ccxt's own affiliate link |
| 5 | `cls.__dict__` only | 44 qualify | a subclass **inherits** overrides; this wrongly excluded `binanceusdm`, `bybiteu`, `gateeu` |
| 6 | **MRO below `ccxt.Exchange`, comparing `urls['test']` hosts to `urls['api']` hosts** | **52 provide all three; 35 route to a non-production host** | correct |

Pass 5 is the one worth remembering: the false rows were exactly the exchanges a person
would reach for first.

---

## 3. Ruled out, and why

### By ccxt's own class layout (measured)

A required call is genuinely absent, so the adapter raises `NotSupported` at runtime:

* **missing `cancel_all_orders`:** `okx`, `hyperliquid`, `dydx`, `blofin`
* **missing `fetch_positions`:** `alpaca`, `bitso`, `blockchaincom`, `coinbaseexchange`,
  `hollaex`, `ndax`
* **missing both:** `gemini`

**`okx` deserves emphasis.** It is one of the largest derivatives venues, has an excellent
demo-trading environment, and ccxt's `okx` overrides `set_sandbox_mode` correctly to send an
`x-simulated-trading: 1` header. It is excluded on two independent grounds: the missing
call, and `requiredCredentials` demanding a `password` this adapter never passes. Any
shortlist built from "which exchanges have a testnet" would have put it at the top.

### By credential model (measured via `requiredCredentials`)

| venue | required | compatible with the adapter as written |
|---|---|---|
| `okx` | apiKey, secret, **password** | no |
| `bitget` | apiKey, secret, **password** | no |
| `hyperliquid` | **privateKey, walletAddress** | no |
| `paradex` | **privateKey, walletAddress** | no |
| `deribit` | apiKey, secret | **yes** |
| `krakenfutures` | apiKey, secret | **yes** |
| `gate` | apiKey, secret | **yes** |

`bitget` is additionally ruled out on its own documentation, which states **KYC is needed**
for demo trading.

### Not disqualifying, but worth knowing

* **16 exchanges provide all three calls yet have no `test` host wired in ccxt at all** --
  including `bitget`, `mexc`, `kucoin`, `htx`, `kraken` and `weex`. That is a gap in ccxt's
  declaration, not proof the venue has no sandbox. Recorded as unverified, not ruled out.
* **`weex` is actively hazardous** -- see defect #70.
* **`poloniex`**: ccxt's `urls['test']` has only a `spot` key; no futures on its sandbox.

---

## 4. The shortlist that survives

35 exchanges clear the ccxt-side checks. Ten are substantial venues with a dedicated
derivatives sandbox:

| ccxt id | sandbox host(s) | activation | notes |
|---|---|---|---|
| `deribit` | `test.deribit.com` | `set_sandbox_mode(True)` works unmodified | perps + options; **no KYC on testnet**; same rate limits as production |
| `krakenfutures` | `demo-futures.kraken.com` | `set_sandbox_mode(True)` works unmodified | demo is **completely separate and needs no existing credentials**; email+password auto-generated |
| `gate` / `gateeu` | `api-testnet.gateapi.io` | `set_sandbox_mode(True)` works unmodified | futures, delivery and options all declared on the testnet |
| `binance` / `binanceusdm` | `testnet.binancefuture.com`, `testnet.binance.vision`, **plus** `demo-fapi.binance.com` | **`enable_demo_trading(True)`** -- `set_sandbox_mode` routes to a legacy host the current docs no longer name | widest instrument set; docs explicitly waive KYC for demo |
| `bybit` | `api-testnet.*`, **plus** `api-demo.*` | **`enable_demo_trading(True)`** -- `set_sandbox_mode` routes to the legacy V3 testnet | documented demo covers Place Order, Cancel All and Positions |
| `bingx` | `open-api-vst.*` | `set_sandbox_mode(True)` | VST = virtual sandbox; venue's own API docs never mention it, so unverified |
| `bitmex` | `testnet.bitmex.com` | `set_sandbox_mode(True)` | |
| `deribit` / `phemex` / `delta` / `btse` | `testnet-api.phemex.com`, `testnet-api.delta.exchange`, `testapi.btse.io` | `set_sandbox_mode(True)` | lower confidence on signup terms |

### Order sizes against the $100 cap (measured live on the sandboxes)

| venue | instrument | minimum notional | within cap? |
|---|---|---|---|
| `deribit` testnet | `BTC-PERPETUAL` | **$10** (1 contract, `contract_size` 10) | yes |
| `gate` testnet | `BTC_USDT` | ~**$8.5** | yes |
| `gate` testnet | `ETH_USDT` | ~**$27** | yes |
| `gate` testnet | `SOL_USDT` | ~**$118** | **no -- exceeds the cap** |
| `binance` demo | `BTCUSDT` | **$50** | yes |
| `binance` demo | `ETHUSDT` / `SOLUSDT` / `DOGEUSDT` | $20 / $5 / $5 | yes |

---

## 5. A caution that bears on the goal, not just the plumbing

**Deribit publishes this about its own testnet:** *"Clients should avoid using the testnet as
a realistic simulation of live market behavior, particularly when testing trading bots or
automated strategies."* Binance similarly notes demo *"does not exactly replicate the actual
live trading environment"* -- order-book depth, fills and chart data differ.

This matters more than it first appears. G240 is **Long Shadow Validation**, whose purpose is
validating that behaviour holds against realistic conditions. The easiest venue to connect
(Deribit: no KYC, no code change, $10 minimum) is explicitly documented as **not** a
realistic simulation. That is a real tension in the goal's own definition, and it is worth
putting to whoever owns the decision rather than resolving silently by picking the easiest
connection.

Kraken's demo makes the opposite claim -- *"the demo API code is identical to production in
terms of feeds, endpoints, and response structure"* -- though its liquidity realism is not
addressed.

---

## 6. Recommended sequence

1. **Fix the adapter before choosing a venue** (defects #69, #70). Make sandbox activation a
   per-venue configuration value rather than a hard-coded `set_sandbox_mode(True)`, since
   Binance and Bybit both need `enable_demo_trading` instead. Replace the `hasattr` guard
   with a check that the exchange declares a sandbox, and refuse when it does not.
2. **Deribit testnet first** for plumbing: no KYC, credentials are exactly `apiKey`+`secret`,
   sandbox mode works unmodified, $10 minimum.
3. **Binance demo second** as the higher-fidelity cross-check, after the activation change.
4. **Before writing any of it**, run a three-call smoke test: `load_markets()` →
   `fetch_balance()` → `fetch_positions()`. `fetch_positions()` is the one that matters and
   the one no remote check can substitute for, since it needs credentials.

---

## 7. Explicit unknowns

Not verified, and not to be treated as fact:

1. **Whether `fetch_positions()` actually succeeds on any of these sandboxes.** Endpoints
   are documented and hosts answer, but every private call needs credentials. This is the
   highest-value thing to test first.
2. **KYC requirements for sandbox keys** at `gate`, `bybit`, `okx`, `phemex`, `kraken`.
   Binance and Deribit are the only two confirmed.
3. **`amount` semantics are not portable.** Deribit perps are inverse and `amount` is in
   **contracts** (1 = $10), not base units; Binance is linear (`amount` in BTC). A single
   hard-coded `amount` works on one venue and is rejected on the other.
4. **Region restrictions.** Binance demo is *"available to users in certain countries and
   regions only"* and geo-blocks by IP; a US IP receives HTTP 451.
5. **Kraken's demo JSON API reachability** could not be confirmed -- unauthenticated requests
   returned an HTML app shell, most likely CDN/geo routing from the research host.
6. **Sandbox market-data realism** for every venue except Binance and Deribit, which are the
   only two publishing warnings either way.
7. **`bingx`, `woox`, `phemex`, `cryptocom`, `hashkey`, `bullish` and the DEX-like venues:**
   a ccxt `urls['test']` exists and in several cases the host answers, but no sandbox signup
   or KYC documentation was found, and BingX's public API docs contain no mention of
   demo/testnet/VST. Unverified leads only.
8. **ccxt version.** The mechanism claims here were checked against the installed 4.5.78;
   venue-side research read `ccxt/master`. `enable_demo_trading` and Binance's `urls['demo']`
   were confirmed present in 4.5.78, but a future upgrade should re-run section 3.

---

## 8. Sources

**Primary, local:** ccxt 4.5.78 at `.venv-fresh/Lib/site-packages/ccxt` -- class MRO and
`describe()` for every capability and url claim in sections 1 and 3.

**Primary, venue documentation** (quoted in section 4):
Deribit testnet (`support.deribit.com/hc/en-us/articles/28685393662365-Deribit-Testnet`,
`docs.deribit.com/articles/deribit-quickstart`); Binance USDS-M futures
(`developers.binance.com/docs/derivatives/usds-margined-futures/general-info`); Kraken
Futures demo (`docs.kraken.com/exchange/guides/futures/introduction`); Gate APIv4
(`gate.com/docs/developers/apiv4/en/`); Bybit V5 demo
(`bybit-exchange.github.io/docs/v5/demo`); OKX docs-v5 "Demo Trading Services";
Bitget classic demo (`bitget.com/docs/classic/demo-trading/rest-api`).

**ccxt reference:** `github.com/ccxt/ccxt/wiki/Manual.md`.
