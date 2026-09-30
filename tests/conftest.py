"""Hermetic test environment.

pydantic-settings merges `.env` into every Settings() instance, so a local
`.env` with MODEL_PROVIDER=openai_compatible would silently turn unit tests
into paid network calls. This autouse fixture pins the process env BEFORE any
Settings is constructed and reverts after each test. Live behavior is opt-in
per entry point (scripts pass get_settings() OUTSIDE pytest).

The PostgreSQL fixtures below serve the integration suites. They are inert
unless ``AIOS_TEST_PG_DSN`` is set, which is exactly the contract the
integration tests rely on to skip themselves in the hermetic default run.
"""

from __future__ import annotations

import importlib
import os

import pytest

#: Clear every financial table but keep the real, migrated schema in place.
#: A few kernel invariants are deliberately global (booking balance, unresolved
#: critical findings, lockout-release provenance), so a run that ended badly
#: would otherwise poison the next one.
_RESET_SQL = """
DO $$
DECLARE
    target text;
BEGIN
    FOR target IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename <> 'schema_migrations'
    LOOP
        EXECUTE format('TRUNCATE TABLE %I CASCADE', target);
    END LOOP;
END $$;
"""


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


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """The disposable PostgreSQL DSN for this session, or ``""``."""
    return os.environ.get("AIOS_TEST_PG_DSN", "")


@pytest.fixture(scope="session")
def nats_url() -> str:
    """The disposable NATS/JetStream URL for this session, or ``""``."""
    return os.environ.get("AIOS_TEST_NATS_URL", "")


@pytest.fixture(scope="session")
def reset_postgres(pg_dsn: str) -> str:
    """Truncate the financial data once per session, keeping the schema.

    Requesting this fixture also returns the DSN, so a module can depend on a
    clean database and obtain the connection string in one declaration.
    """
    if not pg_dsn:
        return pg_dsn
    psycopg = importlib.import_module("psycopg")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_RESET_SQL)
    return pg_dsn
