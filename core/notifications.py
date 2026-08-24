"""Telegram notifications: fire-and-forget alerts to the operator's phone.

Wired into: kill switch, lockout engage/unlock, reconciliation failure,
drawdown tier crossings, large fills. Never blocks the trading loop.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages via Telegram Bot API. Degrades silently when unconfigured."""

    def __init__(self, bot_token: str, chat_id: str, http_post: Any = None) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._http_post = http_post or self._default_post
        self.enabled = bool(bot_token and chat_id)

    @staticmethod
    async def _default_post(url: str, body: dict[str, str]) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            return {"status": resp.status_code}

    async def send(self, message: str, severity: str = "INFO") -> bool:
        """Send a message. Returns True on success. Never raises."""
        if not self.enabled:
            return False
        icon = {"CRITICAL": "🚨", "WARNING": "⚠", "INFO": "ℹ"}.get(severity, "•")
        text = f"{icon} AIOS-0X [{severity}]\n{message}"
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            result = await asyncio.wait_for(
                self._http_post(url, {"chat_id": self._chat_id, "text": text}),
                timeout=8.0,
            )
            ok = isinstance(result, dict) and result.get("status") == 200
            if not ok:
                logger.warning("Telegram send returned non-200: %s", result)
            return ok
        except Exception as exc:  # noqa: BLE001 - never block the trading loop
            logger.warning("Telegram send failed: %s", exc)
            return False


class NotificationHub:
    """Routes notifications to all configured channels."""

    def __init__(self) -> None:
        self._notifiers: list[TelegramNotifier] = []

    def add_telegram(self, bot_token: str, chat_id: str) -> None:
        self._notifiers.append(TelegramNotifier(bot_token, chat_id))

    @property
    def has_channels(self) -> bool:
        return any(n.enabled for n in self._notifiers)

    async def notify(self, message: str, severity: str = "INFO") -> None:
        """Send to all channels concurrently. Fire-and-forget."""
        if not self._notifiers:
            return
        tasks = [n.send(message, severity) for n in self._notifiers if n.enabled]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
