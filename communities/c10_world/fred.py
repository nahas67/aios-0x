"""FRED (St. Louis Fed) client: real macro actuals for the calendar.

Fetches the latest observation of a series so scheduled events can carry a
REAL printed value instead of a hand-entered one. Free API key; data terms
per FRED terms-of-use.
"""

from datetime import datetime
from typing import Any

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Common series used by the expectation engine
SERIES = {
    "CPI_YOY": "CPIAUCSL",  # level; YoY computed by caller when needed
    "FED_FUNDS": "DFF",
    "UNEMPLOYMENT": "UNRATE",
    "GDP_GROWTH": "A191RL1Q225SBEA",
}


class FredClient:
    def __init__(self, api_key: str, http_get: Any = None) -> None:
        import httpx  # noqa: PLC0415 - lazy

        if not api_key:
            raise ValueError("FredClient requires an API key")
        self._api_key = api_key
        self._http_get = http_get or self._default_get
        _ = httpx

    @staticmethod
    async def _default_get(url: str) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def latest_observation(self, series_key: str) -> dict[str, Any] | None:
        """Return {'date': str, 'value': float} of the most recent non-missing point."""
        series_id = SERIES.get(series_key, series_key)
        url = (
            f"{FRED_BASE}?series_id={series_id}&api_key={self._api_key}"
            f"&file_type=json&sort_order=desc&limit=3"
        )
        data = await self._http_get(url)
        observations = data.get("observations", [])
        # Observations arrive newest-first; the first non-missing value IS
        # the latest actual.
        for obs in observations:
            value = obs.get("value", ".")
            if value not in (".", "", None):
                return {"date": str(obs["date"]), "value": float(value)}
        return None


def observation_to_event_actual(series_key: str, observation: dict[str, Any]) -> float:
    """Hook for unit conversions; CPI level -> naive YoY is future work."""
    _ = series_key
    return float(observation["value"])


def parse_fred_date(raw: str) -> datetime:
    return datetime.fromisoformat(raw)
