import numpy as np
import pandas as pd
from typing import List


import numpy as np
import pandas as pd
from typing import List

def ttp_target(
    df: pd.DataFrame,
    horizons: List[int] = [12, 24, 48],
    n_classes: int = 4
) -> pd.DataFrame:

    assert n_classes in (2, 3, 4), "n_classes must be 2, 3 or 4"

    df = df.copy()

    for h in horizons:
        df[f"Close_fwd_{h}"] = df["Close"].shift(-h)

    for h in horizons:
        df[f"ret_{h}"] = np.where(
            df["EntrySignal"] > 0,
            (df[f"Close_fwd_{h}"] - df["Close"]) / df["Close"],
            np.where(
                df["EntrySignal"] < 0,
                (df["Close"] - df[f"Close_fwd_{h}"]) / df["Close"],
                np.nan
            )
        )

    def _calc_ttp(row):
        if row["EntrySignal"] == 0:
            return np.nan
        for h in horizons:
            if row[f"ret_{h}"] > 0:
                return h
        return np.nan

    df["TTP"] = df.apply(_calc_ttp, axis=1)

    def _ttp_to_4class(ttp):
        if pd.isna(ttp):
            return 3  # no_profit
        if ttp <= horizons[0]:
            return 0  # fast
        elif ttp <= horizons[1]:
            return 1  # mid
        elif ttp <= horizons[2]:
            return 2  # slow
        else:
            return 3

    df["TTP_class"] = df["TTP"].apply(_ttp_to_4class)

    if n_classes == 3:
        # 0,1 -> 0 (good)
        # 2   -> 1 (slow)
        # 3   -> 2 (no_profit)
        df["TTP_class"] = df["TTP_class"].map({
            0: 0,
            1: 0,
            2: 1,
            3: 2
        })

    elif n_classes == 2:
        # 0,1,2 -> 1 (good)
        # 3     -> 0 (no_profit)
        df["TTP_class"] = df["TTP_class"].map({
            0: 1,
            1: 1,
            2: 1,
            3: 0
        })

    fwd_cols = [f"Close_fwd_{h}" for h in horizons]
    df = df.dropna(subset=fwd_cols)
    df = df[df["EntrySignal"] != 0]

    return df

def event_target(
    df,
    tp=0.05,
    sl=0.02,
    max_bars=500
):
    df = df.copy()
    close = df["Close"].values
    target = []

    for i in range(len(df)):
        if df.loc[i, "EntrySignal"] == 0:
            target.append(np.nan)
            continue

        entry = close[i]
        side = df.loc[i, "EntrySignal"]
        hit = 0

        for j in range(i + 1, min(i + max_bars, len(df))):
            ret = (close[j] - entry) / entry if side > 0 else (entry - close[j]) / entry

            if ret >= tp:
                hit = 1
                break
            if ret <= -sl:
                hit = 0
                break

        target.append(hit)

    df["EventHit"] = target
    return df.dropna(subset=["EventHit"])


def hybrid_target(
    df: pd.DataFrame,
    tp: float = 0.05,
    sl: float = 0.02,
    max_bars: int = 500
) -> pd.DataFrame:

    df = df.copy()
    close = df["Close"].values
    signal = df["EntrySignal"].values

    max_ret_list = []
    good_trade_list = []

    for i in range(len(df)):

        if signal[i] == 0:
            max_ret_list.append(np.nan)
            good_trade_list.append(np.nan)
            continue

        entry = close[i]
        side = signal[i]

        max_ret = 0.0
        hit_tp = False

        for j in range(i + 1, min(i + max_bars, len(df))):

            ret = (
                (close[j] - entry) / entry
                if side > 0
                else (entry - close[j]) / entry
            )

            max_ret = max(max_ret, ret)

            if ret <= -sl:
                break

            if ret >= tp:
                hit_tp = True
                break

        max_ret_list.append(max_ret)
        good_trade_list.append(1 if hit_tp else 0)

    df["max_ret"] = max_ret_list
    df["GoodTrade"] = good_trade_list

    df = df.dropna(subset=["GoodTrade"])

    return df