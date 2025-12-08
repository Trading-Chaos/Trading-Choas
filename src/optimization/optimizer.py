from __future__ import annotations
import copy
import optuna
from .backtester import Backtester
from ..metrics import mar, sharpe, profit_factor

def _apply(cfg: dict, dotted_key: str, value):
    keys = dotted_key.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value

def suggest_params(trial: optuna.Trial, base_cfg: dict) -> dict:
    cfg = copy.deepcopy(base_cfg)
    # пример пространства поиска
    candidates = {
        "indicators.alligator.jaw": trial.suggest_int("gator_jaw", 5, 21),
        "indicators.alligator.teeth": trial.suggest_int("gator_teeth", 3, 13),
        "indicators.alligator.lips": trial.suggest_int("gator_lips", 3, 8),
        "indicators.ao.fast": trial.suggest_int("ao_fast", 3, 8),
        "indicators.ao.slow": trial.suggest_int("ao_slow", 21, 55),
        "risk.stop_atr_mult": trial.suggest_float("stop_mult", 1.0, 4.0),
        "risk.tp_atr_mult": trial.suggest_float("tp_mult", 1.5, 6.0),
        "rules.score_threshold": trial.suggest_int("score_thr", 1, 5),
    }
    for k, v in candidates.items():
        _apply(cfg, k, v)
    return cfg

def objective(trial: optuna.Trial, df, base_cfg, target: str = "MAR") -> float:
    cfg = suggest_params(trial, base_cfg)
    res = Backtester(df, cfg).run()
    if target.upper() == "SHARPE":
        return sharpe(res["returns"])
    if target.upper() == "PF":
        return profit_factor(res["returns"])
    return mar(res["equity"])

def run_optuna(df, base_cfg: dict, n_trials: int = 100, target: str = "MAR") -> optuna.Study:
    study = optuna.create_study(direction="maximize")
    study.optimize(lambda t: objective(t, df, base_cfg, target), n_trials=n_trials)
    return study