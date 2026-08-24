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
