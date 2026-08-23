"""Community 1: Data Acquisition Agent and Market Data Fetchers."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from core.event_bus import BaseEventBus, EventTopic
from schemas.contracts import MarketDataPayload, NewsSentiment, PriceData

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


class SimulatedDataFetcher(BaseDataFetcher):
    """Simulated market data fetcher for testing and local paper trading."""

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

        payload = MarketDataPayload(
            symbol=symbol,
            timeframe=timeframe,
            price_data=price_data,
            news_sentiment=news_sentiment,
        )

        await self.event_bus.publish(EventTopic.DATA_ACQUIRED, payload)
        logger.info(
            "Published MarketDataPayload for %s (%s) to %s",
            symbol,
            timeframe,
            EventTopic.DATA_ACQUIRED,
        )
        return payload
