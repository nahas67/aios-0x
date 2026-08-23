"""Community 1: CCXT live-market data fetcher (public endpoints, keyless).

Implements BaseDataFetcher against any CCXT exchange for PUBLIC OHLCV data.
Credentials are never required here and never requested; if a network or
exchange failure occurs the exception propagates honestly to the caller.

The ccxt import is lazy and routed through :func:`_build_exchange` so tests
can inject a fake exchange object without network access.
"""

import asyncio
from typing import Any

from communities.c1_data.data_agent import BaseDataFetcher
from schemas.contracts import DataProvenance


def _build_exchange(exchange_id: str, options: dict[str, Any]) -> Any:
    """Factory boundary: builds a real ccxt exchange instance."""
    try:
        import ccxt  # noqa: PLC0415 - lazy by design (optional heavy dep)
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "ccxt is not installed; run `pip install ccxt` to use live market data"
        ) from exc
    factory = getattr(ccxt, exchange_id, None)
    if factory is None:
        raise ValueError(f"unknown ccxt exchange id: {exchange_id!r}")
    return factory(options)


class CcxtDataFetcher(BaseDataFetcher):
    """Real public OHLCV via CCXT, adapted to the AIOS data contracts."""

    def __init__(
        self,
        exchange_id: str = "binance",
        symbol_map: dict[str, str] | None = None,
        limit_bars: int = 2,
    ) -> None:
        """Bind one shared exchange client.

        Args:
            exchange_id: ccxt exchange identifier (e.g. 'binance', 'kraken').
            symbol_map: maps AIOS symbols ('BTC/USD') -> venue symbols
                ('BTC/USDT'); identity when omitted.
            limit_bars: bars fetched per call; the LAST bar is current.
        """
        self.exchange_id = exchange_id
        self._client = _build_exchange(
            exchange_id, {"enableRateLimit": True, "options": {"defaultType": "spot"}}
        )
        self.symbol_map = symbol_map or {}
        self.limit_bars = max(2, limit_bars)

    def provenance(self) -> DataProvenance:
        return DataProvenance(
            source_id=f"ccxt:{self.exchange_id}",
            source_type="MARKET",
            quality_state="LIVE",
            license="venue-public-data",
        )

    def _venue_symbol(self, symbol: str) -> str:
        return self.symbol_map.get(symbol, symbol)

    async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
        venue = self._venue_symbol(symbol)
        ohlcv = await asyncio.to_thread(
            self._client.fetch_ohlcv, venue, timeframe, None, self.limit_bars
        )
        if not ohlcv:
            raise RuntimeError(f"no OHLCV returned for {symbol} on {self.exchange_id}")
        ts, o, h, low, c, volume = ohlcv[-1]
        # Basic sanity before returning; full anomaly detection happens in C1 pipeline.
        if not (h >= low and h >= max(o, c) and low <= min(o, c)):
            raise RuntimeError(
                f"exchange returned inconsistent OHLCV row for {symbol}: {ohlcv[-1]}"
            )
        return {
            "open": float(o),
            "high": float(h),
            "low": float(low),
            "close": float(c),
            "volume": float(volume),
        }

    async def fetch_news_sentiment(self, symbol: str) -> list[dict[str, Any]]:
        """Public OHLCV carries no news; honest empty response (news adapters later)."""
        return []
