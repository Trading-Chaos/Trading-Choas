"""
Главная точка входа проекта (пакет src).

Собирает:
- Backtester
- Оптимизацию (Optuna)
- Walk-Forward анализ
- Метрики

И предоставляет удобные функции:
- run_pipeline(df, base_cfg, ...)        – полный цикл на переданном DataFrame
- load_clean_df(symbol)                  – загрузить df/clean_df/<symbol>.csv
- run_instrument(symbol, base_cfg, ...)  – полный цикл по одному инструменту
- run_all_instruments(base_cfg, ...)     – прогнать по AFKS/YDEX/Brent/Gold
- run_and_report(...)                    – запустить всё и вывести итоговый отчёт
"""

from __future__ import annotations
from typing import Any, Dict, List
import pathlib
import pandas as pd

# --- Импорт ядра стратегии ---

from .backtester import Backtester
from .metrics import summarize

# Оптимизация и Walk Forward
from .optimization.optimizer import run_optuna, suggest_params
from .optimization.wfa import walk_forward


# --- Пути к данным ---
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLEAN_DF_DIR = _PROJECT_ROOT / "df" / "clean_df"

DEFAULT_INSTRUMENTS = ["AFKS", "YDEX", "Brent", "Gold"]

__all__ = [
    "Backtester",
    "summarize",
    "run_optuna",
    "suggest_params",
    "walk_forward",
    "load_clean_df",
    "run_pipeline",
    "run_instrument",
    "run_all_instruments",
    "run_and_report",
]


# ======================================================================
# Утилита: загрузка подготовленных данных
# ======================================================================

def load_clean_df(symbol: str, *, path: pathlib.Path | None = None) -> pd.DataFrame:
    """
    Загрузить подготовленные данные из df/clean_df/<symbol>.csv.
    """
    root = path or _CLEAN_DF_DIR
    csv_path = root / f"{symbol}.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Не найден файл {csv_path}")

    df = pd.read_csv(csv_path)
    if "DateTime" in df.columns:
        df["DateTime"] = pd.to_datetime(df["DateTime"])
    return df


# ======================================================================
# Основной пайплайн для одного DataFrame
# ======================================================================

def run_pipeline(
    df: pd.DataFrame,
    base_cfg: Dict[str, Any],
    *,
    n_trials: int = 50,
    target: str = "MAR",
    window_in: str = "730D",
    window_out: str = "365D",
) -> Dict[str, Any]:
    """
    Полный цикл работы стратегии на одном DataFrame:

    1) Базовый бэктест на base_cfg.
    2) Optuna-оптимизация по целевой метрике (MAR/SHARPE/PF).
    3) Бэктест на лучших параметрах.
    4) Walk-forward анализ.
    """

    results: Dict[str, Any] = {}

    # --- 1. Базовый бэктест ---
    bt_base = Backtester(df, base_cfg).run()
    base_bt = bt_base.get("bt")
    base_trades = bt_base.get("trades", [])

    base_summary = None
    if isinstance(base_bt, pd.DataFrame):
        base_summary = summarize(base_bt, base_trades)

    results["base"] = {
        "raw": bt_base,
        "summary": base_summary,
    }

    # --- 2. Оптимизация ---
    study = run_optuna(df, base_cfg, n_trials=n_trials, target=target)
    best_trial = study.best_trial
    best_cfg = suggest_params(best_trial, base_cfg)

    # --- 3. Бэктест на лучших параметрах ---
    bt_best = Backtester(df, best_cfg).run()
    best_bt = bt_best.get("bt")
    best_trades = bt_best.get("trades", [])

    best_summary = None
    if isinstance(best_bt, pd.DataFrame):
        best_summary = summarize(best_bt, best_trades)

    results["opt"] = {
        "study": study,
        "best_cfg": best_cfg,
        "raw": bt_best,
        "summary": best_summary,
    }

    # --- 4. Walk-forward анализ ---
    wfa_res = walk_forward(
        df=df,
        base_cfg=base_cfg,
        window_in=window_in,
        window_out=window_out,
        trials=n_trials,
        target=target,
    )
    results["wfa"] = {"raw": wfa_res}

    return results


