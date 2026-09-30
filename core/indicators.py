"""Server-side technical indicators over real price series (plan section 4, A5).

Pure functions: no I/O, no fetcher knowledge. Every function returns ``None``
(or a ``None``-valued mapping) when the series is too short rather than
inventing values — the HTTP layer reports honest absence instead.
"""

from __future__ import annotations


def ema(values: list[float], period: int) -> float | None:
    """Last exponential moving average; seeded with the SMA of the first period."""
    if period <= 0 or len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    running = sum(values[:period]) / period
    for value in values[period:]:
        running += (value - running) * multiplier
    return float(running)


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI over closes; 100.0 when there are no losses in the window."""
    if period <= 0 or len(closes) < period + 1:
        return None
    gains = [max(0.0, b - a) for a, b in zip(closes, closes[1:], strict=False)]
    losses = [max(0.0, a - b) for a, b in zip(closes, closes[1:], strict=False)]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=False):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))


def _ema_series(values: list[float], period: int) -> list[float]:
    """Full EMA series (same seeding as :func:`ema`); caller guarantees length."""
    multiplier = 2.0 / (period + 1)
    out: list[float] = []
    running = sum(values[:period]) / period
    out.extend([running] * period)
    for value in values[period:]:
        running += (value - running) * multiplier
        out.append(running)
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, float] | None:
    """MACD line, signal line and histogram from the real closes series.

    Requires ``slow + signal`` points: ``slow`` to stabilise the slow EMA and
    ``signal`` to seed the signal EMA without look-ahead fabrication.
    """
    if fast <= 0 or slow <= 0 or signal <= 0 or fast >= slow:
        return None
    if len(closes) < slow + signal:
        return None
    fast_line = _ema_series(closes, fast)
    slow_line = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(fast_line, slow_line, strict=True)]
    signal_line = _ema_series(macd_line, signal)
    macd_now = macd_line[-1]
    signal_now = signal_line[-1]
    return {
        "macd": float(macd_now),
        "signal": float(signal_now),
        "histogram": float(macd_now - signal_now),
    }


def bollinger(
    closes: list[float], period: int = 20, mult: float = 2.0
) -> dict[str, float] | None:
    """SMA middle band with population-stdev upper/lower bands."""
    if period <= 0 or len(closes) < period:
        return None
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((v - middle) ** 2 for v in window) / period
    width = mult * variance**0.5
    return {
        "middle": float(middle),
        "upper": float(middle + width),
        "lower": float(middle - width),
    }
