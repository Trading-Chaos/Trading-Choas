from __future__ import annotations

import os
import urllib.parse
import urllib.request
from dataclasses import dataclass


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "н/д"
    return f"{value:,.2f}".replace(",", " ")


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "н/д"
    return f"{value:.5f}".rstrip("0").rstrip(".")


def _side_name(side: int | None) -> str:
    if side == 1:
        return "LONG"
    if side == -1:
        return "SHORT"
    return "н/д"


def format_trade_message(
    *,
    backtest_name: str,
    event_type: str,
    symbol: str,
    side: int | None,
    order_kind: str,
    volume: float | None,
    price: float | None,
    stop_loss: float | None,
    balance: float | None,
    equity: float | None,
    reason: str,
    status: str,
) -> str:
    return "\n".join(
        [
            f"Бектест: {backtest_name}",
            f"Событие: {event_type}",
            f"Статус: {status}",
            f"Инструмент: {symbol}",
            f"Заявка/сделка: {order_kind}",
            f"Направление: {_side_name(side)}",
            f"Объем: {_fmt_value(volume)}",
            f"Цена: {_fmt_value(price)}",
            f"Stop Loss: {_fmt_value(stop_loss)}",
            f"Баланс счета: {_fmt_money(balance)}",
            f"Equity счета: {_fmt_money(equity)}",
            f"Причина входа: {reason}",
        ]
    )


@dataclass
class TelegramNotifier:
    token: str | None = None
    chat_id: str | None = None
    enabled: bool = True
    timeout: int = 10

    @classmethod
    def from_env(cls) -> "TelegramNotifier":
        enabled = os.getenv("TELEGRAM_ENABLED", "1").lower() not in {"0", "false", "no"}
        timeout = int(os.getenv("TELEGRAM_TIMEOUT", "10"))
        return cls(
            token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
            enabled=enabled,
            timeout=timeout,
        )

    def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False

        if not self.token or not self.chat_id:
            print(
                "Telegram не настроен: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID пустые."
            )
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")

        request = urllib.request.Request(url, data=payload, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except Exception as exc:
            print(f"Telegram notification failed: {exc}")
            return False
