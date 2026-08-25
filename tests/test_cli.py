"""OS CLI tests: python -m aios {boot, replay, serve}.

The operating system must boot like one. These tests exercise the same
entrypoint an operator uses — no test fixtures, no shortcuts.
"""

import json
from pathlib import Path

import pytest

from aios import cli


@pytest.fixture()
def fast_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Small golden dataset + CLI dataset resolver pointed at it."""
    from simulation.generate_golden_data import write_dataset

    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=90)
    dataset = {"SPY": tmp_path / "golden" / "SPY_1d.csv"}
    monkeypatch.setattr(cli, "_ensure_dataset", lambda symbols, bars: dataset)
    return dataset


def test_boot_prints_kernel_inventory(capsys: pytest.CaptureFixture) -> None:
    exit_code = cli.main(["boot"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "AIOS-0X BOOT" in out
    assert "PINNED" in out  # constitution hash enforced at boot
    assert "FAIL-CLOSED" in out
    assert "BOOT OK" in out


def test_replay_reports_honest_summary(fast_dataset, tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            "replay",
            "--bars", "90",
            "--symbols", "SPY",
            "--db", str(tmp_path / "cli.db"),
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "AIOS-0X REPLAY SUMMARY" in out
    assert "chain_valid" in out
    assert "REPLAY OK" in out
    assert "determinism_hash" in out


def test_summary_json_is_machine_readable(fast_dataset, tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        ["summary-json", "--bars", "90", "--symbols", "SPY", "--db", str(tmp_path / "j.db")]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["chain_valid"] is True
    assert payload["experiment_reproducibility_hash"]
    assert isinstance(payload["trades_closed"], int)


def test_serve_starts_command_center_after_clean_replay(
    fast_dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    started: list[int] = []
    stopped: list[bool] = []

    class _FakeServer:
        def __init__(self, *_a, **_k) -> None:
            self.port = 8123

        def start(self) -> None:
            started.append(self.port)

        def stop(self) -> None:
            stopped.append(True)

    import api.server as server_module

    monkeypatch.setattr(server_module, "CommandCenterServer", _FakeServer)
    monkeypatch.setattr(cli, "_serve_forever", lambda _server: stopped.append(False))

    exit_code = cli.main(
        ["serve", "--bars", "90", "--symbols", "SPY", "--db", str(tmp_path / "s.db")]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert started == [8123]
    assert "http://127.0.0.1:8123" in out


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])
