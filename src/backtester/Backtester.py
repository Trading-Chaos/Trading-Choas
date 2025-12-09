import pandas as pd
import numpy as np
 
# -------- Флаги отладки --------
CHECKS = True  # поставить False, если не нужны проверки ГО/добора

# -------- Параметры инструмента --------
TICK_SIZE    = 0.01
TICK_VALUE   = 7.94715
MULTIPLIER   = TICK_VALUE / TICK_SIZE      # ≈ 794.715 / 1.0 цены (или 808.61, если так в спецификации)
GO_LONG      = 8_171.27
GO_SHORT     = 8_299.81

# -------- Торговые параметры --------
START_EQUITY       = 100_000.0
STOP_RISK_PCT_MAIN = 0.02        # 2% риска на основную ногу
STOP_RISK_PCT_ADD  = 0.02        # 2% риска на добор
EXPOSURE_FRACTION  = 1.0         # доля equity, доступная под ГО
ADDON_RATIO        = 0.50        # добор 50% от основной
MAX_LEVERAGE       = 1.0         # суммарное ГО <= equity * MAX_LEVERAGE
EXEC_EXIT          = "open_next"
EXEC_ADDON         = "open_next"

# Вариант 1: минимальное движение цены в нашу сторону перед добором
MIN_MOVE_FOR_ADD_PCT = 0.005     # 0.5% в нашу сторону; чтобы выключить — поставить 0.0

# Вариант 2: подтягивание стопа основной ноги после добора
TIGHTEN_MAIN_STOP_AFTER_ADD        = True  # включить/выключить механику
STOP_MAIN_TIGHTEN_FACTOR_AFTER_ADD = 0.5   # во сколько раз уменьшать риск основной ноги (0.5 = вдвое)

# Комиссия
FEE_PER_SIDE_PER_CONTRACT = 0.45
def fee_cash(qty: float) -> float:
    return float(qty) * FEE_PER_SIDE_PER_CONTRACT


# -------- Подготовка данных --------
df_bt = df.copy().sort_values("DateTime").reset_index(drop=True)
df_bt["DateTime"] = pd.to_datetime(df_bt["DateTime"], errors="coerce")
df_bt = df_bt[df_bt["DateTime"].notna()].reset_index(drop=True)

req = [
    "Open", "High", "Low", "Close", "EntrySignal",
    "Alligator_Jaw", "Alligator_Teeth", "Alligator_Lips",
    "Fractal_Up", "Fractal_Down"
]
miss = [c for c in req if c not in df_bt.columns]
if miss:
    raise ValueError(f"Нет колонок: {miss}")

# подтверждённые фракталы (через 2 бара)
df_bt["Fractal_Up_conf"]   = df_bt["Fractal_Up"].shift(2).fillna(0).astype(int)
df_bt["Fractal_Down_conf"] = df_bt["Fractal_Down"].shift(2).fillna(0).astype(int)

# --- Аллигатор и flip-выход ---
lips  = df_bt["Alligator_Lips"]
teeth = df_bt["Alligator_Teeth"]
jaw   = df_bt["Alligator_Jaw"]

bull = (lips > teeth) & (teeth > jaw)
bear = (jaw  > teeth) & (teeth > lips)

bull_flip = bull & ~bull.shift(1).fillna(False)
bear_flip = bear & ~bear.shift(1).fillna(False)

df_bt["ExitSignal"] = 0
_pos = 0
for i in range(len(df_bt)):
    if _pos == 1 and bear_flip.iloc[i]:
        df_bt.at[i, "ExitSignal"] = 1
        _pos = 0
    elif _pos == -1 and bull_flip.iloc[i]:
        df_bt.at[i, "ExitSignal"] = -1
        _pos = 0

    if _pos == 0 and df_bt.at[i, "ExitSignal"] == 0:
        s = int(df_bt.at[i, "EntrySignal"])
        if s != 0:
            _pos = s


def px_exit(i: int) -> float:
    if EXEC_EXIT == "close_signal" or i + 1 >= len(df_bt):
        return float(df_bt.at[i, "Close"])
    return float(df_bt.at[i + 1, "Open"])


