import pandas as pd
import numpy as np

name = input("Введите название инструмента(пример: AFKS, GOLD, YDEX):")

df: pd.DataFrame = pd.read_csv(f"/Users/side/Desktop/Trading Chaos AI/df/data/{name}_20.csv")

def clean_df(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    # === Базовая очистка ===
    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    df = df[df["DateTime"].notna()].sort_values("DateTime").reset_index(drop=True)

    if "Volume" in df.columns:
        df = df.drop(columns=["Volume"])

    # === Фракталы в бинарный формат ===
    df["Fractal_Down"] = df["Fractal_Down"].notna().astype(int)
    df["Fractal_Up"]   = df["Fractal_Up"].notna().astype(int)

    df["Fractal_Up_conf"]   = df["Fractal_Up"].shift(2).fillna(0).astype(int)
    df["Fractal_Down_conf"] = df["Fractal_Down"].shift(2).fillna(0).astype(int)

    # === AO ===
    df["Color AO"] = df["AO"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    df["Color AO"] = df["Color AO"].fillna(0).astype(int)

    df["AO_sign"] = np.where(df["Color AO"] > 0, 1, -1)

    df["AO_zero_up"]   = ((df["AO"] > 0) & (df["AO"].shift(1) <= 0)).astype(int)
    df["AO_zero_down"] = ((df["AO"] < 0) & (df["AO"].shift(1) >= 0)).astype(int)

    df["AO_three_green"] = (
        (df["AO_sign"] == 1) &
        (df["AO_sign"].shift(1) == 1) &
        (df["AO_sign"].shift(2) == 1)
    ).astype(int)

    df["AO_three_red"] = (
        (df["AO_sign"] == -1) &
        (df["AO_sign"].shift(1) == -1) &
        (df["AO_sign"].shift(2) == -1)
    ).astype(int)

    df["AO_saucer_up"] = (
        (df["AO"] > 0) &
        (df["AO"].shift(2) > df["AO"].shift(1)) &
        (df["AO"] > df["AO"].shift(1))
    ).astype(int)

    df["AO_saucer_down"] = (
        (df["AO"] < 0) &
        (df["AO"].shift(2) < df["AO"].shift(1)) &
        (df["AO"] < df["AO"].shift(1))
    ).astype(int)

    # === Аллигатор ===
    jaw, teeth, lips = df["Alligator_Jaw"], df["Alligator_Teeth"], df["Alligator_Lips"]

    bullish = (lips > teeth) & (teeth > jaw)
    bearish = (jaw > teeth) & (teeth > lips)

    df["AlligatorStart_Long"]  = (bullish & ~bullish.shift(1, fill_value=False)).astype(int)
    df["AlligatorStart_Short"] = (bearish & ~bearish.shift(1, fill_value=False)).astype(int)

    # === EntrySignal ===
    df["EntrySignal"] = 0
    df["EntryReason"] = 0

    state = "flat"

    for i in range(len(df)):

        start_long  = bool(df.at[i, "AlligatorStart_Long"])
        start_short = bool(df.at[i, "AlligatorStart_Short"])

        if state in ("flat", "in_long", "in_short"):
            if start_long:
                state = "wait_long"
            elif start_short:
                state = "wait_short"

        if state == "wait_long":
            if df.at[i, "AO_zero_up"] == 1:
                df.at[i, "EntrySignal"] = 1
                df.at[i, "EntryReason"] = 1
                state = "in_long"
            elif df.at[i, "AO_three_green"] == 1:
                df.at[i, "EntrySignal"] = 1
                df.at[i, "EntryReason"] = 2
                state = "in_long"
            elif df.at[i, "AO_saucer_up"] == 1:
                df.at[i, "EntrySignal"] = 1
                df.at[i, "EntryReason"] = 3
                state = "in_long"

        elif state == "wait_short":
            if df.at[i, "AO_zero_down"] == 1:
                df.at[i, "EntrySignal"] = -1
                df.at[i, "EntryReason"] = 1
                state = "in_short"
            elif df.at[i, "AO_three_red"] == 1:
                df.at[i, "EntrySignal"] = -1
                df.at[i, "EntryReason"] = 2
                state = "in_short"
            elif df.at[i, "AO_saucer_down"] == 1:
                df.at[i, "EntrySignal"] = -1
                df.at[i, "EntryReason"] = 3
                state = "in_short"

        if state in ("in_long", "wait_long") and start_short:
            state = "wait_short"

        if state in ("in_short", "wait_short") and start_long:
            state = "wait_long"

    df["EntryReason"] = df["EntryReason"].astype("int32")

    return df