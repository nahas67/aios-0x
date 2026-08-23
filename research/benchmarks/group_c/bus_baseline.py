"""Group C baseline: InMemoryEventBus throughput (NATS/Redpanda remain infra-blocked).

Records honest local numbers so the durable-broker ADR has a baseline to beat.
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.event_bus import EventTopic, InMemoryEventBus  # noqa: E402
from schemas.contracts import MarketDataPayload, PriceData  # noqa: E402

TOTAL = 20_000


async def run_once() -> float:
    bus = InMemoryEventBus()
    await bus.start()
    received = 0

    async def sink(payload: MarketDataPayload) -> None:
        nonlocal received
        received += 1

    await bus.subscribe(EventTopic.DATA_ACQUIRED, sink)
    payload = MarketDataPayload(
        symbol="B/T",
        timeframe="1m",
        price_data=PriceData(open=1, high=1, low=1, close=1, volume=1),
    )
    t0 = time.perf_counter()
    for _ in range(TOTAL):
        await bus.publish(EventTopic.DATA_ACQUIRED, payload)
    await bus.wait_until_idle()
    elapsed = time.perf_counter() - t0
    await bus.stop()
    assert received == TOTAL, f"lost events: {received}/{TOTAL}"
    return TOTAL / elapsed


def main() -> int:
    rates = [asyncio.run(run_once()) for _ in range(5)]
    result = {
        "group": "C",
        "candidate": "inmemory_event_bus (baseline only)",
        "events": TOTAL,
        "reps": 5,
        "msg_per_sec_mean": round(statistics.fmean(rates), 0),
        "msg_per_sec_p50": round(sorted(rates)[2], 0),
        "note": (
            "Baseline for the local transport. NATS JetStream / Redpanda / Redis "
            "protocol runs remain BLOCKED pending broker infrastructure "
            "(see research/benchmarks/group_c/BLOCKED.md)."
        ),
    }
    out_dir = ROOT / "research" / "benchmarks" / "group_c"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "baseline_inmemory.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
