# AIOS Specification 1.2: Community 1 Specification (Data Acquisition)

## Document Control
- **Document Version**: 1.0.0
- **Status**: Approved Specification
- **Target System**: AIOS - Community 1 (Data Acquisition)
- **Author**: AIOS System Architecture Team

---

## 1. Community Purpose & Responsibilities

### 1.1 Primary Objective
Community 1 (C1) acts as the continuous data gateway for the entire AIOS ecosystem. Its primary objective is to ingest, clean, normalize, timestamp, and route multi-asset market prices, order book dynamics, financial news, macro indicators, and sentiment feeds into standardized events.

### 1.2 Core Responsibilities
- **Multi-Asset Ingestion**: Ingest high-frequency and bar data across Crypto, Stocks, Forex, and Commodities from multiple exchanges and feeds.
- **Data Deduplication**: Eliminate duplicate news headlines, duplicate tick ticks, and overlapping candle windows across concurrent data streams.
- **UTC Timestamp Standardization**: Enforce UTC ISO 8601 formatting for every incoming tick and bar to guarantee chronological alignment across disparate global sources.
- **Noise & Outlier Filtering**: Detect and flag abnormal price spikes, zero-volume anomalies, or malformed data feeds before downstream distribution.
- **Publish Routing**: Package clean data into immutable `MarketDataPayload` instances and publish them to the event bus topic `data.acquired` (`EventTopic.DATA_ACQUIRED`).

---

## 2. Data Intake Taxonomy & Multi-Source Specifications

Community 1 ingests data across five main categories:

```
+-----------------------------------------------------------------------------------+
|                           COMMUNITY 1 INGESTION TAXONOMY                          |
+-----------------------------------------------------------------------------------+
    |                   |                   |                   |               |
    v                   v                   v                   v               v
[Market Data]    [News Feeds]        [Macro Data]       [Social Sentiment]  [On-Chain / Alt]
 - OHLCV Bars     - News Outlets      - CPI / Rates      - Velocity         - Active Addrs
 - Tick Feeds     - Regulatory Sec    - NFP / GDP        - Sentiment Score  - Exchange Flow
 - Order Books    - Earnings          - Central Banks    - -1.0 to +1.0     - Whale Moves
```

