from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from input.mt5_candles import (
    MT5ConnectionConfig,
    connect_mt5,
    select_symbol,
    shutdown_mt5,
)
from output.telegram_bot import TelegramNotifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path("output") / "telegram_trading_config.local.json"
DEFAULT_LOG_PATH = Path("output") / "basic_live_pipeline.log"


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass
class TradingBotConfig:
    login: int | None = None
    password: str | None = None
    server: str | None = None
    terminal_path: str | None = None
    symbol: str = "BRENT"
    timeframe: str = "H1"
    volume: float = 1.0
    risk_pct: float = 0.02
    poll_seconds: int = 60

    @classmethod
    def from_env(cls) -> "TradingBotConfig":
        login = os.getenv("MT5_LOGIN")
        volume = os.getenv("BASIC_BACKTEST_VOLUME")
        risk_pct = os.getenv("BASIC_BACKTEST_RISK_PCT")
        poll_seconds = os.getenv("BASIC_BACKTEST_POLL_SECONDS")

        return cls(
            login=int(login) if login else None,
            password=os.getenv("MT5_PASSWORD") or None,
            server=os.getenv("MT5_SERVER") or None,
            terminal_path=os.getenv("MT5_PATH") or None,
            symbol=os.getenv("MT5_SYMBOL", "BRENT"),
            timeframe=os.getenv("MT5_TIMEFRAME", "H1"),
            volume=float(volume) if volume else 1.0,
            risk_pct=float(risk_pct) if risk_pct else 0.02,
            poll_seconds=int(poll_seconds) if poll_seconds else 60,
        )

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "TradingBotConfig":
        if not path.exists():
            return cls.from_env()

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        base = asdict(cls.from_env())
        base.update({key: value for key, value in data.items() if value is not None})
        return cls(**base)

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)

    def to_mt5_connection(self) -> MT5ConnectionConfig:
        return MT5ConnectionConfig(
            login=self.login,
            password=self.password,
            server=self.server,
            path=self.terminal_path,
        )

    def is_account_ready(self) -> bool:
        return bool(self.login and self.password and self.server)

    def summary(self) -> str:
        return "\n".join(
            [
                f"Счет: {self.login if self.login else 'не задан'}",
                f"Сервер: {self.server or 'не задан'}",
                f"Пароль: {'задан' if self.password else 'не задан'}",
                f"Терминал: {self.terminal_path or 'по умолчанию'}",
                f"Инструмент: {self.symbol}",
                f"Таймфрейм: {self.timeframe}",
                f"Объем: {self.volume}",
                f"Риск на сделку: {self.risk_pct:.4f}",
                f"Опрос: {self.poll_seconds} сек.",
            ]
        )


def build_pipeline_command(
    python_executable: str, config: TradingBotConfig, dry_run: bool
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "basic_backtest.live_brent_h1_pipeline",
        "--symbol",
        config.symbol,
        "--timeframe",
        config.timeframe,
        "--volume",
        str(config.volume),
        "--risk-pct",
        str(config.risk_pct),
        "--poll-seconds",
        str(config.poll_seconds),
    ]

    if dry_run:
        command.append("--dry-run")

    return command


