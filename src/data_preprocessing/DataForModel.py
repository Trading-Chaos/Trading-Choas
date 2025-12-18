import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
import os
from typing import List
from typing import Iterator
from typing import Tuple

def preprocess_dataset(
    df: pd.DataFrame,
    horizons: List[int] = [12, 24, 48]
) -> pd.DataFrame:

    df = df.copy()

    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df = df.sort_values("DateTime").reset_index(drop=True)
    df = df.drop(columns=["DateTime"])

    df = df.dropna(subset=[
        "AddOn_Anchor_Level",
        "AddOn_Anchor_IsUp",
        "AddOn_Size_Pct"
    ]).reset_index(drop=True)

    df = build_target(
        df,
        horizons=horizons
    )

    leak_cols = (
        [f"Close_fwd_{h}" for h in horizons] +
        [f"ret_{h}" for h in horizons] +
        ["TTP"]
    )

    df = df.drop(columns=leak_cols)

    return df

def build_target(
    df: pd.DataFrame,
    horizons: List[int] = [12, 24, 48]
) -> pd.DataFrame:

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

    def _ttp_to_class(ttp):
        if pd.isna(ttp):
            return 3  # no_profit
        if ttp <= horizons[0]:
            return 0
        elif ttp <= horizons[1]:
            return 1
        elif ttp <= horizons[2]:
            return 2
        else:
            return 3

    df["TTP_class"] = df["TTP"].apply(_ttp_to_class)

    fwd_cols = [f"Close_fwd_{h}" for h in horizons]
    df = df.dropna(subset=fwd_cols)

    df = df[df["EntrySignal"] != 0]

    return df

def walk_forward_split(
    df: pd.DataFrame,
    target_col: str,
    train_size: int,
    test_size: int,
    step: int
) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]]:

    df = df.sort_index()
    n = len(df)

    start = 0
    while start + train_size + test_size <= n:
        train = df.iloc[start : start + train_size]
        test  = df.iloc[start + train_size : start + train_size + test_size]

        X_train = train.drop(columns=[target_col])
        y_train = train[target_col]

        X_test = test.drop(columns=[target_col])
        y_test = test[target_col]

        yield X_train, X_test, y_train, y_test

        start += step

def scale_train_test(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame, RobustScaler]:

    scaler = RobustScaler()

    X_train = X_train.copy()
    X_test = X_test.copy()
    scale_cols = [
    "Open", "High", "Low", "Close",
    "Alligator_Jaw", "Alligator_Teeth", "Alligator_Lips",
    "AO",
    "AddOn_Anchor_Level", "AddOn_Size_Pct"
]
    X_train[scale_cols] = scaler.fit_transform(X_train[scale_cols])
    X_test[scale_cols] = scaler.transform(X_test[scale_cols])

    return X_train, X_test, scaler

def prep(
    df: pd.DataFrame,
    horizons: List[int],
    target_col: str,
    train_size: int,
    test_size: int,
    step: int
) -> Iterator[
    Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, RobustScaler]
]:

    df_prep = preprocess_dataset(
        df,
        horizons=horizons
    )

    for X_train, X_test, y_train, y_test in walk_forward_split(
        df_prep,
        target_col=target_col,
        train_size=train_size,
        test_size=test_size,
        step=step
    ):
        X_train_scaled, X_test_scaled, scaler = scale_train_test(
            X_train,
            X_test
        )

        yield X_train_scaled, X_test_scaled, y_train, y_test, scaler

def append_results(results: dict, path="/Users/side/Desktop/Trading Chaos AI/df/results/Results.csv"):
   
    results_df = pd.DataFrame([results])

    if os.path.exists(path):
        results_df.to_csv(path, mode="a", header=False, index=False)
    else:
        results_df.to_csv(path, mode="w", header=True, index=False)

    print(f"Results appended to {path}")