### 2.1 Price & Market Data
- **OHLCV Bars**: Standardized intervals (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`).
- **Tick & Order Book**: Bid/Ask spread, top-of-book depth, trade velocity, and cumulative volume.
- **Asset Coverage**: Crypto (CCXT, Binance, Coinbase), Stocks/Indices (Alpaca, Polygon.io), Forex (OANDA), Commodities (Interactive Brokers).

### 2.2 News & Financial Announcements
- **Headline Streams**: RSS, financial news APIs (Bloomberg, Reuters, Benzinga, CoinDesk).
- **Earnings & Regulatory Filings**: SEC EDGAR filings, corporate earnings announcements, regulatory notices.

### 2.3 Macroeconomic Data
- **Global Indicators**: US CPI, Federal Reserve Interest Rate decisions, Non-Farm Payrolls (NFP), GDP figures, ECB / Bank of Japan announcements.

### 2.4 Social Sentiment & Narrative Signals
- **Social Velocity**: Post volume trends across X/Twitter, Reddit, and Telegram channels.
- **Sentiment Scores**: NLP-analyzed sentiment score range from `-1.0` (extreme bearishness) to `+1.0` (extreme bullishness).

### 2.5 On-Chain & Alternative Data
- **Crypto On-Chain**: Exchange net flows, active wallet addresses, miner/whale transactions.
- **Alternative Signals**: Web traffic analytics, search volume trends.

---

## 3. Agent Hierarchy & Roles

Community 1 utilizes a specialized, multi-agent cooperative hierarchy to perform data ingestion and quality control concurrently:

```
+-----------------------------------------------------------------------------------+
|                        COMMUNITY 1 AGENT HIERARCHY                                |
+-----------------------------------------------------------------------------------+
                                         |
     +-------------------+---------------+---------------+-------------------+
     |                   |                               |                   |
     v                   v                               v                   v
[Market Data Agent]  [News & Sentiment Agent]  [Deduplication & Sanity]  [Normalization & Formatting]
 (Ingests OHLCV/Ticks) (Scrapes & Scores News)   (Filters Spikes/Dupes)   (Formats UTC & Emits Payload)
```

### 3.1 Market Data Ingestion Agent
- Connects to exchange WebSockets and REST endpoints (`BaseDataFetcher` implementations).
- Maintained fetchers include `SimulatedDataFetcher` (for local testing/paper trading) and production exchange fetchers.
- Streams live price bars and top-of-book depth for specified symbols.

### 3.2 News & Sentiment Agent
- Polls news providers and social media feeds.
- Computes baseline sentiment score (-1.0 to +1.0) and aggregates headline titles into `NewsSentiment` components.

### 3.3 Data Deduplication & Sanity Agent
- Maintains sliding deduplication window (e.g. hash-based title matching over a 24-hour buffer).
- Validates price sanity: flags price ticks where `high < low`, `open <= 0`, or price jump > threshold X% within single bar interval.

### 3.4 Normalization & Formatting Agent
- Maps exchange-specific asset tickers into standard unified AIOS symbols (e.g., `BTCUSDT` -> `BTC/USD`).
- Standardizes all timestamps to timezone-aware UTC datetime.
- Assembles validated price and sentiment components into `MarketDataPayload` and dispatches via `DataAcquisitionAgent`.

---

## 4. Data Normalization & Quality Rules

### 4.1 UTC ISO 8601 Timestamping Protocol
- All timestamp attributes MUST be timezone-aware UTC datetime objects.
- Example ISO 8601 format: `2026-08-03T23:00:00Z`.
- Local exchange timestamps (e.g. EST or Unix epoch milliseconds) are explicitly converted upon entry into C1.

### 4.2 Ticker Mapping & Symbol Unification
- AIOS enforces a single unified format: `<BASE_ASSET>/<QUOTE_ASSET>` (e.g. `BTC/USD`, `ETH/USD`, `AAPL/USD`).
- Mapping table examples:
  - Binance `BTCUSDT` -> `BTC/USD`
  - Coinbase `BTC-USD` -> `BTC/USD`
  - Alpaca `AAPL` -> `AAPL/USD`

### 4.3 Outlier & Anomaly Detection Rules
- **Price Jump Threshold**: If $|P_t - P_{t-1}| / P_{t-1} > 0.15$ (15% jump in a 1-minute candle without news correlation), flag as potential bad tick.
- **Price Validity Checks**:
  - `open`, `high`, `low`, `close` must be strict positive floats (`> 0.0`).
  - `high` must be $\ge \max(\text{open}, \text{close}, \text{low})$.
  - `low` must be $\le \min(\text{open}, \text{close}, \text{high})$.
  - `volume` must be $\ge 0.0$.

---

## 5. Output Schema & Event Bus Routing

### 5.1 Output Schema Definition
Community 1 outputs instances of `MarketDataPayload` defined in `schemas/contracts.py`:

```python
class PriceData(BaseModel):
    open: float = Field(..., gt=0.0)
    high: float = Field(..., gt=0.0)
    low: float = Field(..., gt=0.0)
    close: float = Field(..., gt=0.0)
    volume: float = Field(..., ge=0.0)


class NewsSentiment(BaseModel):
    title: str = Field(..., min_length=1)
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    source: str = Field(..., min_length=1)


class MarketDataPayload(BaseModel):
    timestamp: datetime = Field(default_factory=generate_utc_now)
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    price_data: PriceData
    news_sentiment: list[NewsSentiment] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 5.2 Event Bus Publication Topic
- **Topic Name**: `data.acquired` (`EventTopic.DATA_ACQUIRED`)
- **Publisher**: `DataAcquisitionAgent.collect_and_publish(symbol, timeframe)`
- **Target Subscribers**: Community 2 (Research & Analysis), Community 7 (Memory Architecture for indexing).

---

## 6. Document Verification & Compliance

This specification is tracked in [CHECKPOINT.md](CHECKPOINT.md) under **Doc 1.2: Community 1 Specification (Data Acquisition)**. Implementation code resides in `communities/c1_data/` and unit tests in `tests/test_c1_data.py`.
