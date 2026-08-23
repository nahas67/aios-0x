"""Group A smoke probe: LangGraph cyclic graph on CPython 3.14 (win32).

Measures per-hop latency over a synthetic cycle mirroring our C8->C2 learning
loop shape. NOT a formal Phase 2B protocol run (single rep, small N); recorded
as feasibility evidence toward the Group A ADR.
"""

import json
import sys
import time


def main() -> int:
    try:
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "FAIL_IMPORT", "error": str(exc)}))
        return 1

    class ProbeState(TypedDict):
        hops: int
        payload: str

    def node(state: ProbeState) -> ProbeState:
        # Deterministic tiny transform standing in for an agent hop.
        return {
            "hops": state["hops"] + 1,
            "payload": state["payload"] + ".",
        }

    graph = StateGraph(ProbeState)
    graph.add_node("hop", node)

    def route(state: ProbeState) -> str:
        return "hop" if state["hops"] < HOPS else END

    HOPS = 200
    graph.add_conditional_edges("hop", route)
    graph.set_entry_point("hop")
    app = graph.compile()

    started = time.perf_counter()
    # One invocation cycles internally until HOPS reached - the honest shape
    # of a persistent learning loop (state must survive across hops).
    state: ProbeState = {"hops": 0, "payload": "x"}
    final_state = app.invoke(state)
    elapsed = time.perf_counter() - started

    ok = final_state["hops"] == HOPS and len(final_state["payload"]) == 1 + HOPS
    result = {
        "status": "PASS" if ok else "FAIL_STATE_CORRUPTION",
        "python": sys.version.split()[0],
        "hops_requested": HOPS,
        "hops_executed": final_state["hops"],
        "state_integrity_ok": ok,
        "total_wall_s": round(elapsed, 4),
        "latency_ms_mean_per_hop": round(elapsed * 1000 / max(1, final_state["hops"]), 4),
        "compat_warnings": [
            "langchain_core emits pydantic.v1 UserWarning on CPython>=3.14 "
            "(core pydantic v1 functionality incompatible)"
        ],
    }
    print(json.dumps(result))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
