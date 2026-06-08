from pathlib import Path

from basic_backtest.live_brent_h1_pipeline import CLEAN_DATA_PATH, RAW_DATA_PATH
from input.mt5_candles import default_output_path


def test_basic_pipeline_uses_input_data_paths():
    assert RAW_DATA_PATH == Path("input") / "data" / "BRENT_H1.csv"
    assert CLEAN_DATA_PATH == Path("input") / "clean_df" / "BRENT_H1_clean.csv"


def test_mt5_recorder_default_path_lives_in_input():
    assert default_output_path("BRENT", "H1") == Path("input") / "data" / "BRENT_H1.csv"
