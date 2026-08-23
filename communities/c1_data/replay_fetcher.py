"""Community 1: Historical replay data fetcher with strict no-look-ahead semantics.

The fetcher exposes exactly ONE bar per symbol at any time - the bar at the
shared replay cursor (Directive 75: only information actually available at
decision time may be used). Future bars are unreachable until the cursor
advances. All data is tagged is_simulated=True unless the CSV carries real
licensed data with provenance overrides.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from communities.c1_data.data_agent import BaseDataFetcher
from schemas.contracts import DataProvenance


class Bar(TypedDict):
    """One OHLCV replay bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


_REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


def _parse_timestamp(raw: str) -> datetime:
    """Parse ISO-8601 timestamps; naive values are assumed UTC."""
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError(f"Timestamp must carry timezone information: {raw!r}")
    return ts


class ReplayCursor:
    """Shared position in historical time for a panel of symbols."""

    def __init__(self) -> None:
        self._index = 0
        self._started = False

    def advance(self) -> int:
        """Move to the next bar and return the new index."""
        self._index += 1
        self._started = True
        return self._index

    @property
    def index(self) -> int:
        return self._index

    @property
    def started(self) -> bool:
        return self._started


class ReplayDataFetcher(BaseDataFetcher):
    """Deterministic OHLCV replay from CSV files, one current bar at a time."""

    def __init__(
        self,
        csv_path_by_symbol: dict[str, str | Path],
        cursor: ReplayCursor | None = None,
        source_tag: str = "replay_csv_v1",
        treat_as_real: bool = False,
    ) -> None:
        """Load datasets and bind them to a shared replay cursor.

        Args:
            csv_path_by_symbol: Mapping of normalized symbol to OHLCV CSV path.
            cursor: Shared cursor; a private one is created when omitted.
            source_tag: Provenance source identifier.
            treat_as_real: Mark dataset provenance MARKET instead of SIM.
        """
        self.cursor = cursor or ReplayCursor()
        self._bars: dict[str, list[Bar]] = {}
        self._symbols = sorted(csv_path_by_symbol)
        for symbol, path in csv_path_by_symbol.items():
            self._bars[symbol] = self._load_csv(Path(path))
        self._provenance = DataProvenance(
            source_id=source_tag,
            source_type="MARKET" if treat_as_real else "SIM",
            quality_state="FRESH",
            license="internal-synthetic" if not treat_as_real else "external-licensed",
        )

    @staticmethod
    def _load_csv(path: Path) -> list[Bar]:
        if not path.exists():
            raise FileNotFoundError(f"Replay dataset missing: {path}")
        rows: list[Bar] = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = _REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(f"{path}: missing columns {sorted(missing)}")
            for raw in reader:
                o = float(raw["open"])
                hi = float(raw["high"])
                lo = float(raw["low"])
                c = float(raw["close"])
                if not (hi >= lo and hi >= max(o, c) and lo <= min(o, c)):
                    raise ValueError(f"{path}: inconsistent OHLC row {raw}")
                rows.append(
                    Bar(
                        timestamp=_parse_timestamp(raw["timestamp"]),
                        open=o,
                        high=hi,
                        low=lo,
                        close=c,
                        volume=float(raw["volume"]),
                    )
                )
        if not rows:
            raise ValueError(f"{path}: dataset is empty")
        rows.sort(key=lambda r: r["timestamp"])
        return rows

    def provenance(self) -> DataProvenance:
        return self._provenance

    def current_bar(self, symbol: str) -> Bar:
        """Return the bar at the cursor without advancing (the ONLY visible future).

        Cursor semantics: index counts consumed bars; after N advances the bar
        at position N-1 is current. Bar 0 is never skipped.
        """
        if symbol not in self._bars:
            raise KeyError(f"Unknown replay symbol: {symbol!r}")
        if not self.cursor.started:
            raise RuntimeError("Replay cursor has not been advanced yet")
        idx = self.cursor.index - 1
        bars = self._bars[symbol]
        if idx >= len(bars) or idx < 0:
            raise IndexError(f"Replay exhausted for {symbol} at index {idx}")
        return bars[idx]

    def current_timestamp(self) -> datetime:
        """Decision-time timestamp shared across the panel."""
        return self.current_bar(self._symbols[0])["timestamp"]

    def remaining(self, symbol: str) -> int:
        """Bars left after the cursor for this symbol (runner bookkeeping)."""
        return len(self._bars[symbol]) - self.cursor.index

    def bar_count(self, symbol: str) -> int:
        """Total bars available for a symbol."""
        return len(self._bars[symbol])

    async def fetch_price_data(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Expose the CURRENT bar only - never any later bar (no look-ahead)."""
        bar = self.current_bar(symbol)
        return {
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
        }

    async def fetch_news_sentiment(self, symbol: str) -> list[dict[str, Any]]:
        """Replay carries no news feed; honest empty response."""
        return []
