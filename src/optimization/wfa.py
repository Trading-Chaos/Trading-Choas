from __future__ import annotations
import pandas as pd
from .optimizer import run_optuna
from .backtester import Backtester

def walk_forward(
    df: pd.DataFrame,
    base_cfg: dict,
    window_in: str = "730D",
    window_out: str = "365D",
    trials: int = 100,
    target: str = "MAR"
):
    win_in = pd.Timedelta(window_in)
    win_out = pd.Timedelta(window_out)

    t0 = df.index.min()
    t1 = t0 + win_in
    results = []
    out_equity = None

    while t1 + win_out <= df.index.max():
        train = df[(df.index >= t0) & (df.index < t1)]
        study = run_optuna(train, base_cfg, n_trials=trials, target=target)
        best_cfg = base_cfg.copy()
        # аккуратная «встройка» найденных параметров
        for k, v in study.best_params.items():
            # соответствие ключей см. optimizer.suggest_params
            if k == "gator_jaw":
                best_cfg["indicators"]["alligator"]["jaw"] = v
            elif k == "gator_teeth":
                best_cfg["indicators"]["alligator"]["teeth"] = v
            elif k == "gator_lips":
                best_cfg["indicators"]["alligator"]["lips"] = v
            elif k == "ao_fast":
                best_cfg["indicators"]["ao"]["fast"] = v
            elif k == "ao_slow":
                best_cfg["indicators"]["ao"]["slow"] = v
            elif k == "stop_mult":
                best_cfg["risk"]["stop_atr_mult"] = v
            elif k == "tp_mult":
                best_cfg["risk"]["tp_atr_mult"] = v
            elif k == "score_thr":
                best_cfg["rules"]["score_threshold"] = v

        test = df[(df.index >= t1) & (df.index < t1 + win_out)]
        res = Backtester(test, best_cfg).run()

        results.append({
            "period_in": (t0, t1),
            "period_out": (t1, t1 + win_out),
            "equity": res["equity"],
            "cfg": best_cfg,
            "study_value": study.best_value
        })

        out_equity = (res["equity"] if out_equity is None
                      else out_equity.append(res["equity"]).groupby(level=0).last())

        t0 = t0 + win_out
        t1 = t0 + win_in

    return {"segments": results, "equity_out": out_equity}