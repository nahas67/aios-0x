"""Community 1: News providers -> sentiment payloads (Directive: world data).

Sentiment is computed by a deterministic lexicon scorer (transparent, fast,
free) over provider headlines. An LLM-based scorer can replace the lexicon
later without touching callers - the contract returns plain dicts matching
NewsSentiment.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

_BULLISH = [
    "surge",
    "surges",
    "rally",
    "rallies",
    "soar",
    "soars",
    "jump",
    "jumps",
    "gain",
    "gains",
    "bullish",
    "upgrade",
    "upgraded",
    "beat",
    "beats",
    "record",
    "all-time high",
    "breakout",
    "adoption",
    "partnership",
    "inflow",
    "outperform",
    "strong",
    "growth",
    "profit",
    "boost",
]
_BEARISH = [
    "plunge",
    "plunges",
    "crash",
    "crashes",
    "slump",
    "slumps",
    "drop",
    "drops",
    "fall",
    "falls",
    "bearish",
    "downgrade",
    "downgraded",
    "miss",
    "misses",
    "lawsuit",
    "hack",
    "hacked",
    "exploit",
    "ban",
    "banned",
    "sec charges",
    "outflow",
    "underperform",
    "weak",
    "loss",
    "bankruptcy",
    "fear",
    "selloff",
]


def score_sentiment(headlines: list[str]) -> float:
    """Lexicon score in [-1, 1]; 0.0 when no signal words present."""
    if not headlines:
        return 0.0
    total = 0.0
    for headline in headlines:
        text = headline.lower()
        bull = sum(text.count(w) for w in _BULLISH)
        bear = sum(text.count(w) for w in _BEARISH)
        if bull + bear == 0:
            continue
        total += (bull - bear) / (bull + bear)
    return round(max(-1.0, min(1.0, total / len(headlines))), 4)


class NewsProvider(ABC):
    """Boundary for news sources; returns raw headline dicts."""

    @abstractmethod
    async def fetch_headlines(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return [{'title': str, 'source': str}, ...]."""


