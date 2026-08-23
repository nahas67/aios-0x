"""Hermetic test environment.

pydantic-settings merges `.env` into every Settings() instance, so a local
`.env` with MODEL_PROVIDER=openai_compatible would silently turn unit tests
into paid network calls. This autouse fixture pins the process env BEFORE any
Settings is constructed and reverts after each test. Live behavior is opt-in
per entry point (scripts pass get_settings() OUTSIDE pytest).
"""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "none")
    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "FINNHUB_API_KEY",
        "GNEWS_API_KEY",
        "NEWSDATA_API_KEY",
        "MARKETSTACK_API_KEY",
        "FRED_API_KEY",
        "AIOS_ALLOW_LIVE_EXECUTION",
    ):
        monkeypatch.delenv(var, raising=False)
