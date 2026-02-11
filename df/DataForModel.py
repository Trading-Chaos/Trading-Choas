import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler
import os
from typing import List
from typing import Iterator
from typing import Tuple


def preprocess_dataset(df):

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
        horizons=horizons # type: ignore
    )

    leak_cols = (
        [f"Close_fwd_{h}" for h in horizons] + # type: ignore
        [f"ret_{h}" for h in horizons] + # type: ignore
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

def split_data(df, target, val_size=0.1, test_size=0.2, random_state=42, split_type="train_test"):
    
    X = df.drop(columns=[target])
    y = df[target]
    
    if split_type == "train_test":
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)
        return X_train, X_test, y_train, y_test
    
    elif split_type == "train_val_test":
        X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=(val_size + test_size), random_state=random_state)
        X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=(test_size / (val_size + test_size)), random_state=random_state)
        return X_train, X_val, X_test, y_train, y_val, y_test
    

def append_results(results: dict, path="/Users/side/Desktop/Trading Chaos AI/df/results/Results.csv"):
   
    results_df = pd.DataFrame([results])

    if os.path.exists(path):
        results_df.to_csv(path, mode="a", header=False, index=False)
    else:
        results_df.to_csv(path, mode="w", header=True, index=False)

    print(f"Results appended to {path}")