def build_pipeline_env(
    config: TradingBotConfig, chat_id: int | str | None
) -> dict[str, str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    src_path = str(PROJECT_ROOT / "src")
    dot_path = str(PROJECT_ROOT)
    env["PYTHONPATH"] = (
        os.pathsep.join([src_path, dot_path, current_pythonpath])
        if current_pythonpath
        else os.pathsep.join([src_path, dot_path])
    )

    if config.login is not None:
        env["MT5_LOGIN"] = str(config.login)
    if config.password:
        env["MT5_PASSWORD"] = config.password
    if config.server:
        env["MT5_SERVER"] = config.server
    if config.terminal_path:
        env["MT5_PATH"] = config.terminal_path

    env["MT5_SYMBOL"] = config.symbol
    env["MT5_TIMEFRAME"] = config.timeframe
    if chat_id is not None and not env.get("TELEGRAM_CHAT_ID"):
        env["TELEGRAM_CHAT_ID"] = str(chat_id)

    return env


def check_mt5_connection(config: TradingBotConfig) -> str:
    if not config.is_account_ready():
        return "MT5-счет не настроен: нужны login, server и password."

    try:
        terminal = connect_mt5(config.to_mt5_connection())
        select_symbol(config.symbol)
        account = terminal.account_info()
        terminal_info = terminal.terminal_info()

        if account is None:
            return "MT5 подключился, но account_info() пустой."

        trade_allowed = getattr(account, "trade_allowed", None)
        terminal_trade_allowed = getattr(terminal_info, "trade_allowed", None)
        return "\n".join(
            [
                "MT5 подключен.",
                f"Счет: {account.login}",
                f"Сервер: {account.server}",
                f"Баланс: {float(account.balance):,.2f}".replace(",", " "),
                f"Equity: {float(account.equity):,.2f}".replace(",", " "),
                f"Торговля на счете: {trade_allowed}",
                f"Торговля в терминале: {terminal_trade_allowed}",
                f"Инструмент: {config.symbol}",
            ]
        )
    except Exception as exc:
        return f"Проверка MT5 не прошла: {exc}"
    finally:
        shutdown_mt5()


class BasicBacktestProcess:
    def __init__(self, log_path: Path = DEFAULT_LOG_PATH):
        self.process: subprocess.Popen | None = None
        self.log_path = log_path
        self._log_handle = None
        self.started_mode: str | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def status(self) -> str:
        if self.is_running():
            return (
                f"basic_backtest работает, режим: {self.started_mode}. "
                f"Лог: {self.log_path}"
            )

        if self.process is None:
            return "basic_backtest не запущен."

        return f"basic_backtest остановлен, код выхода: {self.process.poll()}."

    def start(
        self,
        *,
        config: TradingBotConfig,
        dry_run: bool,
        chat_id: int | str | None,
    ) -> str:
        if self.is_running():
            return self.status()

        if not dry_run and not _env_enabled("TELEGRAM_ALLOW_LIVE_TRADING"):
            return (
                "Реальная торговля заблокирована защитой. "
                "На Windows-машине задай TELEGRAM_ALLOW_LIVE_TRADING=1 "
                "и повтори /start_basic_live."
            )

        if not config.is_account_ready():
            return "Счет не подключен. Сначала отправь /connect <login> <server> <password>."

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("a", encoding="utf-8")
        command = build_pipeline_command(sys.executable, config, dry_run=dry_run)
        env = build_pipeline_env(config, chat_id=chat_id)
        self.process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.started_mode = "dry-run" if dry_run else "live"
        return (
            f"basic_backtest запущен, режим: {self.started_mode}. "
            f"Инструмент: {config.symbol}, объем: {config.volume}. "
            f"Лог: {self.log_path}"
        )

    def stop(self) -> str:
        if not self.is_running():
            return self.status()

        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=15)

        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

        return f"basic_backtest остановлен, код выхода: {self.process.returncode}."