class FinnhubNewsProvider(NewsProvider):
    """Finnhub company news for equities; crypto category feed for crypto pairs."""

    BASE = "https://finnhub.io/api/v1"

    def __init__(
        self,
        api_key: str,
        http_get: Any = None,
        crypto_symbols: set[str] | None = None,
    ) -> None:
        import httpx  # noqa: PLC0415 - lazy

        if not api_key:
            raise ValueError("FinnhubNewsProvider requires an API key")
        self._api_key = api_key
        self._http_get = http_get or self._default_get
        self.crypto_symbols = crypto_symbols or {"BTC/USD", "ETH/USD", "SOL/USD"}
        _ = httpx

    @staticmethod
    async def _default_get(url: str) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await asyncio.wait_for(client.get(url), timeout=12.0)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    def _url(self, symbol: str, limit: int) -> str:
        if symbol in self.crypto_symbols:
            return f"{self.BASE}/news?category=crypto&token={self._api_key}"
        ticker = symbol.split("/")[0]
        _to = "2026-12-31"
        _from = "2024-01-01"
        return (
            f"{self.BASE}/company-news?symbol={ticker}&from={_from}&to={_to}&token={self._api_key}"
        )

    async def fetch_headlines(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        data = await self._http_get(self._url(symbol, limit))
        items = data if isinstance(data, list) else []
        out: list[dict[str, Any]] = []
        for item in items[:limit]:
            headline = str(item.get("headline") or item.get("summary") or "").strip()
            if headline:
                out.append(
                    {
                        "title": headline,
                        "source": str(item.get("source") or "finnhub"),
                    }
                )
        return out


class GNewsNewsProvider(NewsProvider):
    """GNews article search (gnews.io) — key stored in settings.gnews_api_key."""

    BASE = "https://gnews.io/api/v4"

    def __init__(self, api_key: str, http_get: Any = None) -> None:
        if not api_key:
            raise ValueError("GNewsNewsProvider requires an API key")
        self._api_key = api_key
        self._http_get = http_get or FinnhubNewsProvider._default_get

    async def fetch_headlines(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        query = symbol.replace("/", " ")
        url = (
            f"{self.BASE}/search?q={query}&token={self._api_key}"
            f"&max={limit}&sortby=publishedat"
        )
        data = await self._http_get(url)
        out: list[dict[str, Any]] = []
        for item in (data or {}).get("articles", [])[:limit]:
            title = str(item.get("title") or "").strip()
            if title:
                out.append(
                    {
                        "title": title,
                        "source": str((item.get("source") or {}).get("name") or "gnews"),
                    }
                )
        return out


class NewsDataNewsProvider(NewsProvider):
    """NewsData.io latest-news search — key stored in settings.newsdata_api_key."""

    BASE = "https://newsdata.io/api/1"

    def __init__(self, api_key: str, http_get: Any = None) -> None:
        if not api_key:
            raise ValueError("NewsDataNewsProvider requires an API key")
        self._api_key = api_key
        self._http_get = http_get or FinnhubNewsProvider._default_get

    async def fetch_headlines(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        query = symbol.replace("/", " ")
        url = f"{self.BASE}/news?apikey={self._api_key}&q={query}&size={limit}"
        data = await self._http_get(url)
        out: list[dict[str, Any]] = []
        for item in (data or {}).get("results", [])[:limit]:
            title = str(item.get("title") or "").strip()
            if title:
                out.append(
                    {
                        "title": title,
                        "source": str(item.get("source_id") or "newsdata"),
                    }
                )
        return out


class FailoverNewsChain(NewsProvider):
    """Tries providers in order; first non-empty result wins.

    Every provider is an independent paid/free feed with its own outage
    profile — failover keeps sentiment flowing when one is down. The chain
    records which provider served, so the audit trail stays honest.
    """

    def __init__(self, providers: list[NewsProvider]) -> None:
        self.providers = [p for p in providers if p is not None]
        if not self.providers:
            raise ValueError("FailoverNewsChain requires at least one provider")
        self.last_served: str | None = None

    async def fetch_headlines(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                headlines = await provider.fetch_headlines(symbol, limit=limit)
            except Exception as exc:  # noqa: BLE001 - failover IS the point
                errors.append(f"{type(provider).__name__}: {exc}")
                continue
            if headlines:
                self.last_served = type(provider).__name__
                return headlines
            errors.append(f"{type(provider).__name__}: empty")
        raise RuntimeError("all news providers failed: " + "; ".join(errors))


def build_news_chain(settings: Any) -> NewsProvider | None:
    """Assemble the failover chain from whichever keys the operator set."""
    from core.config import Settings  # noqa: F401 - documentation of source

    providers: list[NewsProvider] = []
    if getattr(settings, "finnhub_api_key", None):
        providers.append(FinnhubNewsProvider(settings.finnhub_api_key))
    if getattr(settings, "gnews_api_key", None):
        providers.append(GNewsNewsProvider(settings.gnews_api_key))
    if getattr(settings, "newsdata_api_key", None):
        providers.append(NewsDataNewsProvider(settings.newsdata_api_key))
    if not providers:
        return None
    return providers[0] if len(providers) == 1 else FailoverNewsChain(providers)


class MarketStackEODFetcher:
    """MarketStack end-of-day OHLCV — available utility pending the licensed-
    data gate. NOT wired into replay goldens (synthetic remains default)."""

    BASE = "https://api.marketstack.com/v1"

    def __init__(self, api_key: str, http_get: Any = None) -> None:
        if not api_key:
            raise ValueError("MarketStackEODFetcher requires an API key")
        self._api_key = api_key
        self._http_get = http_get or FinnhubNewsProvider._default_get

    async def fetch_eod(self, symbol: str, limit: int = 30) -> list[dict[str, float]]:
        ticker = symbol.split("/")[0]
        url = f"{self.BASE}/eod?access_key={self._api_key}&symbols={ticker}&limit={limit}"
        data = await self._http_get(url)
        bars: list[dict[str, float]] = []
        for item in reversed((data or {}).get("data", [])):  # oldest first
            try:
                bars.append(
                    {
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": float(item.get("volume") or 0.0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return bars


def headlines_to_sentiment(
    headlines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert raw headlines into NewsSentiment-shaped dicts with a per-item
    lexicon score plus an aggregate entry."""
    scored: list[dict[str, Any]] = []
    for item in headlines:
        title = str(item.get("title", ""))
        score = score_sentiment([title])
        if score != 0.0:
            scored.append(
                {"title": title, "sentiment_score": score, "source": item.get("source", "news")}
            )
    aggregate = score_sentiment([str(h.get("title", "")) for h in headlines])
    if headlines:
        scored.append(
            {
                "title": f"[aggregate] {len(headlines)} headlines",
                "sentiment_score": aggregate,
                "source": "lexicon-aggregate",
            }
        )
    return scored


_SYMBOL_RE = re.compile(r"[A-Z]{2,}")


def sanitize_ticker(symbol: str) -> str:
    tickers = _SYMBOL_RE.findall(symbol.upper())
    return tickers[0] if tickers else ""
