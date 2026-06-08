from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError as exc:  # pragma: no cover - MT5 is Windows-terminal bound.
    mt5 = None
    MT5_IMPORT_ERROR = exc
else:
    MT5_IMPORT_ERROR = None


TIMEFRAME_ATTRS = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M6": "TIMEFRAME_M6",
    "M10": "TIMEFRAME_M10",
    "M12": "TIMEFRAME_M12",
    "M15": "TIMEFRAME_M15",
    "M20": "TIMEFRAME_M20",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H2": "TIMEFRAME_H2",
    "H3": "TIMEFRAME_H3",
    "H4": "TIMEFRAME_H4",
    "H6": "TIMEFRAME_H6",
    "H8": "TIMEFRAME_H8",
    "H12": "TIMEFRAME_H12",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
    "MN1": "TIMEFRAME_MN1",
}

RATE_COLUMNS = [
    "DateTime",
    "Open",
    "High",
    "Low",
    "Close",
    "TickVolume",
    "Spread",
    "RealVolume",
]


@dataclass(frozen=True)
class MT5ConnectionConfig:
    login: int | None = None
    password: str | None = None
    server: str | None = None
    path: str | None = None
    timeout: int = 60000
    portable: bool = False

    @classmethod
    def from_env(cls) -> "MT5ConnectionConfig":
        login = os.getenv("MT5_LOGIN")
        timeout = os.getenv("MT5_TIMEOUT")

        return cls(
            login=int(login) if login else None,
            password=os.getenv("MT5_PASSWORD") or None,
            server=os.getenv("MT5_SERVER") or None,
            path=os.getenv("MT5_PATH") or None,
            timeout=int(timeout) if timeout else 60000,
            portable=os.getenv("MT5_PORTABLE", "").lower() in {"1", "true", "yes"},
        )

    def as_initialize_kwargs(self) -> dict:
        kwargs = {
            "timeout": self.timeout,
            "portable": self.portable,
        }

        if self.path:
            kwargs["path"] = self.path
        if self.login is not None:
            kwargs["login"] = self.login
        if self.password:
            kwargs["password"] = self.password
        if self.server:
            kwargs["server"] = self.server

        return kwargs


def require_mt5():
    if mt5 is None:
        raise RuntimeError(
            "Python package MetaTrader5 is not available in this environment. "
            "Run this recorder on Windows with MetaTrader 5 installed and install "
            "dependencies with `pip install -r requirements.txt`."
        ) from MT5_IMPORT_ERROR

    return mt5


def connect_mt5(config: MT5ConnectionConfig | None = None):
    terminal = require_mt5()
    config = config or MT5ConnectionConfig.from_env()

    if not terminal.initialize(**config.as_initialize_kwargs()):
        raise RuntimeError(f"MT5 initialize failed: {terminal.last_error()}")

    account = terminal.account_info()
    if account is not None:
        print(f"MT5 connected: login={account.login}, server={account.server}")
    else:
        print("MT5 connected")

    return terminal


def shutdown_mt5() -> None:
    if mt5 is not None:
        mt5.shutdown()


def resolve_timeframe(timeframe: str) -> int:
    terminal = require_mt5()
    key = timeframe.upper()

    attr = TIMEFRAME_ATTRS.get(key)
    if attr is None:
        allowed = ", ".join(sorted(TIMEFRAME_ATTRS))
        raise ValueError(f"Unsupported timeframe `{timeframe}`. Allowed: {allowed}")

    return getattr(terminal, attr)


def find_symbol_candidates(query: str, limit: int = 20) -> list[str]:
    terminal = require_mt5()
    symbols = terminal.symbols_get()

    if symbols is None:
        return []

    needle = query.lower()
    candidates = []

    for symbol in symbols:
        haystack = " ".join(
            str(value)
            for value in (
                getattr(symbol, "name", ""),
                getattr(symbol, "path", ""),
                getattr(symbol, "description", ""),
            )
        ).lower()

        if needle in haystack:
            candidates.append(symbol.name)

    return candidates[:limit]


