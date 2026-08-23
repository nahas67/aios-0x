"""CLI: pull a REAL live OHLCV sample through the C1 quality pipeline.

Uses public exchange endpoints via CCXT (no credentials). Network or venue
failures are reported honestly and non-zero-exit.

Example:
    python scripts/fetch_live_sample.py --exchange binance --symbol BTC/USDT
"""

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from communities.c1_data.ccxt_fetcher import CcxtDataFetcher  # noqa: E402
from communities.c1_data.data_agent import DataAcquisitionAgent  # noqa: E402
from core.data_quality import AnomalyDetector  # noqa: E402
from core.event_bus import EventTopic, InMemoryEventBus  # noqa: E402


async def _run(exchange: str, symbol: str, timeframe: str, aios_symbol: str) -> None:
    fetcher = CcxtDataFetcher(
        exchange_id=exchange, symbol_map={aios_symbol: symbol} if symbol != aios_symbol else None
    )
    bus = InMemoryEventBus()
    await bus.start()

    received = []

    async def sink(payload):
        received.append(payload)

    await bus.subscribe(EventTopic.DATA_ACQUIRED, sink)

    agent = DataAcquisitionAgent(fetcher=fetcher, event_bus=bus)
    detector = AnomalyDetector()

    payload = await agent.collect_and_publish(aios_symbol, timeframe)
    await bus.wait_until_idle()
    alerts = detector.ingest(payload)
    await bus.stop()

    out = {
        "symbol": payload.symbol,
        "timeframe": payload.timeframe,
        "price": payload.price_data.model_dump(),
        "timestamp": payload.timestamp.isoformat(),
        "is_simulated": payload.is_simulated,
        "provenance": payload.provenance.model_dump(mode="json") if payload.provenance else None,
        "anomalies": [a.model_dump(mode="json") for a in alerts],
    }
    print(json.dumps(out, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default="BTC/USDT", help="Venue symbol")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--as-symbol", default=None, help="AIOS-side symbol (default: --symbol)")
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.exchange, args.symbol, args.timeframe, args.as_symbol or args.symbol))
    except Exception as exc:  # noqa: BLE001 - CLI boundary must report honestly
        print(f"LIVE FETCH FAILED honestly: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
