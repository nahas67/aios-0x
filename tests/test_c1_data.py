"""Unit tests for Community 1 Data Acquisition Agent and SimulatedDataFetcher."""

import asyncio

from communities.c1_data.data_agent import (
    BaseDataFetcher,
    DataAcquisitionAgent,
    SimulatedDataFetcher,
)
from core.event_bus import EventTopic, InMemoryEventBus
from schemas.contracts import MarketDataPayload


def test_simulated_data_fetcher_formats() -> None:
    """Test that SimulatedDataFetcher returns valid price and news data formats."""

    async def _test() -> None:
        fetcher = SimulatedDataFetcher()
        assert isinstance(fetcher, BaseDataFetcher)

        # Test price data fetching
        price_data = await fetcher.fetch_price_data("BTC/USD", "1h")
        assert isinstance(price_data, dict)
        required_price_keys = {"open", "high", "low", "close", "volume"}
        assert required_price_keys.issubset(price_data.keys())
        for key in required_price_keys:
            assert isinstance(price_data[key], (int, float))
            assert price_data[key] > 0

        # Test news sentiment fetching
        news_sentiment = await fetcher.fetch_news_sentiment("BTC/USD")
        assert isinstance(news_sentiment, list)
        assert len(news_sentiment) > 0
        for article in news_sentiment:
            assert isinstance(article, dict)
            assert "title" in article and isinstance(article["title"], str)
            assert "sentiment_score" in article and isinstance(article["sentiment_score"], float)
            assert -1.0 <= article["sentiment_score"] <= 1.0
            assert "source" in article and isinstance(article["source"], str)

    asyncio.run(_test())


def test_data_acquisition_agent_collect_and_publish() -> None:
    """Test DataAcquisitionAgent collects data and publishes to DATA_ACQUIRED topic."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        received_events: list[MarketDataPayload] = []

        async def event_handler(payload: MarketDataPayload) -> None:
            received_events.append(payload)

        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, event_handler)

        fetcher = SimulatedDataFetcher()
        agent = DataAcquisitionAgent(fetcher=fetcher, event_bus=event_bus)

        try:
            symbol = "BTC/USD"
            timeframe = "1h"
            returned_payload = await agent.collect_and_publish(symbol, timeframe)

            # Wait until event bus finishes dispatching
            await event_bus.wait_until_idle()

            # Assert returned payload validity
            assert isinstance(returned_payload, MarketDataPayload)
            assert returned_payload.symbol == symbol
            assert returned_payload.timeframe == timeframe
            assert returned_payload.price_data.close > 0
            assert returned_payload.news_sentiment is not None
            assert len(returned_payload.news_sentiment) > 0

            # Assert published payload delivered to subscriber
            assert len(received_events) == 1
            received_payload = received_events[0]
            assert isinstance(received_payload, MarketDataPayload)
            assert received_payload.symbol == symbol
            assert received_payload.timeframe == timeframe
            assert received_payload.price_data.close == returned_payload.price_data.close
            assert len(received_payload.news_sentiment) == len(returned_payload.news_sentiment)
        finally:
            await event_bus.stop()

    asyncio.run(_test())
