import pandas as pd
import numpy as np

def summarize(bt: pd.DataFrame, trades: list):
    res = {}
    res["final_equity"] = float(bt["Equity"].iloc[-1])

    # --- устойчивый расчёт CAGR ---
    dt = pd.to_datetime(bt["DateTime"], errors="coerce")
    # используем первые и последние валидные значения
    valid = dt.notna()
    if valid.sum() >= 2:
        t0 = dt[valid].iloc[0]
        t1 = dt[valid].iloc[-1]
        seconds = (t1 - t0).total_seconds()
        years = max(seconds / (365.25 * 24 * 3600), 1e-9)
        res["CAGR"] = res["final_equity"] ** (1 / years) - 1
    else:
        # fallback: если времени нет, оценим по числу баров (без календарной привязки)
        bars = len(bt)
        # допустим дневные данные: 252 бара в год; при другом ТФ поменяй коэффициент
        years = max(bars / 252.0, 1e-9)
        res["CAGR"] = res["final_equity"] ** (1 / years) - 1

    # --- макс. просадка ---
    roll_max = bt["Equity"].cummax()
    dd = bt["Equity"] / roll_max - 1.0
    res["MaxDD"] = float(dd.min())

    # --- сделки ---
    res["NumTrades"] = len(trades)
    if trades:
        wins, rets = 0, []
        for t in trades:
            r = (t["exit_price"]/t["entry_price"] - 1.0) if t["side"]=="LONG" else (t["entry_price"]/t["exit_price"] - 1.0)
            rets.append(r)
            if r > 0: wins += 1
        res["WinRate"] = wins / len(trades)
        res["AvgTradeRet"] = float(np.mean(rets))
        res["MedianTradeRet"] = float(np.median(rets))
    else:
        res["WinRate"] = res["AvgTradeRet"] = res["MedianTradeRet"] = np.nan
    return res