def px_addon(i: int) -> float:
    if EXEC_ADDON == "close_signal" or i + 1 >= len(df_bt):
        return float(df_bt.at[i, "Close"])
    return float(df_bt.at[i + 1, "Open"])


def go_for_side(side: int) -> float:
    return GO_LONG if side == 1 else GO_SHORT


def check_margin_and_addon(equity_before_fee, pos, units_main, units_add):
    """Отладочная проверка: ГО и ограничение добора."""
    if not CHECKS:
        return
    if pos == 0:
        return

    go_side = go_for_side(pos)
    max_margin_total = equity_before_fee * EXPOSURE_FRACTION * MAX_LEVERAGE
    margin_used = (units_main + units_add) * go_side

    if margin_used > max_margin_total + 1e-6:
        raise RuntimeError(
            f"Margin exceeded: used={margin_used:.2f}, "
            f"limit={max_margin_total:.2f}, "
            f"units_main={units_main}, units_add={units_add}"
        )

    if units_add > units_main * ADDON_RATIO + 1e-6:
        raise RuntimeError(
            f"Add-on too big: units_add={units_add}, "
            f"units_main={units_main}, ratio={ADDON_RATIO}"
        )


# -------- Бэктест --------
equity = START_EQUITY
equity_curve, trades = [], []

pos = 0
in_trade = False

units_main = 0.0
units_add  = 0.0

entry_i_main = None
entry_px_main = None
entry_eq_main = None

entry_i_add = None
entry_px_add = None
entry_eq_add = None

fee_in_main = 0.0
fee_in_add  = 0.0

stop_px_main = None
stop_px_add  = None

prev_close = float(df_bt.at[0, "Close"])

pending    = None
addon_done = False
wait_addon = False

