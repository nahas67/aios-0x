"""Store factory: selects the persistence backend from settings (ADR: Data Plane).

SQLite remains the default local tier (zero-dependency, hermetic tests).
Setting ``DATABASE_URL`` to a postgres DSN promotes the run to the
server-grade PostgreSQL tier with identical hash-chain semantics — an
adapter swap behind :class:`core.persistence.BaseMemoryStore`, never a
rewrite of callers.
"""

from pathlib import Path
from typing import Any

from core.persistence import BaseMemoryStore, SqliteMemoryStore


def select_store_class(database_url: str | None) -> type[BaseMemoryStore]:
    """Return the store class for a database URL (pure, no connections)."""
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        from core.pg_store import PostgresMemoryStore

        return PostgresMemoryStore
    return SqliteMemoryStore


def build_memory_store(
    store_path: str | Path,
    database_url: str | None = None,
) -> BaseMemoryStore:
    """Build the configured memory store. Connections fail closed on error."""
    store_cls: Any = select_store_class(database_url)
    if store_cls is SqliteMemoryStore:
        return SqliteMemoryStore(store_path)
    # The Postgres subclass takes a DSN where the SQLite one takes a path; the
    # base ABC declares no constructor, so the dispatcher is typed Any.
    built: BaseMemoryStore = store_cls(database_url or "")
    return built
