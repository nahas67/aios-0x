"""Group A benchmark: LangGraph cyclic orchestration vs native AIOS event bus.

Task shape mirrors our C8->C2 learning loop: a stateful cycle of N hops where
each hop transforms typed state; integrity requires exact hop count and payload
growth. Protocol: >=10 repetitions per side, discarded warmup, mean/p50/p95.

Output: research/benchmarks/group_a/groupA_result.yaml (simplified schema).
NOT the full Phase 2B protocol (no real-model costs, no CrewAI/LlamaIndex arms
yet) - recorded as functional evidence toward the orchestration ADR.
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

HOPS = 100
WARMUP = 1
REPS = 10

from pydantic import BaseModel  # noqa: E402


def bench_langgraph() -> list[float]:
    from langgraph.graph import END, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict):
        hops: int
        payload: str

    def node(state: State) -> State:
        return {"hops": state["hops"] + 1, "payload": state["payload"] + "."}

    graph = StateGraph(State)
    graph.add_node("hop", node)
    graph.add_conditional_edges("hop", lambda s: "hop" if s["hops"] < HOPS else END)
    graph.set_entry_point("hop")
    app = graph.compile()

    latencies = []
    for rep in range(WARMUP + REPS):
        t0 = time.perf_counter()
        final = app.invoke({"hops": 0, "payload": "x"})
        elapsed = time.perf_counter() - t0
        if rep >= WARMUP:
            latencies.append(elapsed)
        assert final["hops"] == HOPS and len(final["payload"]) == 1 + HOPS, (
            f"state corruption on rep {rep}: {final['hops']}"
        )
    return latencies


def bench_native_bus() -> list[float]:
    from core.event_bus import EventTopic, InMemoryEventBus
    from schemas.contracts import CandidateHypothesis

    class HopState:
        def __init__(self) -> None:
            self.hops = 0

    async def run_once(bus: InMemoryEventBus) -> float:
        state = HopState()
        done = asyncio.Event()

        async def hop(payload: BaseModel) -> None:
            state.hops += 1
            if state.hops < HOPS:
                await bus.publish(EventTopic.HYPOTHESIS_GENERATED, payload)
            else:
                done.set()

        await bus.start()
        await bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, hop)
        t0 = time.perf_counter()
        await bus.publish(
            EventTopic.HYPOTHESIS_GENERATED,
            CandidateHypothesis(
                symbol="X/USD",
                thesis="bench",
                supporting_arguments=["a"],
                counter_arguments=["b"],
                timeframe="1d",
                expected_risk_reward_ratio=2.0,
            ),
        )
        await done.wait()
        elapsed = time.perf_counter() - t0
        await bus.stop()
        assert state.hops == HOPS, f"bus lost hops: {state.hops}"
        return elapsed

    latencies = []
    for rep in range(WARMUP + REPS):
        bus = InMemoryEventBus()
        elapsed = asyncio.run(run_once(bus))
        if rep >= WARMUP:
            latencies.append(elapsed)
    return latencies


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "mean_s": round(statistics.fmean(ordered), 5),
        "p50_s": round(ordered[len(ordered) // 2], 5),
        "p95_s": round(ordered[int(len(ordered) * 0.95)], 5),
        "reps": len(ordered),
    }


def main() -> int:
    result: dict[str, object] = {
        "group": "A",
        "task": f"stateful cycle x{HOPS} hops",
        "protocol": f"{REPS} reps after {WARMUP} warmup; integrity asserted every rep",
        "python": sys.version.split()[0],
    }
    try:
        lg = stats(bench_langgraph())
        result["langgraph"] = {"status": "PASS", **lg}
    except Exception as exc:  # noqa: BLE001 - evidence must capture failures honestly
        result["langgraph"] = {"status": "FAIL", "error": str(exc)[:200]}

    try:
        nb = stats(bench_native_bus())
        result["native_inmemory_bus"] = {"status": "PASS", **nb}
    except Exception as exc:  # noqa: BLE001
        result["native_inmemory_bus"] = {"status": "FAIL", "error": str(exc)[:200]}

    out_dir = ROOT / "research" / "benchmarks" / "group_a"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "groupA_benchmark.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