for i in range(len(df_bt)):
    op, hi, lo, cl = map(float, [
        df_bt.at[i, "Open"],
        df_bt.at[i, "High"],
        df_bt.at[i, "Low"],
        df_bt.at[i, "Close"]
    ])

    # 0) pending-вход (на следующем баре)
    if (not in_trade) and (pending is not None) and (i == pending["idx"] + 1):
        side, level = pending["side"], pending["level"]
        trig = (side == 1 and hi >= level) or (side == -1 and lo <= level)

        if trig:
            fill = max(level, op) if side == 1 else min(level, op)
            go_side = go_for_side(side)

            # общий лимит по ГО
            max_margin_total = equity * EXPOSURE_FRACTION * MAX_LEVERAGE

            # ЧАСТЬ лимита отдаём под основную ногу,
            # остальное оставляем под добор (ADDON_RATIO)
            margin_for_main = max_margin_total / (1.0 + ADDON_RATIO)

            max_qty_main_by_go = np.floor(margin_for_main / go_side)

            if max_qty_main_by_go >= 1:
                units_main = float(max_qty_main_by_go)

                # проверка ГО до списания комиссии
                check_margin_and_addon(
                    equity_before_fee=equity,
                    pos=side,
                    units_main=units_main,
                    units_add=0.0
                )

                fee_in_main = fee_cash(units_main)
                equity -= fee_in_main

                pos = side
                in_trade = True

                entry_i_main = i
                entry_px_main = float(fill)
                entry_eq_main = float(equity)

                # стоп основной ноги: 2% от equity после входа
                risk_main = STOP_RISK_PCT_MAIN * entry_eq_main
                stop_dist_main = risk_main / (units_main * MULTIPLIER)
                stop_px_main = (
                    entry_px_main - stop_dist_main
                    if pos == 1
                    else entry_px_main + stop_dist_main
                )

                addon_done = False
                wait_addon = True
                units_add = 0.0
                fee_in_add = 0.0
                stop_px_add = None

        pending = None

    # 1) Жёсткие стопы по main/add — раздельно
    if in_trade and (stop_px_main is not None or stop_px_add is not None):
        hit_main = False
        hit_add  = False
        stop_fill_main = None
        stop_fill_add  = None

        if pos == 1:
            if stop_px_main is not None and lo <= stop_px_main:
                hit_main = True
                stop_fill_main = min(stop_px_main, op)
            if stop_px_add is not None and lo <= stop_px_add:
                hit_add = True
                stop_fill_add = min(stop_px_add, op)
        else:
            if stop_px_main is not None and hi >= stop_px_main:
                hit_main = True
                stop_fill_main = max(stop_px_main, op)
            if stop_px_add is not None and hi >= stop_px_add:
                hit_add = True
                stop_fill_add = max(stop_px_add, op)

        if hit_main or hit_add:
            fills = [f for f in [stop_fill_main, stop_fill_add] if f is not None]
            stop_fill_global = (
                fills[0]
                if len(fills) == 1
                else (max(fills) if pos == 1 else min(fills))
            )

            total_units_before = units_main + units_add
            equity += (stop_fill_global - prev_close) * total_units_before * pos * MULTIPLIER
            prev_close = stop_fill_global

            # закрываем main
            if hit_main and units_main > 0 and entry_i_main is not None:
                fee_out_main = fee_cash(units_main)
                equity -= fee_out_main

                trades.append({
                    "leg": "main",
                    "side": "LONG" if pos == 1 else "SHORT",
                    "entry_time": df_bt.at[entry_i_main, "DateTime"],
                    "exit_time":  df_bt.at[i, "DateTime"],
                    "entry_price": float(entry_px_main),
                    "exit_price":  float(stop_fill_main),
                    "units_main": float(units_main),
                    "units_add":  0.0,
                    "reason": "hard_stop_main",
                    "fee_in_main": float(fee_in_main),
                    "fee_in_add":  0.0,
                    "fee_out": float(fee_out_main),
                })

                units_main   = 0.0
                fee_in_main  = 0.0
                stop_px_main = None
                entry_i_main = None
                entry_px_main = None
                entry_eq_main = None

            # закрываем add
            if hit_add and units_add > 0 and entry_i_add is not None:
                fee_out_add = fee_cash(units_add)
                equity -= fee_out_add

                trades.append({
                    "leg": "add",
                    "side": "LONG" if pos == 1 else "SHORT",
                    "entry_time": df_bt.at[entry_i_add, "DateTime"],
                    "exit_time":  df_bt.at[i, "DateTime"],
                    "entry_price": float(entry_px_add),
                    "exit_price":  float(stop_fill_add),
                    "units_main": 0.0,
                    "units_add":  float(units_add),
                    "reason": "hard_stop_add",
                    "fee_in_main": 0.0,
                    "fee_in_add":  float(fee_in_add),
                    "fee_out": float(fee_out_add),
                })

                units_add   = 0.0
                fee_in_add  = 0.0
                stop_px_add = None
                entry_i_add = None
                entry_px_add = None
                entry_eq_add = None

            if units_main == 0 and units_add == 0:
                pos = 0
                in_trade = False
                addon_done = False
                wait_addon = False

            equity_curve.append(equity)
            continue

    # 2) MTM (если стопы не сработали)
    if i > 0 and in_trade:
        total_units = units_main + units_add
        equity += (cl - prev_close) * total_units * pos * MULTIPLIER
    prev_close = cl

    # 3) Плановый выход по flip — закрываем оставшиеся ноги
    ex = int(df_bt.at[i, "ExitSignal"])
    if in_trade and ((pos == 1 and ex == 1) or (pos == -1 and ex == -1)):
        exit_price = px_exit(i)
        total_units = units_main + units_add

        equity += (exit_price - prev_close) * total_units * pos * MULTIPLIER
        prev_close = exit_price

        fee_out_main = fee_cash(units_main) if units_main > 0 else 0.0
        fee_out_add  = fee_cash(units_add)  if units_add  > 0 else 0.0
        equity -= (fee_out_main + fee_out_add)

        if units_main > 0 and entry_i_main is not None:
            trades.append({
                "leg": "main_flip",
                "side": "LONG" if pos == 1 else "SHORT",
                "entry_time": df_bt.at[entry_i_main, "DateTime"],
                "exit_time":  df_bt.at[i, "DateTime"],
                "entry_price": float(entry_px_main),
                "exit_price":  float(exit_price),
                "units_main": float(units_main),
                "units_add":  0.0,
                "reason": "flip_exit_main",
                "fee_in_main": float(fee_in_main),
                "fee_in_add":  0.0,
                "fee_out": float(fee_out_main),
            })

        if units_add > 0 and entry_i_add is not None:
            trades.append({
                "leg": "add_flip",
                "side": "LONG" if pos == 1 else "SHORT",
                "entry_time": df_bt.at[entry_i_add, "DateTime"],
                "exit_time":  df_bt.at[i, "DateTime"],
                "entry_price": float(entry_px_add),
                "exit_price":  float(exit_price),
                "units_main": 0.0,
                "units_add":  float(units_add),
                "reason": "flip_exit_add",
                "fee_in_main": 0.0,
                "fee_in_add":  float(fee_in_add),
                "fee_out": float(fee_out_add),
            })

        pos = 0
        in_trade = False
        units_main = units_add = 0.0
        entry_i_main = entry_px_main = entry_eq_main = None
        entry_i_add  = entry_px_add  = entry_eq_add  = None
        fee_in_main = fee_in_add = 0.0
        stop_px_main = stop_px_add = None
        addon_done = False
        wait_addon = False

        equity_curve.append(equity)
        continue

    # 4) Добор на первом подтверждённом фрактале (с учётом ГО и минимального хода)
    if in_trade and wait_addon and (not addon_done):
        upc = int(df_bt.at[i, "Fractal_Up_conf"])
        dnc = int(df_bt.at[i, "Fractal_Down_conf"])
        trig_add = (pos == 1 and upc == 1) or (pos == -1 and dnc == 1)

        if trig_add:
            fill_add = px_addon(i)

            # --- Вариант 1: минимальное движение в нашу сторону ---
            if entry_px_main is not None and MIN_MOVE_FOR_ADD_PCT > 0.0:
                move_pct = (fill_add / entry_px_main - 1.0) * (1 if pos == 1 else -1)
                if move_pct < MIN_MOVE_FOR_ADD_PCT:
                    addon_done = True
                    wait_addon = False
                    equity_curve.append(equity)
                    continue

            # максимум по соотношению (например, 50% от основной)
            qty_by_ratio = np.floor(units_main * ADDON_RATIO)

            # лимит по ГО на текущем equity
            go_side = go_for_side(pos)
            max_margin_total = equity * EXPOSURE_FRACTION * MAX_LEVERAGE
            margin_used_main = units_main * go_side
            margin_remaining = max(max_margin_total - margin_used_main, 0.0)
            qty_by_margin = np.floor(margin_remaining / go_side)

            qty_candidate = min(qty_by_ratio, qty_by_margin)

            if qty_candidate >= 1:
                units_add_candidate = float(qty_candidate)

                # проверка ГО/ratio до списания комиссии
                check_margin_and_addon(
                    equity_before_fee=equity,
                    pos=pos,
                    units_main=units_main,
                    units_add=units_add_candidate
                )

                units_add = units_add_candidate
                fee_in_add = fee_cash(units_add)
                equity -= fee_in_add

                entry_i_add = i
                entry_px_add = float(fill_add)
                entry_eq_add = float(equity)

                risk_add = STOP_RISK_PCT_ADD * entry_eq_add
                stop_dist_add = risk_add / (units_add * MULTIPLIER)
                stop_px_add = (
                    entry_px_add - stop_dist_add
                    if pos == 1
                    else entry_px_add + stop_dist_add
                )

                # --- Вариант 2: подтягиваем стоп основной ноги после добора ---
                if (
                    TIGHTEN_MAIN_STOP_AFTER_ADD
                    and stop_px_main is not None
                    and entry_px_main is not None
                    and units_main > 0
                    and 0.0 < STOP_MAIN_TIGHTEN_FACTOR_AFTER_ADD < 1.0
                ):
                    # исходная дистанция стопа основной ноги от входа
                    orig_dist_main = abs(entry_px_main - stop_px_main)
                    new_dist_main  = orig_dist_main * STOP_MAIN_TIGHTEN_FACTOR_AFTER_ADD

                    if pos == 1:
                        new_stop_main = entry_px_main - new_dist_main
                        # стоп только подтягиваем ближе (никогда дальше)
                        stop_px_main = max(stop_px_main, new_stop_main)
                    else:
                        new_stop_main = entry_px_main + new_dist_main
                        stop_px_main = min(stop_px_main, new_stop_main)

            addon_done = True
            wait_addon = False

    # 5) Новая pending-заявка на вход
    if (not in_trade) and (pending is None) and ex == 0:
        s = int(df_bt.at[i, "EntrySignal"])
        if s != 0 and i + 1 < len(df_bt):
            level = float(df_bt.at[i, "High"]) if s == 1 else float(df_bt.at[i, "Low"])
            pending = {"side": s, "level": level, "idx": i}

    equity_curve.append(equity)


