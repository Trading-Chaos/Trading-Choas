from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from basic_backtest.execution.MT5Executor import MT5Executor
from input.mt5_candles import (
    MT5ConnectionConfig,
    MT5DataRecorder,
    connect_mt5,
    require_mt5,
    shutdown_mt5,
)
from input.Cleaner import clean_df
from output.telegram_bot import TelegramNotifier, format_trade_message

RAW_DATA_PATH = Path("input") / "data" / "BRENT_H1.csv"
CLEAN_DATA_PATH = Path("input") / "clean_df" / "BRENT_H1_clean.csv"


@dataclass
class BasicLiveConfig:
    symbol: str = "BRENT"
    timeframe: str = "H1"
    raw_path: Path = RAW_DATA_PATH
    clean_path: Path = CLEAN_DATA_PATH
    history_bars: int = 2000
    poll_seconds: int = 60
    volume: float = 1.0
    risk_pct: float = 0.02
    dry_run: bool = False
    backtest_name: str = "basic_backtest"


class BasicBrentH1Pipeline:
    def __init__(self, config: BasicLiveConfig):
        self.config = config
        self.recorder = MT5DataRecorder(
            symbol=config.symbol,
            timeframe=config.timeframe,
            output_path=config.raw_path,
            history_bars=config.history_bars,
            poll_seconds=config.poll_seconds,
            closed_bars_only=True,
        )
        self.executor = MT5Executor(symbol=config.symbol)
        self.notifier = TelegramNotifier.from_env()
        self.last_processed_time = self._load_last_processed_time(config.clean_path)

    @staticmethod
    def _load_last_processed_time(path: Path) -> pd.Timestamp | None:
        if not path.exists():
            return None

        df = pd.read_csv(path, usecols=["DateTime"])
        if df.empty:
            return None

        return pd.to_datetime(df["DateTime"], errors="coerce").max()

    def sync_and_clean(self) -> pd.DataFrame:
        self.recorder.sync_once()
        raw = pd.read_csv(self.config.raw_path)
        cleaned = clean_df(raw)
        self.config.clean_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned.to_csv(self.config.clean_path, index=False)
        return cleaned

    def _latest_closed_bar(self, cleaned: pd.DataFrame) -> pd.Series | None:
        if cleaned.empty:
            return None

        latest = cleaned.iloc[-1].copy()
        latest["DateTime"] = pd.to_datetime(latest["DateTime"], errors="coerce")
        if pd.isna(latest["DateTime"]):
            return None

        return latest

    def _stop_loss_for(self, side: int, entry_price: float) -> float | None:
        terminal = require_mt5()
        info = terminal.symbol_info(self.config.symbol)
        account = terminal.account_info()

        if info is None or account is None:
            return None

        tick_size = float(
            getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0
        )
        tick_value = float(getattr(info, "trade_tick_value", 0) or 0)
        if tick_size <= 0 or tick_value <= 0 or self.config.volume <= 0:
            return None

        multiplier = tick_value / tick_size
        risk_cash = float(account.equity) * self.config.risk_pct
        stop_distance = risk_cash / (self.config.volume * multiplier)

        return entry_price - stop_distance if side == 1 else entry_price + stop_distance

    def _account_snapshot(self) -> tuple[float | None, float | None]:
        terminal = require_mt5()
        account = terminal.account_info()
        if account is None:
            return None, None

        return float(account.balance), float(account.equity)

    @staticmethod
    def _entry_reason_text(reason: int) -> str:
        reasons = {
            1: "AO пересек нулевую линию",
            2: "три одноцветных столбца AO",
            3: "паттерн AO saucer",
        }
        return reasons.get(reason, "нет причины входа")

    def _notify(
        self,
        *,
        event_type: str,
        side: int | None,
        order_kind: str,
        volume: float | None,
        price: float | None,
        stop_loss: float | None,
        reason: str,
        status: str,
    ) -> None:
        balance, equity = self._account_snapshot()
        message = format_trade_message(
            backtest_name=self.config.backtest_name,
            event_type=event_type,
            symbol=self.config.symbol,
            side=side,
            order_kind=order_kind,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            balance=balance,
            equity=equity,
            reason=reason,
            status=status,
        )
        print(message)
        self.notifier.send_message(message)

    def process_latest_bar(self, latest: pd.Series) -> None:
        latest_time = latest["DateTime"]
        if (
            self.last_processed_time is not None
            and latest_time <= self.last_processed_time
        ):
            return

        self.last_processed_time = latest_time

        exit_signal = int(latest.get("ExitSignal", 0))
        entry_signal = int(latest.get("EntrySignal", 0))

        if exit_signal != 0 and self.executor.has_position():
            print(f"{latest_time}: ExitSignal={exit_signal}. Closing position.")
            if not self.config.dry_run:
                self.executor.cancel_all_stops()
                closed = self.executor.close_position()
                self._notify(
                    event_type="сделка",
                    side=None,
                    order_kind="закрытие позиции",
                    volume=None,
                    price=None,
                    stop_loss=None,
                    reason=f"ExitSignal={exit_signal}",
                    status="позиция закрыта" if closed else "ошибка закрытия",
                )
            else:
                self._notify(
                    event_type="сделка",
                    side=None,
                    order_kind="закрытие позиции",
                    volume=None,
                    price=None,
                    stop_loss=None,
                    reason=f"ExitSignal={exit_signal}",
                    status="dry-run",
                )
            return

        if entry_signal == 0:
            print(f"{latest_time}: no entry signal.")
            return

        if self.executor.has_exposure():
            print(f"{latest_time}: signal={entry_signal}, exposure already exists.")
            return

        entry_price = float(latest["High"] if entry_signal == 1 else latest["Low"])
        stop_loss = self._stop_loss_for(entry_signal, entry_price)
        entry_reason = int(latest.get("EntryReason", 0))
        reason_text = self._entry_reason_text(entry_reason)
        side_name = "LONG" if entry_signal == 1 else "SHORT"

        print(
            f"{latest_time}: placing {side_name} stop entry "
            f"volume={self.config.volume}, entry={entry_price}, sl={stop_loss}"
        )

        if not self.config.dry_run:
            result = self.executor.place_stop_entry(
                side=entry_signal,
                volume=self.config.volume,
                entry_price=entry_price,
                stop_loss=stop_loss,
            )
            ok = bool(result and result.retcode == require_mt5().TRADE_RETCODE_DONE)
            self._notify(
                event_type="заявка",
                side=entry_signal,
                order_kind=f"{side_name} stop-entry",
                volume=self.config.volume,
                price=entry_price,
                stop_loss=stop_loss,
                reason=reason_text,
                status="выставлена" if ok else "ошибка выставления",
            )
        else:
            self._notify(
                event_type="заявка",
                side=entry_signal,
                order_kind=f"{side_name} stop-entry",
                volume=self.config.volume,
                price=entry_price,
                stop_loss=stop_loss,
                reason=reason_text,
                status="dry-run",
            )

    def run_once(self) -> None:
        cleaned = self.sync_and_clean()
        latest = self._latest_closed_bar(cleaned)
        if latest is not None:
            self.process_latest_bar(latest)

    def run_forever(self) -> None:
        print(
            f"Basic Brent H1 pipeline started: raw={self.config.raw_path}, "
            f"clean={self.config.clean_path}, poll={self.config.poll_seconds}s"
        )

        while True:
            self.run_once()
            time.sleep(self.config.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Запускает обычный live-контур Brent H1 без ML."
    )
    parser.add_argument("--symbol", default="BRENT")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--raw-path", default=str(RAW_DATA_PATH))
    parser.add_argument("--clean-path", default=str(CLEAN_DATA_PATH))
    parser.add_argument("--history-bars", type=int, default=2000)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--volume", type=float, default=1.0)
    parser.add_argument("--risk-pct", type=float, default=0.02)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")

    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--server", default=None)
    parser.add_argument("--terminal-path", default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--portable", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    env_config = MT5ConnectionConfig.from_env()
    connection = MT5ConnectionConfig(
        login=args.login if args.login is not None else env_config.login,
        password=args.password if args.password is not None else env_config.password,
        server=args.server if args.server is not None else env_config.server,
        path=args.terminal_path if args.terminal_path is not None else env_config.path,
        timeout=args.timeout if args.timeout is not None else env_config.timeout,
        portable=args.portable or env_config.portable,
    )
    config = BasicLiveConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        raw_path=Path(args.raw_path),
        clean_path=Path(args.clean_path),
        history_bars=args.history_bars,
        poll_seconds=args.poll_seconds,
        volume=args.volume,
        risk_pct=args.risk_pct,
        dry_run=args.dry_run,
    )

    try:
        connect_mt5(connection)
        pipeline = BasicBrentH1Pipeline(config)
        if args.once:
            pipeline.run_once()
        else:
            pipeline.run_forever()
        return 0
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        shutdown_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
