import numpy as np
import pandas as pd

from input.Cleaner import clean_df


def test_clean_df_builds_indicators_from_ohlc():
    rows = 90
    base = 70 + np.sin(np.arange(rows) / 5) * 2 + np.arange(rows) * 0.02
    raw = pd.DataFrame(
        {
            "DateTime": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "Open": base,
            "High": base + 0.5,
            "Low": base - 0.5,
            "Close": base + 0.1,
            "TickVolume": np.arange(rows) + 100,
            "Spread": 2,
            "RealVolume": 0,
        }
    )

    cleaned = clean_df(raw)

    assert len(cleaned) == rows
    assert "AO" in cleaned.columns
    assert "Alligator_Jaw" in cleaned.columns
    assert "Alligator_Teeth" in cleaned.columns
    assert "Alligator_Lips" in cleaned.columns
    assert "Fractal_Up" in cleaned.columns
    assert "Fractal_Down" in cleaned.columns
    assert "EntrySignal" in cleaned.columns
    assert "ExitSignal" in cleaned.columns