def select_symbol(symbol: str) -> None:
    terminal = require_mt5()
    info = terminal.symbol_info(symbol)

    if info is None:
        candidates = find_symbol_candidates("brent")
        hint = (
            f" Brent-like symbols found: {', '.join(candidates)}" if candidates else ""
        )
        raise RuntimeError(f"MT5 symbol `{symbol}` was not found.{hint}")

    if not info.visible and not terminal.symbol_select(symbol, True):
        raise RuntimeError(f"MT5 symbol `{symbol}` exists but cannot be selected.")


def default_output_path(symbol: str, timeframe: str) -> Path:
    return Path("input") / "data" / f"{symbol}_{timeframe.upper()}.csv"


def rates_to_frame(rates) -> pd.DataFrame:
    if rates is None or len(rates) == 0:
        return pd.DataFrame(columns=RATE_COLUMNS)

    df = pd.DataFrame(rates)
    df["DateTime"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)

    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "TickVolume",
            "spread": "Spread",
            "real_volume": "RealVolume",
        }
    )

    return df[RATE_COLUMNS].sort_values("DateTime").reset_index(drop=True)


def load_existing_rates(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=RATE_COLUMNS)

    df = pd.read_csv(path)
    if "DateTime" not in df.columns:
        raise ValueError(f"`{path}` exists but has no DateTime column.")

    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    df = df[df["DateTime"].notna()].copy()

    for column in RATE_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    return df[RATE_COLUMNS].sort_values("DateTime").reset_index(drop=True)


def merge_rates(existing: pd.DataFrame, new_rates: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        merged = new_rates.copy()
    elif new_rates.empty:
        merged = existing.copy()
    else:
        merged = pd.concat([existing, new_rates], ignore_index=True)

    if merged.empty:
        return pd.DataFrame(columns=RATE_COLUMNS)

    merged["DateTime"] = pd.to_datetime(merged["DateTime"], errors="coerce")
    merged = merged[merged["DateTime"].notna()]
    merged = merged.drop_duplicates(subset=["DateTime"], keep="last")
    return merged[RATE_COLUMNS].sort_values("DateTime").reset_index(drop=True)


def write_rates(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


class MT5DataRecorder:
    def __init__(
        self,
        symbol: str = "Brent",
        timeframe: str = "H1",
        output_path: str | Path | None = None,
        history_bars: int = 2000,
        poll_seconds: int = 60,
        closed_bars_only: bool = True,
    ):
        self.symbol = symbol
        self.timeframe = timeframe.upper()
        self.timeframe_value = resolve_timeframe(self.timeframe)
        self.output_path = (
            Path(output_path) if output_path else default_output_path(symbol, timeframe)
        )
        self.history_bars = history_bars
        self.poll_seconds = poll_seconds
        self.closed_bars_only = closed_bars_only
        select_symbol(self.symbol)

    def fetch_rates(self) -> pd.DataFrame:
        terminal = require_mt5()
        start_pos = 1 if self.closed_bars_only else 0
        rates = terminal.copy_rates_from_pos(
            self.symbol,
            self.timeframe_value,
            start_pos,
            self.history_bars,
        )

        if rates is None:
            raise RuntimeError(
                f"MT5 copy_rates_from_pos failed: {terminal.last_error()}"
            )

        return rates_to_frame(rates)

    def sync_once(self) -> tuple[int, pd.Timestamp | None]:
        existing = load_existing_rates(self.output_path)
        before_count = len(existing)

        rates = self.fetch_rates()
        merged = merge_rates(existing, rates)
        write_rates(self.output_path, merged)

        added_count = max(len(merged) - before_count, 0)
        latest_time = merged["DateTime"].iloc[-1] if not merged.empty else None
        return added_count, latest_time

    def run_forever(self) -> None:
        print(
            f"Recording {self.symbol}_{self.timeframe} to {self.output_path} "
            f"every {self.poll_seconds}s"
        )

        while True:
            added_count, latest_time = self.sync_once()
            if latest_time is None:
                print("No rates received yet.")
            else:
                print(f"{self.output_path}: +{added_count} rows, latest={latest_time}")

            time.sleep(self.poll_seconds)