class TelegramTradingBot:
    def __init__(
        self,
        *,
        token: str | None = None,
        allowed_chat_id: str | None = None,
        config_path: Path = DEFAULT_CONFIG_PATH,
        timeout: int = 30,
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_chat_id = allowed_chat_id or os.getenv(
            "TELEGRAM_ALLOWED_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID")
        )
        self.config_path = config_path
        self.timeout = timeout
        self.process = BasicBacktestProcess()
        self.notifier = TelegramNotifier(
            token=self.token,
            chat_id=None,
            enabled=True,
            timeout=10,
        )

    def _api(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")

        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = None
        if params:
            data = urllib.parse.urlencode(params).encode("utf-8")

        request = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout + 5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _send(self, chat_id: int | str, text: str) -> None:
        self.notifier.chat_id = str(chat_id)
        self.notifier.send_message(text)

    def _is_authorized(self, chat_id: int | str) -> bool:
        return self.allowed_chat_id is not None and str(chat_id) == str(
            self.allowed_chat_id
        )

    @staticmethod
    def help_text() -> str:
        return "\n".join(
            [
                "Команды торгового бота:",
                "/whoami - показать chat_id",
                "/status - статус счета и basic_backtest",
                "/connect <login> <server> <password> - сохранить счет MT5",
                "/set_path <путь к terminal64.exe> - задать путь терминала",
                "/set_symbol <symbol> - задать инструмент, например BRENT",
                "/set_volume <volume> - задать объем",
                "/set_risk <0.02> - задать риск на сделку",
                "/set_poll <seconds> - задать частоту проверки",
                "/test_mt5 - проверить подключение к MT5",
                "/start_basic_dry - запустить без реальных заявок",
                "/start_basic_live - запустить реальные заявки basic_backtest",
                "/stop_basic - остановить basic_backtest",
                "/clear_account - удалить локальные данные счета",
            ]
        )

    def handle_message(self, chat_id: int | str, text: str) -> str:
        text = text.strip()
        command, _, args = text.partition(" ")
        command = command.split("@", 1)[0].lower()

        if command == "/whoami":
            return f"chat_id: {chat_id}"

        if command in {"/start", "/help"}:
            return self.help_text()

        if not self._is_authorized(chat_id):
            return (
                "Команда отклонена: этот chat_id не разрешен. "
                "Отправь /whoami и задай TELEGRAM_ALLOWED_CHAT_ID на машине с ботом."
            )

        config = TradingBotConfig.load(self.config_path)

        if command == "/status":
            return "\n\n".join([config.summary(), self.process.status()])

        if command == "/connect":
            parts = args.split(maxsplit=2)
            if len(parts) != 3:
                return "Формат: /connect <login> <server> <password>"
            try:
                config.login = int(parts[0])
            except ValueError:
                return "Login должен быть числом."
            config.server = parts[1]
            config.password = parts[2]
            config.save(self.config_path)
            return "Данные счета сохранены локально.\n\n" + check_mt5_connection(config)

        if command == "/set_path":
            if not args:
                return "Формат: /set_path <путь к terminal64.exe>"
            config.terminal_path = args.strip().strip('"')
            config.save(self.config_path)
            return "Путь к терминалу сохранен."

        if command == "/set_symbol":
            if not args:
                return "Формат: /set_symbol <symbol>"
            config.symbol = args.strip()
            config.save(self.config_path)
            return f"Инструмент сохранен: {config.symbol}"

        if command == "/set_volume":
            try:
                config.volume = float(args)
            except ValueError:
                return "Формат: /set_volume <volume>"
            config.save(self.config_path)
            return f"Объем сохранен: {config.volume}"

        if command == "/set_risk":
            try:
                config.risk_pct = float(args)
            except ValueError:
                return "Формат: /set_risk <0.02>"
            config.save(self.config_path)
            return f"Риск сохранен: {config.risk_pct:.4f}"

        if command == "/set_poll":
            try:
                config.poll_seconds = int(args)
            except ValueError:
                return "Формат: /set_poll <seconds>"
            config.save(self.config_path)
            return f"Частота проверки сохранена: {config.poll_seconds} сек."

        if command == "/test_mt5":
            return check_mt5_connection(config)

        if command == "/start_basic_dry":
            return self.process.start(config=config, dry_run=True, chat_id=chat_id)

        if command == "/start_basic_live":
            return self.process.start(config=config, dry_run=False, chat_id=chat_id)

        if command == "/stop_basic":
            return self.process.stop()

        if command == "/clear_account":
            if self.process.is_running():
                return "Сначала останови basic_backtest командой /stop_basic."
            if self.config_path.exists():
                self.config_path.unlink()
            return "Локальные данные счета удалены."

        return "Неизвестная команда. Отправь /help."

    def run_forever(self) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")
        if not self.allowed_chat_id:
            print(
                "TELEGRAM_ALLOWED_CHAT_ID не задан. "
                "Будет доступна только команда /whoami."
            )

        print("Telegram trading bot started.")
        offset = None

        while True:
            params: dict[str, Any] = {
                "timeout": self.timeout,
                "allowed_updates": json.dumps(["message"]),
            }
            if offset is not None:
                params["offset"] = offset

            try:
                response = self._api("getUpdates", params)
            except Exception as exc:
                print(f"Telegram polling failed: {exc}")
                time.sleep(5)
                continue

            for update in response.get("result", []):
                offset = int(update["update_id"]) + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = message.get("text")
                if chat_id is None or not text:
                    continue

                answer = self.handle_message(chat_id, text)
                self._send(chat_id, answer)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Запускает Telegram-бот для управления basic_backtest."
    )
    parser.add_argument("--token", default=None)
    parser.add_argument("--allowed-chat-id", default=None)
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bot = TelegramTradingBot(
        token=args.token,
        allowed_chat_id=args.allowed_chat_id,
        config_path=Path(args.config_path),
        timeout=args.timeout,
    )
    try:
        bot.run_forever()
        return 0
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
