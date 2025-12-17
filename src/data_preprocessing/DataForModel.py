import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler
import os


def preprocess_dataset(df):

    df = df.copy()

    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = df.drop(columns=["DateTime"])

    df = df.dropna(subset=[
        "AddOn_Anchor_Level",
        "AddOn_Anchor_IsUp",
        "AddOn_Size_Pct"
    ]).reset_index(drop=True)

    scale_cols = [
        "Open", "High", "Low", "Close",
        "Alligator_Jaw", "Alligator_Teeth", "Alligator_Lips",
        "AO",
        "AddOn_Anchor_Level", "AddOn_Size_Pct"
    ]

    scaler = RobustScaler()
    df[scale_cols] = scaler.fit_transform(df[scale_cols])

    return df

def build_target(df: pd.DataFrame, h: int = 20, target_type: str = "classification") -> pd.DataFrame:

    df = df.copy()

    df["Close_fwd"] = df["Close"].shift(-h)

    df["ret_H"] = np.where(
        df["EntrySignal"] > 0,
        (df["Close_fwd"] - df["Close"]) / df["Close"],

        np.where(
            df["EntrySignal"] < 0,
            (df["Close"] - df["Close_fwd"]) / df["Close"],
            0.0
        )
    )

    if target_type == "classification":
        df["GoodTrade"] = ((df["EntrySignal"] != 0) & (df["ret_H"] > 0)).astype(int)

    df = df.dropna(subset=["Close_fwd"])

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