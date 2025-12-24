import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
import os
from typing import List
from typing import Iterator
from typing import Tuple
from preprocessing.target import ttp_target, event_target, hybrid_target
from datetime import datetime
import json
import hashlib


def prep(
    df: pd.DataFrame,
    target_fn,
    target_name: str,
    target_col: str,
    train_size: int,
    test_size: int,
    step: int,
    horizons=None,
    target_kwargs=None,
    scale_cols=None,
    extra_target_fns=None
):
    target_kwargs = target_kwargs or {}
    extra_target_fns = extra_target_fns or []

    df_feat = preprocess_features_only(df)

    if target_name == "ttp":
        df_labeled = target_fn(df_feat, horizons=horizons, **target_kwargs)
    else:
        df_labeled = target_fn(df_feat, **target_kwargs)

    for fn in extra_target_fns:
        df_labeled = fn(df_labeled)

    if target_name == "ttp":
        leak_cols = get_leak_cols("ttp", horizons)
    else:
        leak_cols = get_leak_cols(target_name, horizons)

    for c in leak_cols:
        if c in df_labeled.columns:
            df_labeled = df_labeled.drop(columns=c)

    obj_cols = df_labeled.select_dtypes(include=["object"]).columns
    if len(obj_cols) > 0:
        df_labeled = df_labeled.drop(columns=obj_cols)

    for X_train, X_test, y_train, y_test in walk_forward_split(
        df_labeled,
        target_col=target_col,
        train_size=train_size,
        test_size=test_size,
        step=step
    ):
        scaler = None
        if scale_cols:
            X_train, X_test, scaler = scale_train_test(
                X_train, X_test
            )

        yield X_train, X_test, y_train, y_test, scaler

def preprocess_features_only(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "DateTime" in df.columns:
        df["DateTime"] = pd.to_datetime(df["DateTime"])
        df = df.sort_values("DateTime").reset_index(drop=True)
        df = df.drop(columns=["DateTime"])

    df = df.dropna(subset=[
        "AddOn_Anchor_Level",
        "AddOn_Anchor_IsUp",
        "AddOn_Size_Pct"
    ]).reset_index(drop=True)

    return df

def get_leak_cols(target_name: str, horizons=None):
    if target_name == "ttp":
        return (
            [f"Close_fwd_{h}" for h in horizons] +
            [f"ret_{h}" for h in horizons] +
            ["TTP"]
        )
    elif target_name == "event":
        return []
    elif target_name == "hybrid":
        return ["max_ret"]
    else:
        raise ValueError(f"Unknown target_name={target_name}")

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

def _hash_params(params: dict) -> str:
    s = json.dumps(params, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:8]


def append_results(
    results: dict,
    path="/Users/side/Desktop/Trading Chaos AI/df/results/Results.csv"
):
    """
    results — уже готовый dict из model_zoo
    """

    results = results.copy()

    # --- META ---
    results.setdefault("timestamp", datetime.utcnow().isoformat())
    results.setdefault("run_id", "default")
    results.setdefault("wfs_step", None)

    # --- MODEL ---
    if "model_params" in results:
        results["params_hash"] = _hash_params(results["model_params"])
        for k, v in results["model_params"].items():
            results[k] = v
        del results["model_params"]

    # --- to DataFrame ---
    results_df = pd.DataFrame([results])

    if os.path.exists(path):
        results_df.to_csv(path, mode="a", header=False, index=False)
    else:
        results_df.to_csv(path, mode="w", header=True, index=False)

    return results_df

import numpy as np
from sklearn.metrics import precision_score, recall_score

def eval_thresholds(
    y_true,
    y_proba,
    thresholds=np.arange(0.3, 0.81, 0.05)
):
    rows = []

    for thr in thresholds:
        y_pred = (y_proba >= thr).astype(int)

        coverage = y_pred.mean()  # % разрешённых сделок

        if coverage == 0:
            continue

        rows.append({
            "threshold": thr,
            "coverage": coverage,
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
        })

    return rows