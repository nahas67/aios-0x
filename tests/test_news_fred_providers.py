"""News provider + FRED client contract tests (fake HTTP, no network)."""

import asyncio

import pytest

from communities.c1_data.news_providers import (
    FinnhubNewsProvider,
    headlines_to_sentiment,
    sanitize_ticker,
    score_sentiment,
)
from communities.c10_world.fred import FredClient

# ------------------------------------------------------------------ sentiment


def test_lexicon_scoring_bounds_and_direction() -> None:
    bull = score_sentiment(["Bitcoin surges to record high on institutional adoption"])
    bear = score_sentiment(["Exchange hacked; users fear selloff after crash"])
    neutral = score_sentiment(["Quarterly report published today"])
    assert bull > 0.5
    assert bear < -0.5
    assert neutral == 0.0


def test_sanitize_ticker_extracts_base() -> None:
    assert sanitize_ticker("BTC/USD") == "BTC"
    assert sanitize_ticker("AAPL") == "AAPL"


def test_headlines_to_sentiment_appends_aggregate() -> None:
    out = headlines_to_sentiment(
        [
            {"title": "Markets rally strongly", "source": "x"},
            {"title": "Nothing words here", "source": "y"},
        ]
    )
    # per-item score only for the signal headline + one aggregate row
    assert len(out) == 2
    assert out[-1]["source"] == "lexicon-aggregate"
    assert out[0]["sentiment_score"] > 0


# -------------------------------------------------------------------- finnhub


def test_finnhub_crypto_uses_category_feed(fake_http):
    provider = FinnhubNewsProvider("KEY", http_get=fake_http.handler)
    url = provider._url("BTC/USD", limit=5)
    assert "category=crypto" in url

    headlines = asyncio_run(provider.fetch_headlines("BTC/USD"))
    assert len(headlines) == 2
    assert {h["title"] for h in headlines} == {
        "Crypto surges on inflows",
        "Altcoin dumps ahead of unlock",
    }
    assert fake_http.calls[0].startswith("https://finnhub.io/api/v1/news")


def test_finnhub_equity_uses_company_news(fake_http):
    provider = FinnhubNewsProvider("KEY", http_get=fake_http.handler)
    url = provider._url("AAPL", limit=5)
    assert "company-news" in url and "symbol=AAPL" in url
    headlines = asyncio_run(provider.fetch_headlines("AAPL"))
    assert isinstance(headlines, list)


def test_finnhub_requires_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        FinnhubNewsProvider("")


# ----------------------------------------------------------------------- fred


def test_fred_latest_observation_skips_missing_values(fake_http) -> None:
    client = FredClient("KEY", http_get=fake_http.fred_handler)

    async def _run():
        return await client.latest_observation("CPI_YOY")

    obs = asyncio.run(_run())
    assert obs == {"date": "2026-05-01", "value": 333.979}
    assert fake_http.fred_calls[0].startswith("https://api.stlouisfed.org/fred")
    assert "series_id=CPIAUCSL" in fake_http.fred_calls[0]


def test_fred_series_map_and_real_money_guard() -> None:
    from communities.c10_world.fred import SERIES

    assert SERIES["FED_FUNDS"] == "DFF"

    async def boom(url: str):
        raise AssertionError("network call attempted")

    with pytest.raises(ValueError, match="API key"):
        FredClient("", http_get=boom)


# ------------------------------------------------------------------- helpers


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.fixture()
def fake_http():
    class Registry:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.fred_calls: list[str] = []

        async def handler(self, url: str):
            self.calls.append(url)
            if "/news?" in url:
                return [
                    {"headline": "Crypto surges on inflows", "source": "wire"},
                    {"headline": "", "summary": "Altcoin dumps ahead of unlock", "source": "blog"},
                ]
            return []

        async def fred_handler(self, url: str):
            self.fred_calls.append(url)
            return {
                "observations": [
                    {"date": "2026-06-01", "value": "."},
                    {"date": "2026-05-01", "value": "333.979"},
                    {"date": "2026-04-01", "value": "332.1"},
                ]
            }

    return Registry()