# ======================================================================
# Запуск пайплайна по подготовленным CSV
# ======================================================================

def run_instrument(
    symbol: str,
    base_cfg: Dict[str, Any],
    *,
    n_trials: int = 50,
    target: str = "MAR",
    window_in: str = "730D",
    window_out: str = "365D",
) -> Dict[str, Any]:
    """
    Запустить полный пайплайн для одного инструмента из df/clean_df.
    """
    df = load_clean_df(symbol)
    return run_pipeline(
        df=df,
        base_cfg=base_cfg,
        n_trials=n_trials,
        target=target,
        window_in=window_in,
        window_out=window_out,
    )


def run_all_instruments(
    base_cfg: Dict[str, Any],
    instruments: List[str] | None = None,
    *,
    n_trials: int = 50,
    target: str = "MAR",
    window_in: str = "730D",
    window_out: str = "365D",
) -> Dict[str, Dict[str, Any]]:
    """
    Запускает run_instrument по всем инструментам и возвращает словарь результатов.
    """
    insts = instruments or DEFAULT_INSTRUMENTS
    out: Dict[str, Dict[str, Any]] = {}

    for sym in insts:
        print(f"\n=== ▶ Запуск пайплайна для {sym} ===")
        out[sym] = run_instrument(
            sym,
            base_cfg,
            n_trials=n_trials,
            target=target,
            window_in=window_in,
            window_out=window_out,
        )
    return out


# ======================================================================
# Формирование и вывод отчёта
# ======================================================================

def summarize_results(results: dict) -> pd.DataFrame:
    """
    Делает табличку метрик по результатам run_all_instruments() или run_pipeline().
    """
    rows = []
    for symbol, res in results.items():
        base_sum = res["base"]["summary"]
        opt_sum = res["opt"]["summary"]

        if base_sum is None or opt_sum is None:
            continue

        rows.append({
            "Symbol": symbol,
            "CAGR % (Base)": round(base_sum["CAGR"] * 100, 2),
            "CAGR % (Opt)": round(opt_sum["CAGR"] * 100, 2),
            "MaxDD % (Base)": round(base_sum["MaxDD"] * 100, 2),
            "MaxDD % (Opt)": round(opt_sum["MaxDD"] * 100, 2),
            "MAR (Base)": round(base_sum["MAR"], 2),
            "MAR (Opt)": round(opt_sum["MAR"], 2),
            "Sharpe (Opt)": round(opt_sum["Sharpe"], 2),
            "PF (Opt)": round(opt_sum["PF"], 2),
        })

    df = pd.DataFrame(rows)
    df.set_index("Symbol", inplace=True)
    return df


def print_summary(df_summary: pd.DataFrame) -> None:
    """Простой форматированный вывод в консоль."""
    print("\n===== РЕЗЮМЕ ПО РЕЗУЛЬТАТАМ =====\n")
    print(df_summary.to_string())
    print("\n==================================\n")


def run_and_report(
    base_cfg: dict,
    *,
    instruments: list[str] | None = None,
    n_trials: int = 50,
    target: str = "MAR",
    window_in: str = "730D",
    window_out: str = "365D",
    save_csv: bool = True,
) -> pd.DataFrame:
    """
    Запускает полный цикл по всем инструментам и выводит табличный отчёт.
    """
    print("=== 🚀 Запуск полной оптимизации и WFA по всем инструментам ===")

    results = run_all_instruments(
        base_cfg=base_cfg,
        instruments=instruments,
        n_trials=n_trials,
        target=target,
        window_in=window_in,
        window_out=window_out,
    )

    df_summary = summarize_results(results)
    print_summary(df_summary)

    if save_csv:
        path = _PROJECT_ROOT / "results" / "summary.csv"
        path.parent.mkdir(exist_ok=True, parents=True)
        df_summary.to_csv(path)
        print(f"Файл сохранён: {path}")

    return df_summary