# -------- Статистика --------
bt = df_bt[["DateTime"]].copy()
bt["Equity"] = equity_curve

def full_stats(bt, trades):
    out = {}
    out["start_equity"]    = START_EQUITY
    out["final_equity"]    = float(bt["Equity"].iloc[-1])
    out["total_return_%"]  = (out["final_equity"]/out["start_equity"] - 1)*100.0

    out["start_date"]      = bt["DateTime"].iloc[0]
    out["end_date"]        = bt["DateTime"].iloc[-1]
    years = max((out["end_date"] - out["start_date"]).days/365.25, 1e-9)
    out["CAGR_%"]          = ((out["final_equity"]/out["start_equity"])**(1/years) - 1)*100.0

    roll = bt["Equity"].cummax()
    dd = bt["Equity"]/roll - 1.0
    out["MaxDD_%"]         = float(dd.min()*100.0)

    out["NumTrades"]       = len(trades)

    if trades:
        tr = pd.DataFrame(trades)
        qty = tr["units_main"].abs() + tr["units_add"].abs()

        tr["ret_rub"] = (tr["exit_price"] - tr["entry_price"]) * qty * MULTIPLIER

        tr["ret_trade_%"] = np.where(
            tr["side"]=="LONG",
            (tr["exit_price"]/tr["entry_price"] - 1.0)*100.0,
            (tr["entry_price"]/tr["exit_price"] - 1.0)*100.0
        )

        tr["dur_days"] = (
            pd.to_datetime(tr["exit_time"]) -
            pd.to_datetime(tr["entry_time"])
        ).dt.days

        out["WinRate_%"]        = float((tr["ret_trade_%"]>0).mean()*100.0)
        out["AvgTradeRet_%"]    = float(tr["ret_trade_%"].mean())
        out["MedianTradeRet_%"] = float(tr["ret_trade_%"].median())
        out["AvgDur_days"]      = float(tr["dur_days"].mean())

        gp = tr.loc[tr["ret_rub"]>0,  "ret_rub"].sum()
        gl = -tr.loc[tr["ret_rub"]<=0, "ret_rub"].sum()
        out["ProfitFactor"] = float(gp/gl) if gl>0 else np.nan
    else:
        out.update({
            "WinRate_%":        np.nan,
            "AvgTradeRet_%":    np.nan,
            "MedianTradeRet_%": np.nan,
            "AvgDur_days":      np.nan,
            "ProfitFactor":     np.nan,
        })

    return out

stats = full_stats(bt, trades)

print("=== BR-12.25 | FULL-PERIOD STATS (move-filter + tightened main stop after add) ===")
print(f"start_equity      : {stats['start_equity']:.2f}")
print(f"final_equity      : {stats['final_equity']:.2f}")
print(f"total_return_%    : {stats['total_return_%']:.2f}")
print(f"CAGR_%            : {stats['CAGR_%']:.2f}")
print(f"MaxDD_%           : {stats['MaxDD_%']:.2f}")
print(f"NumTrades         : {stats['NumTrades']}")

print(f"WinRate_%         : {stats.get('WinRate_%', np.nan):.2f}")
print(f"AvgTradeRet_%     : {stats.get('AvgTradeRet_%', np.nan):.4f}")
print(f"MedianTradeRet_%  : {stats.get('MedianTradeRet_%', np.nan):.4f}")
print(f"AvgDur_days       : {stats.get('AvgDur_days', np.nan):.2f}")
print(f"ProfitFactor      : {stats.get('ProfitFactor', np.nan):.3f}")

