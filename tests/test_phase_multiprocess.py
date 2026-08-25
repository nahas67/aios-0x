"""Multi-process consumption tests: a SECOND process tails the durable log.

The trading OS writes the hash-chained log; an independent OS process
(`python -m aios tail --follow`) consumes it with its own cursor. This is the
service-split seam proven with real processes — not in-memory fakes.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from core.event_recovery import checkpoint
from core.persistence import SqliteMemoryStore

ROOT = Path(__file__).resolve().parents[1]


def _spawn_tail(db: Path, state_file: Path, follow: bool) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "aios",
        "tail",
        "--db",
        str(db),
        "--json",
        "--poll-interval",
        "0.1",
    ]
    if follow:
        cmd.append("--follow")
    if state_file != Path(""):
        cmd += ["--state-file", str(state_file)]
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_json_line(proc: subprocess.Popen, timeout_s: float = 20.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if not line:
            time.sleep(0.05)
            continue
        line = line.strip()
        if line.startswith("{") and '"kind"' in line:
            return json.loads(line)
        # skip banner/other lines until first event JSON
    raise TimeoutError("tail process produced no event line in time")


def test_second_process_consumes_events_written_by_first(tmp_path: Path) -> None:
    db = tmp_path / "mp.db"
    store = SqliteMemoryStore(db)
    store.append_event("BOOT", "genesis", {"n": 0})
    start_cursor = checkpoint(store)

    state = tmp_path / "cursor.json"
    proc = _spawn_tail(db, state, follow=True)
    try:
        # tail prints its banner immediately on startup
        banner = proc.stdout.readline()  # type: ignore[union-attr]
        assert banner.startswith("tail "), banner
        assert proc.poll() is None, "tail process must be alive"

        # ---- FIRST process (this one) writes new events AFTER tail started
        written = []
        for i in range(3):
            seq = store.append_event(
                "aios.platform.hypothesis_created", f"h-{i}", {"symbol": f"S{i}"}
            )
            written.append(seq)

        received = [_read_json_line(proc) for _ in range(3)]
        assert [r["seq"] for r in received] == sorted(written)
        assert all(r["kind"] == "aios.platform.hypothesis_created" for r in received)
        assert [r["payload"]["symbol"] for r in received] == ["S0", "S1", "S2"]

        # cursor state persisted by the tail process, exactly at the last seq
        deadline = time.time() + 10
        while time.time() < deadline:
            if state.exists():
                saved = json.loads(state.read_text())["after_seq"]
                if saved == written[-1]:
                    break
            time.sleep(0.1)
        assert json.loads(state.read_text())["after_seq"] == written[-1]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    _ = start_cursor


def test_state_file_resume_is_exactly_once(tmp_path: Path) -> None:
    db = tmp_path / "resume.db"
    store = SqliteMemoryStore(db)
    for i in range(6):
        store.append_event("KIND", str(i), {"i": i})

    state = tmp_path / "cursor.json"
    state.write_text(json.dumps({"after_seq": 4}))  # consumer already saw seq<=4

    proc = _spawn_tail(db, state, follow=False)
    try:
        out, _err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()

    events = [
        json.loads(line)
        for line in out.splitlines()
        if line.startswith("{") and '"kind"' in line
    ]
    # seqs 5..6 remain after cursor 4; payload i == seq - 1 in this seeding
    assert [(e["seq"], e["payload"]["i"]) for e in events] == [(5, 4), (6, 5)], (
        "exactly-once resume"
    )
    assert json.loads(state.read_text())["after_seq"] == 6
