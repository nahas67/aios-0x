"""Research Plane persistence: durable hypotheses + evidence (Phase C).

The kernel tracks lifecycle transitions within a run; this store makes the
knowledge itself outlive the process. Same backend-selection philosophy as
the memory fabric: SQLite locally, PostgreSQL when DATABASE_URL says so.

Schema:
- hypotheses: one row per first-class Hypothesis (upsert by id)
- evidence:   hash-addressable EvidencePackages (dedupe on content_hash)
- hypothesis_evidence: knowledge-graph links with relationship semantics
  ("supports" | "contradicts" | "outcome")
"""

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schemas.contracts import EvidencePackage, Hypothesis, HypothesisStatus


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _load(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


class BaseResearchStore(ABC):
    """Abstract persistence for the Research Plane."""

    @abstractmethod
    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Insert or update a hypothesis row (last_updated refreshed)."""

    @abstractmethod
    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        """Load one hypothesis; KeyError if unknown."""

    @abstractmethod
    def list_hypotheses(
        self,
        status: HypothesisStatus | None = None,
        symbol: str | None = None,
        limit: int = 500,
    ) -> list[Hypothesis]:
        """Query hypotheses, newest activity first."""

    @abstractmethod
    def save_evidence(self, package: EvidencePackage) -> str:
        """Insert evidence; returns the canonical evidence_id.

        Dedupe: an existing row with the same content_hash is reused so the
        same verification payload never forks into duplicate knowledge.
        """

    @abstractmethod
    def link_evidence(
        self, hypothesis_id: str, evidence_id: str, relationship: str
    ) -> None:
        """Attach evidence to a hypothesis (supports|contradicts|outcome)."""

    @abstractmethod
    def evidence_for_hypothesis(
        self, hypothesis_id: str
    ) -> list[tuple[EvidencePackage, str]]:
        """All (evidence, relationship) pairs linked to a hypothesis."""

    @abstractmethod
    def counts(self) -> dict[str, int]:
        """Row counts per table."""


_HYPOTHESIS_COLUMNS = (
    "hypothesis_id, statement, rationale, expected_outcome, applicable_regime, "
    "assumptions_json, symbol, timeframe, expected_risk_reward_ratio, "
    "evidence_ids_json, confidence, status, parent_hypotheses_json, "
    "dataset_ref_json, first_seen, last_updated"
)

_EVIDENCE_COLUMNS = (
    "evidence_id, source, source_version, retrieval_time, claims_json, "
    "counter_claims_json, confidence, provenance_json, linked_hypotheses_json, "
    "payload_json, content_hash"
)

# Alias-qualified form for JOIN queries (both tables contain evidence_id)
_EVIDENCE_QUALIFIED = ", ".join(
    f"e.{name.strip()}" for name in _EVIDENCE_COLUMNS.split(",")
)


def _hypothesis_row(h: Hypothesis) -> tuple:
    return (
        h.hypothesis_id,
        h.statement,
        h.rationale,
        h.expected_outcome,
        h.applicable_regime,
        _dump([a for a in h.assumptions]),
        h.symbol,
        h.timeframe,
        h.expected_risk_reward_ratio,
        _dump(h.evidence_ids),
        h.confidence,
        h.status.value,
        _dump(h.parent_hypotheses),
        _dump(h.dataset_ref),
        h.first_seen.isoformat(),
        _utc_now(),
    )


def _evidence_row(e: EvidencePackage) -> tuple:
    return (
        e.evidence_id,
        e.source,
        e.source_version,
        e.retrieval_time.isoformat(),
        _dump(e.claims),
        _dump(e.counter_claims),
        e.confidence,
        _dump(e.provenance),
        _dump(e.linked_hypotheses),
        _dump(e.payload),
        e.content_hash(),
    )


def _row_to_hypothesis(row: Any) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=row[0],
        statement=row[1],
        rationale=row[2] or "",
        expected_outcome=row[3] or "",
        applicable_regime=row[4] or "",
        assumptions=_load(row[5]) or [],
        symbol=row[6],
        timeframe=row[7],
        expected_risk_reward_ratio=row[8],
        evidence_ids=_load(row[9]) or [],
        confidence=float(row[10]),
        status=HypothesisStatus(row[11]),
        parent_hypotheses=_load(row[12]) or [],
        dataset_ref=_load(row[13]) or {},
        first_seen=datetime.fromisoformat(row[14]),
        last_updated=datetime.fromisoformat(row[15]),
    )


def _row_to_evidence(row: Any) -> EvidencePackage:
    return EvidencePackage(
        evidence_id=row[0],
        source=row[1],
        source_version=row[2],
        retrieval_time=datetime.fromisoformat(row[3]),
        claims=_load(row[4]) or [],
        counter_claims=_load(row[5]) or [],
        confidence=float(row[6]),
        provenance=_load(row[7]) or {},
        linked_hypotheses=_load(row[8]) or [],
        payload=_load(row[9]) or {},
    )


class SqliteResearchStore(BaseResearchStore):
    """Local-tier research store (mirrors SqliteMemoryStore conventions)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    rationale TEXT,
                    expected_outcome TEXT,
                    applicable_regime TEXT,
                    assumptions_json TEXT,
                    symbol TEXT,
                    timeframe TEXT,
                    expected_risk_reward_ratio REAL,
                    evidence_ids_json TEXT,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    parent_hypotheses_json TEXT,
                    dataset_ref_json TEXT,
                    first_seen TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses (status);
                CREATE INDEX IF NOT EXISTS idx_hyp_symbol ON hypotheses (symbol);
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_version TEXT,
                    retrieval_time TEXT NOT NULL,
                    claims_json TEXT,
                    counter_claims_json TEXT,
                    confidence REAL NOT NULL,
                    provenance_json TEXT,
                    linked_hypotheses_json TEXT,
                    payload_json TEXT,
                    content_hash TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_content_hash
                    ON evidence (source, content_hash);
                CREATE TABLE IF NOT EXISTS hypothesis_evidence (
                    hypothesis_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (hypothesis_id, evidence_id, relationship)
                );
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------- hypotheses

    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        with self._lock:
            placeholders = ", ".join("?" * 16)
            updates = ", ".join(
                f"{col} = excluded.{col}"
                for col in (
                    "statement", "rationale", "expected_outcome", "applicable_regime",
                    "assumptions_json", "symbol", "timeframe", "expected_risk_reward_ratio",
                    "evidence_ids_json", "confidence", "status", "parent_hypotheses_json",
                    "dataset_ref_json", "last_updated",
                )
            )
            self._conn.execute(
                f"INSERT INTO hypotheses ({_HYPOTHESIS_COLUMNS}) VALUES ({placeholders}) "
                f"ON CONFLICT (hypothesis_id) DO UPDATE SET {updates}",  # noqa: S608
                _hypothesis_row(hypothesis),
            )
            self._conn.commit()

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_HYPOTHESIS_COLUMNS} FROM hypotheses WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"hypothesis not found: {hypothesis_id!r}")
        return _row_to_hypothesis(tuple(row))

    def list_hypotheses(
        self,
        status: HypothesisStatus | None = None,
        symbol: str | None = None,
        limit: int = 500,
    ) -> list[Hypothesis]:
        query = f"SELECT {_HYPOTHESIS_COLUMNS} FROM hypotheses"  # noqa: S608
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY last_updated DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_row_to_hypothesis(tuple(r)) for r in rows]

    # --------------------------------------------------------------- evidence

    def save_evidence(self, package: EvidencePackage) -> str:
        content_hash = package.content_hash()
        with self._lock:
            existing = self._conn.execute(
                "SELECT evidence_id FROM evidence WHERE source = ? AND content_hash = ?",
                (package.source, content_hash),
            ).fetchone()
            if existing is not None:
                return str(existing["evidence_id"])
            placeholders = ", ".join("?" * 11)
            self._conn.execute(
                f"INSERT INTO evidence ({_EVIDENCE_COLUMNS}) VALUES ({placeholders})",  # noqa: S608
                _evidence_row(package),
            )
            self._conn.commit()
        return package.evidence_id

    def link_evidence(
        self, hypothesis_id: str, evidence_id: str, relationship: str
    ) -> None:
        if relationship not in {"supports", "contradicts", "outcome"}:
            raise ValueError(f"invalid evidence relationship: {relationship!r}")
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO hypothesis_evidence "
                "(hypothesis_id, evidence_id, relationship, created_at) "
                "VALUES (?, ?, ?, ?)",
                (hypothesis_id, evidence_id, relationship, _utc_now()),
            )
            # maintain the denormalized evidence_ids list on the hypothesis
            row = self._conn.execute(
                "SELECT evidence_ids_json FROM hypotheses WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchone()
            if row is not None:
                ids = _load(row["evidence_ids_json"]) or []
                if evidence_id not in ids:
                    ids.append(evidence_id)
                    self._conn.execute(
                        "UPDATE hypotheses SET evidence_ids_json = ?, last_updated = ? "
                        "WHERE hypothesis_id = ?",
                        (_dump(ids), _utc_now(), hypothesis_id),
                    )
            self._conn.commit()

    def evidence_for_hypothesis(
        self, hypothesis_id: str
    ) -> list[tuple[EvidencePackage, str]]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_EVIDENCE_QUALIFIED}, he.relationship "  # noqa: S608
                "FROM hypothesis_evidence he JOIN evidence e "
                "ON e.evidence_id = he.evidence_id "
                "WHERE he.hypothesis_id = ? ORDER BY he.created_at ASC",
                (hypothesis_id,),
            ).fetchall()
        return [(_row_to_evidence(tuple(r[:11])), r[11]) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            result = {}
            for table in ("hypotheses", "evidence", "hypothesis_evidence"):
                row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                result[table] = int(row["n"])
            return result

    def close(self) -> None:
        self._conn.close()


class PostgresResearchStore(SqliteResearchStore):
    """Server-tier research store: PostgreSQL, identical schema semantics.

    Reuses the SQL-building logic from the SQLite implementation via
    placeholder translation (? -> %s); DDL and queries stay in lockstep.
    """

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg  # noqa: PLC0415 - lazy like pg_store
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise ImportError(
                "PostgresResearchStore requires psycopg >= 3. "
                "Install with: pip install 'psycopg[binary]'"
            ) from exc
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn)
        self._conn.autocommit = False
        self._sqlite_mode = False  # marker: execute() uses %s placeholders
        self._ensure_schema_pg()

    # -- placeholder translation helpers -----------------------------------

    def _q(self, query: str) -> str:
        return query.replace("?", "%s")

    def _exec(self, cur: Any, query: str, params: tuple = ()) -> None:
        cur.execute(self._q(query), params)

    def _ensure_schema_pg(self) -> None:
        ddl_sqlite = [
            """CREATE TABLE IF NOT EXISTS hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    rationale TEXT,
                    expected_outcome TEXT,
                    applicable_regime TEXT,
                    assumptions_json TEXT,
                    symbol TEXT,
                    timeframe TEXT,
                    expected_risk_reward_ratio DOUBLE PRECISION,
                    evidence_ids_json TEXT,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    parent_hypotheses_json TEXT,
                    dataset_ref_json TEXT,
                    first_seen TEXT NOT NULL,
                    last_updated TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses (status)",
            "CREATE INDEX IF NOT EXISTS idx_hyp_symbol ON hypotheses (symbol)",
            """CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_version TEXT,
                    retrieval_time TEXT NOT NULL,
                    claims_json TEXT,
                    counter_claims_json TEXT,
                    confidence REAL NOT NULL,
                    provenance_json TEXT,
                    linked_hypotheses_json TEXT,
                    payload_json TEXT,
                    content_hash TEXT NOT NULL
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_content_hash ON evidence (source, content_hash)",
            """CREATE TABLE IF NOT EXISTS hypothesis_evidence (
                    hypothesis_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (hypothesis_id, evidence_id, relationship)
            )""",
        ]
        with self._lock:
            with self._conn.cursor() as cur:
                for stmt in ddl_sqlite:
                    cur.execute(stmt)
            self._conn.commit()

    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        with self._lock:
            placeholders = ", ".join(["%s"] * 16)
            updates = ", ".join(
                f"{col} = EXCLUDED.{col}"
                for col in (
                    "statement", "rationale", "expected_outcome", "applicable_regime",
                    "assumptions_json", "symbol", "timeframe", "expected_risk_reward_ratio",
                    "evidence_ids_json", "confidence", "status", "parent_hypotheses_json",
                    "dataset_ref_json", "last_updated",
                )
            )
            with self._conn.cursor() as cur:
                self._exec(
                    cur,
                    f"INSERT INTO hypotheses ({_HYPOTHESIS_COLUMNS}) VALUES ({placeholders}) "
                    f"ON CONFLICT (hypothesis_id) DO UPDATE SET {updates}",  # noqa: S608
                    _hypothesis_row(hypothesis),
                )
            self._conn.commit()

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        with self._lock:
            with self._conn.cursor() as cur:
                self._exec(
                    cur,
                    f"SELECT {_HYPOTHESIS_COLUMNS} FROM hypotheses WHERE hypothesis_id = ?",  # noqa: S608
                    (hypothesis_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(f"hypothesis not found: {hypothesis_id!r}")
        return _row_to_hypothesis(tuple(row))

    def list_hypotheses(
        self,
        status: HypothesisStatus | None = None,
        symbol: str | None = None,
        limit: int = 500,
    ) -> list[Hypothesis]:
        query = f"SELECT {_HYPOTHESIS_COLUMNS} FROM hypotheses"  # noqa: S608
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY last_updated DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            with self._conn.cursor() as cur:
                self._exec(cur, query, tuple(params))
                rows = cur.fetchall()
        return [_row_to_hypothesis(tuple(r)) for r in rows]

    def save_evidence(self, package: EvidencePackage) -> str:
        content_hash = package.content_hash()
        with self._lock:
            with self._conn.cursor() as cur:
                self._exec(
                    cur,
                    "SELECT evidence_id FROM evidence WHERE source = ? AND content_hash = ?",
                    (package.source, content_hash),
                )
                row = cur.fetchone()
                if row is not None:
                    return str(row[0])
                placeholders = ", ".join(["%s"] * 11)
                self._exec(
                    cur,
                    f"INSERT INTO evidence ({_EVIDENCE_COLUMNS}) VALUES ({placeholders})",  # noqa: S608
                    _evidence_row(package),
                )
            self._conn.commit()
        return package.evidence_id

    def link_evidence(
        self, hypothesis_id: str, evidence_id: str, relationship: str
    ) -> None:
        if relationship not in {"supports", "contradicts", "outcome"}:
            raise ValueError(f"invalid evidence relationship: {relationship!r}")
        with self._lock:
            with self._conn.cursor() as cur:
                self._exec(
                    cur,
                    "INSERT INTO hypothesis_evidence "
                    "(hypothesis_id, evidence_id, relationship, created_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (hypothesis_id, evidence_id, relationship, _utc_now()),
                )
                self._exec(
                    cur,
                    "SELECT evidence_ids_json FROM hypotheses WHERE hypothesis_id = ?",
                    (hypothesis_id,),
                )
                row = cur.fetchone()
                if row is not None:
                    ids = _load(row[0]) or []
                    if evidence_id not in ids:
                        ids.append(evidence_id)
                        self._exec(
                            cur,
                            "UPDATE hypotheses SET evidence_ids_json = ?, last_updated = ? "
                            "WHERE hypothesis_id = ?",
                            (_dump(ids), _utc_now(), hypothesis_id),
                        )
            self._conn.commit()

    def evidence_for_hypothesis(
        self, hypothesis_id: str
    ) -> list[tuple[EvidencePackage, str]]:
        with self._lock:
            with self._conn.cursor() as cur:
                self._exec(
                    cur,
                    f"SELECT {_EVIDENCE_QUALIFIED}, he.relationship "  # noqa: S608
                    "FROM hypothesis_evidence he JOIN evidence e "
                    "ON e.evidence_id = he.evidence_id "
                    "WHERE he.hypothesis_id = ? ORDER BY he.created_at ASC",
                    (hypothesis_id,),
                )
                rows = cur.fetchall()
        return [(_row_to_evidence(tuple(r[:11])), r[11]) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._lock:
            result: dict[str, int] = {}
            with self._conn.cursor() as cur:
                for table in ("hypotheses", "evidence", "hypothesis_evidence"):
                    self._exec(cur, f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                    result[table] = int(cur.fetchone()[0])
            return result

    def close(self) -> None:
        self._conn.close()


def select_research_store_class(database_url: str | None) -> type[BaseResearchStore]:
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return PostgresResearchStore
    return SqliteResearchStore


def build_research_store(
    store_path: str | Path,
    database_url: str | None = None,
) -> BaseResearchStore:
    store_cls = select_research_store_class(database_url)
    if store_cls is SqliteResearchStore:
        return SqliteResearchStore(Path(str(store_path)).with_suffix(".research.db"))
    return store_cls(database_url or "")

