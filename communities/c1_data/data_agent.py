"""Community 1: Data Acquisition Agent and Market Data Fetchers."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import DataProvenance, MarketDataPayload, NewsSentiment, PriceData

logger = logging.getLogger(__name__)


class BaseDataFetcher(ABC):
    """Abstract base class for market data fetchers."""

    @abstractmethod
    async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Fetch OHLCV price data for a given symbol and timeframe.

        Args:
            symbol: Trading pair or asset symbol (e.g. 'BTC/USD').
            timeframe: Time resolution (e.g. '1h', '1d').

        Returns:
            Dictionary containing 'open', 'high', 'low', 'close', and 'volume'.
        """
        pass

    @abstractmethod
    async def fetch_news_sentiment(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch news sentiment analysis for a given symbol.

        Args:
            symbol: Trading pair or asset symbol.

        Returns:
            List of dictionaries containing 'title', 'sentiment_score', and 'source'.
        """
        pass

    def provenance(self) -> DataProvenance | None:
        """Source/quality metadata attached to payloads built from this fetcher."""
        return None


class CompositeDataFetcher(BaseDataFetcher):
    """Combines a price fetcher with an independent news provider.

    Lets real venues (CCXT prices) pair with real news sentiment
    (e.g. Finnhub) without either adapter knowing about the other.
    """

    def __init__(self, price_fetcher: BaseDataFetcher, news_provider: Any) -> None:
        self.price_fetcher = price_fetcher
        self.news_provider = news_provider

    def provenance(self) -> DataProvenance | None:
        return self.price_fetcher.provenance()

    async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return await self.price_fetcher.fetch_price_data(symbol, timeframe)

    async def fetch_news_sentiment(self, symbol: str) -> list[dict[str, Any]]:
        from communities.c1_data.news_providers import headlines_to_sentiment

        headlines = await self.news_provider.fetch_headlines(symbol)
        return headlines_to_sentiment(headlines)


class SimulatedDataFetcher(BaseDataFetcher):
    """Simulated market data fetcher for testing and local paper trading."""

    def provenance(self) -> DataProvenance:
        return DataProvenance(
            source_id="simulated_v1",
            source_type="SIM",
            quality_state="FRESH",
            license="internal-test",
        )

    async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Return realistic simulated OHLCV price candle data."""
        # Provide symbol-specific price levels for realistic simulation
        base_price = 45000.0 if "BTC" in symbol.upper() else 100.0
        return {
            "open": base_price,
            "high": base_price * 1.02,
            "low": base_price * 0.98,
            "close": base_price * 1.01,
            "volume": 1250.75,
        }

    async def fetch_news_sentiment(self, symbol: str) -> list[dict[str, Any]]:
        """Return simulated news sentiment data."""
        return [
            {
                "title": f"Strong bullish momentum observed for {symbol}",
                "sentiment_score": 0.82,
                "source": "CryptoFinancial",
            },
            {
                "title": f"Market analysis and price prediction for {symbol}",
                "sentiment_score": 0.35,
                "source": "GlobalMarketNews",
            },
        ]


class DataAcquisitionAgent:
    """Agent responsible for acquiring market data and publishing to EventBus."""

    def __init__(self, fetcher: BaseDataFetcher, event_bus: BaseEventBus) -> None:
        """Initialize DataAcquisitionAgent.

        Args:
            fetcher: Data fetcher instance implementing BaseDataFetcher.
            event_bus: Event bus instance for inter-community messaging.
        """
        self.fetcher = fetcher
        self.event_bus = event_bus

    async def collect_and_publish(self, symbol: str, timeframe: str) -> MarketDataPayload:
        """Fetch price data and news sentiment concurrently and publish payload.

        Args:
            symbol: Trading symbol identifier (e.g. 'BTC/USD').
            timeframe: Time resolution (e.g. '1h').

        Returns:
            The generated MarketDataPayload instance.
        """
        # Concurrent fetching of price data and news sentiment
        price_dict, news_list = await asyncio.gather(
            self.fetcher.fetch_price_data(symbol, timeframe),
            self.fetcher.fetch_news_sentiment(symbol),
        )

        price_data = PriceData(**price_dict)
        news_sentiment = [NewsSentiment(**item) for item in news_list] if news_list else None

        provenance = self.fetcher.provenance()
        payload = MarketDataPayload(
            symbol=symbol,
            timeframe=timeframe,
            price_data=price_data,
            news_sentiment=news_sentiment,
            provenance=provenance,
            is_simulated=bool(provenance and provenance.source_type == "SIM"),
        )

        await self.event_bus.publish(EventTopic.DATA_ACQUIRED, payload)
        logger.info(
            "Published MarketDataPayload for %s (%s) to %s",
            symbol,
            timeframe,
            EventTopic.DATA_ACQUIRED,
        )
        return payload
