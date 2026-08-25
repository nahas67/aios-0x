"""News provider failover chain + MarketStack utility tests.

All transports are injected fakes — no network. Proves: URL/key handling per
provider, payload shape parsing, failover ordering with honest last_served,
chain selection matrix from settings, and MarketStack EOD parsing.
"""

import asyncio
from typing import Any

import pytest

from communities.c1_data.news_providers import (
    FailoverNewsChain,
    FinnhubNewsProvider,
    GNewsNewsProvider,
    MarketStackEODFetcher,
    NewsDataNewsProvider,
    build_news_chain,
)


def _fake_get(payload):
    async def _get(url: str):
        _get.calls.append(url)  # type: ignore[attr-defined]
        return payload

    _get.calls = []  # type: ignore[attr-defined]
    return _get


# ---------------------------------------------------------------- providers


def test_gnews_parses_articles_and_builds_url_with_key() -> None:
    get = _fake_get({"articles": [
        {"title": "Fed cuts rates", "source": {"name": "Reuters"}},
        {"title": "", "source": {}},
    ]})
    provider = GNewsNewsProvider("gkey", http_get=get)

    headlines = asyncio.run(provider.fetch_headlines("AAPL", limit=5))

    assert headlines == [{"title": "Fed cuts rates", "source": "Reuters"}]
    assert "token=gkey" in get.calls[0]
    assert "q=AAPL" in get.calls[0]


def test_newsdata_parses_results_and_uses_source_id() -> None:
    get = _fake_get({"results": [
        {"title": "BTC ETF approved", "source_id": "coindeck"},
    ]})
    provider = NewsDataNewsProvider("nkey", http_get=get)

    headlines = asyncio.run(provider.fetch_headlines("BTC/USD"))

    assert headlines == [{"title": "BTC ETF approved", "source": "coindeck"}]
    assert "apikey=nkey" in get.calls[0]


def test_providers_require_keys() -> None:
    for cls in (GNewsNewsProvider, NewsDataNewsProvider, MarketStackEODFetcher):
        with pytest.raises(ValueError):
            cls("")


# ----------------------------------------------------------------- failover


def test_failover_skips_failing_provider_and_records_server() -> None:
    class Boom(FinnhubNewsProvider):
        def __init__(self) -> None:
            pass  # skip key check

        async def fetch_headlines(self, symbol, limit=5):
            raise RuntimeError("outage")

    healthy = GNewsNewsProvider("gkey", http_get=_fake_get(
        {"articles": [{"title": "recovered", "source": {"name": "AP"}}]}
    ))
    chain = FailoverNewsChain([Boom(), healthy])

    headlines = asyncio.run(chain.fetch_headlines("SPY"))
    assert headlines[0]["title"] == "recovered"
    assert chain.last_served == "GNewsNewsProvider"


def test_failover_raises_when_all_fail() -> None:
    class Dead:
        async def fetch_headlines(self, symbol, limit=5):
            raise RuntimeError("down")

    chain = FailoverNewsChain([Dead(), Dead()])
    with pytest.raises(RuntimeError, match="all news providers failed"):
        asyncio.run(chain.fetch_headlines("X"))


# ------------------------------------------------------- settings selection


def _settings(**keys: Any) -> Any:
    """Hermetic settings: every provider key explicit, .env ignored."""
    from core.config import Settings

    base: dict[str, Any] = {
        "model_provider": "none",
        "finnhub_api_key": None,
        "gnews_api_key": None,
        "newsdata_api_key": None,
    }
    base.update(keys)
    return Settings(**base)


def test_build_news_chain_selection_matrix() -> None:
    assert build_news_chain(_settings()) is None

    single = build_news_chain(_settings(finnhub_api_key="fh"))
    assert isinstance(single, FinnhubNewsProvider)

    chain3 = build_news_chain(
        _settings(finnhub_api_key="fh", gnews_api_key="gn", newsdata_api_key="nd")
    )
    assert isinstance(chain3, FailoverNewsChain)
    assert len(chain3.providers) == 3


def test_marketstack_eod_parses_oldest_first_and_skips_bad_rows() -> None:
    get = _fake_get({"data": [
        {"open": "100", "high": "102", "low": "99", "close": "101", "volume": "10"},
        {"open": None},  # malformed row skipped
        {"open": "101", "high": "103", "low": "100", "close": "103", "volume": "12"},
    ]})
    fetcher = MarketStackEODFetcher("mkey", http_get=get)

    bars = asyncio.run(fetcher.fetch_eod("AAPL"))

    # API returns newest-first; fetch_eod reverses to oldest-first
    assert [b["close"] for b in bars] == [103.0, 101.0], "oldest-first ordering"
    assert all(set(b) == {"open", "high", "low", "close", "volume"} for b in bars)
    assert "access_key=mkey" in get.calls[0]


def test_runner_wires_chain_when_live_news_enabled(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config import Settings
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=40)
    captured = {}

    import communities.c1_data.news_providers as np_mod

    real_chain = np_mod.build_news_chain

    def spy(settings):
        built = real_chain(settings)
        captured["chain"] = built
        return built

    monkeypatch.setattr(np_mod, "build_news_chain", spy)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "r.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        use_live_news=True,
        settings=Settings(model_provider="none", finnhub_api_key="fh-test"),
    )
    assert captured["chain"] is not None
    assert runner.fetcher_any.news_provider is captured["chain"]
