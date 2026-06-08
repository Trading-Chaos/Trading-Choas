from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_OHLC_COLUMNS = ["DateTime", "Open", "High", "Low", "Close"]


def _median_price(df: pd.DataFrame) -> pd.Series:
    return (df["High"].astype(float) + df["Low"].astype(float)) / 2.0


def _smma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _fractal_up(df: pd.DataFrame) -> pd.Series:
    high = df["High"].astype(float)
    mask = (
        (high > high.shift(1))
        & (high > high.shift(2))
        & (high > high.shift(-1))
        & (high > high.shift(-2))
    )
    return high.where(mask)


def _fractal_down(df: pd.DataFrame) -> pd.Series:
    low = df["Low"].astype(float)
    mask = (
        (low < low.shift(1))
        & (low < low.shift(2))
        & (low < low.shift(-1))
        & (low < low.shift(-2))
    )
    return low.where(mask)


def _binary_indicator(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return (series.notna() & numeric.fillna(1).ne(0)).astype(int)


def add_bill_williams_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    median = _median_price(df)

    if "AO" not in df.columns:
        df["AO"] = (
            median.rolling(5, min_periods=5).mean()
            - median.rolling(34, min_periods=34).mean()
        )

    if "Alligator_Jaw" not in df.columns:
        df["Alligator_Jaw"] = _smma(median, 13).shift(8)

    if "Alligator_Teeth" not in df.columns:
        df["Alligator_Teeth"] = _smma(median, 8).shift(5)

    if "Alligator_Lips" not in df.columns:
        df["Alligator_Lips"] = _smma(median, 5).shift(3)

    if "Fractal_Up" not in df.columns:
        df["Fractal_Up"] = _fractal_up(df)

    if "Fractal_Down" not in df.columns:
        df["Fractal_Down"] = _fractal_down(df)

    return df


def add_exit_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    lips = df["Alligator_Lips"]
    teeth = df["Alligator_Teeth"]
    jaw = df["Alligator_Jaw"]

    bullish = lips.gt(teeth) & teeth.gt(jaw)
    bearish = jaw.gt(teeth) & teeth.gt(lips)

    bull_flip = bullish & ~bullish.shift(1, fill_value=False).astype(bool)
    bear_flip = bearish & ~bearish.shift(1, fill_value=False).astype(bool)

    df["ExitSignal"] = 0
    position = 0

    for i in range(len(df)):
        if position == 1 and bool(bear_flip.iloc[i]):
            df.at[i, "ExitSignal"] = 1
            position = 0
        elif position == -1 and bool(bull_flip.iloc[i]):
            df.at[i, "ExitSignal"] = -1
            position = 0

        if position == 0 and df.at[i, "ExitSignal"] == 0:
            signal = int(df.at[i, "EntrySignal"])
            if signal != 0:
                position = signal

    return df


def clean_df(df: pd.DataFrame, build_missing_indicators: bool = True) -> pd.DataFrame:
    df = df.copy()

    missing = [column for column in REQUIRED_OHLC_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
    df = df[df["DateTime"].notna()].sort_values("DateTime").reset_index(drop=True)
    df = df.drop_duplicates(subset=["DateTime"], keep="last").reset_index(drop=True)

    if "Volume" in df.columns:
        df = df.drop(columns=["Volume"])

    if build_missing_indicators:
        df = add_bill_williams_indicators(df)

    required_indicators = [
        "AO",
        "Alligator_Jaw",
        "Alligator_Teeth",
        "Alligator_Lips",
        "Fractal_Up",
        "Fractal_Down",
    ]
    missing_indicators = [
        column for column in required_indicators if column not in df.columns
    ]
    if missing_indicators:
        raise ValueError(f"Missing indicator columns: {missing_indicators}")

    df["Fractal_Down"] = _binary_indicator(df["Fractal_Down"])
    df["Fractal_Up"] = _binary_indicator(df["Fractal_Up"])

    df["Fractal_Up_conf"] = df["Fractal_Up"].shift(2).fillna(0).astype(int)
    df["Fractal_Down_conf"] = df["Fractal_Down"].shift(2).fillna(0).astype(int)

    df["Color AO"] = (
        df["AO"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    )
    df["Color AO"] = df["Color AO"].fillna(0).astype(int)
    df["AO_sign"] = np.where(df["Color AO"] > 0, 1, -1)

    df["AO_zero_up"] = ((df["AO"] > 0) & (df["AO"].shift(1) <= 0)).astype(int)
    df["AO_zero_down"] = ((df["AO"] < 0) & (df["AO"].shift(1) >= 0)).astype(int)

    df["AO_three_green"] = (
        (df["AO_sign"] == 1)
        & (df["AO_sign"].shift(1) == 1)
        & (df["AO_sign"].shift(2) == 1)
    ).astype(int)

    df["AO_three_red"] = (
        (df["AO_sign"] == -1)
        & (df["AO_sign"].shift(1) == -1)
        & (df["AO_sign"].shift(2) == -1)
    ).astype(int)

    df["AO_saucer_up"] = (
        (df["AO"] > 0)
        & (df["AO"].shift(2) > df["AO"].shift(1))
        & (df["AO"] > df["AO"].shift(1))
    ).astype(int)

    df["AO_saucer_down"] = (
        (df["AO"] < 0)
        & (df["AO"].shift(2) < df["AO"].shift(1))
        & (df["AO"] < df["AO"].shift(1))
    ).astype(int)

    jaw, teeth, lips = df["Alligator_Jaw"], df["Alligator_Teeth"], df["Alligator_Lips"]

    bullish = (lips > teeth) & (teeth > jaw)
    bearish = (jaw > teeth) & (teeth > lips)

    df["AlligatorStart_Long"] = (bullish & ~bullish.shift(1, fill_value=False)).astype(
        int
    )
    df["AlligatorStart_Short"] = (bearish & ~bearish.shift(1, fill_value=False)).astype(
        int
    )

    df["EntrySignal"] = 0
    df["EntryReason"] = 0

    state = "flat"

    for i in range(len(df)):
        start_long = bool(df.at[i, "AlligatorStart_Long"])
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
    df = add_exit_signal(df)

    return df


def clean_file(
    input_path: str | Path, output_path: str | Path | None = None
) -> pd.DataFrame:
    input_path = Path(input_path)
    output_path = (
        Path(output_path)
        if output_path
        else input_path.with_name(f"{input_path.stem}_clean.csv")
    )

    cleaned = clean_df(pd.read_csv(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(output_path, index=False)
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean OHLC data and build strategy features."
    )
    parser.add_argument("input")
    parser.add_argument("--output")
    args = parser.parse_args()

    cleaned = clean_file(args.input, args.output)
    output = args.output or Path(args.input).with_name(
        f"{Path(args.input).stem}_clean.csv"
    )
    print(f"{output}: {len(cleaned)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
