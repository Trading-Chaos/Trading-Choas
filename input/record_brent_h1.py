from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from .mt5_candles import (
    MT5ConnectionConfig,
    MT5DataRecorder,
    connect_mt5,
    shutdown_mt5,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Записывает H1-свечи Brent из MetaTrader 5 в input/data/BRENT_H1.csv."
    )

    parser.add_argument("--symbol", default=os.getenv("MT5_SYMBOL", "Brent"))
    parser.add_argument("--timeframe", default=os.getenv("MT5_TIMEFRAME", "H1"))
    parser.add_argument("--output", default=os.getenv("MT5_OUTPUT"))
    parser.add_argument(
        "--history-bars", type=int, default=int(os.getenv("MT5_HISTORY_BARS", "2000"))
    )
    parser.add_argument(
        "--poll-seconds", type=int, default=int(os.getenv("MT5_POLL_SECONDS", "60"))
    )
    parser.add_argument("--include-current-bar", action="store_true")
    parser.add_argument("--once", action="store_true")

    parser.add_argument("--login", type=int, default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--server", default=None)
    parser.add_argument("--terminal-path", default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--portable", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    if load_dotenv is not None:
        load_dotenv()

    args = build_parser().parse_args(argv)

    output = (
        args.output or Path("input") / "data" / f"BRENT_{args.timeframe.upper()}.csv"
    )
    env_config = MT5ConnectionConfig.from_env()
    config = MT5ConnectionConfig(
        login=args.login if args.login is not None else env_config.login,
        password=args.password if args.password is not None else env_config.password,
        server=args.server if args.server is not None else env_config.server,
        path=args.terminal_path if args.terminal_path is not None else env_config.path,
        timeout=args.timeout if args.timeout is not None else env_config.timeout,
        portable=args.portable or env_config.portable,
    )

    try:
        connect_mt5(config)
        recorder = MT5DataRecorder(
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_path=output,
            history_bars=args.history_bars,
            poll_seconds=args.poll_seconds,
            closed_bars_only=not args.include_current_bar,
        )

        if args.once:
            added_count, latest_time = recorder.sync_once()
            print(f"{recorder.output_path}: +{added_count} rows, latest={latest_time}")
        else:
            recorder.run_forever()

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
