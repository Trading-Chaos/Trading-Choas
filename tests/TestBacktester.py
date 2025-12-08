
# ==== 0) Проверки колонок ====
need_cols = {"DateTime","Open","High","Low","Close",
             "Alligator_Jaw","Alligator_Teeth","Alligator_Lips","AO"}
miss = need_cols - set(df_bt.columns)
if miss:
    raise ValueError(f"В df_bt отсутствуют колонки: {sorted(miss)}")

# ==== 1) Пересчитываем «чистый» сигнал на баре ====
d = df_bt.copy().reset_index(drop=True)
d["DateTime"] = pd.to_datetime(d["DateTime"])

bull = (d["Alligator_Lips"] > d["Alligator_Teeth"]) & (d["Alligator_Teeth"] > d["Alligator_Jaw"])
bear = (d["Alligator_Jaw"]  > d["Alligator_Teeth"]) & (d["Alligator_Teeth"] > d["Alligator_Lips"])

# AO "цвет": +1 (зелёный), -1 (красный) — именно как ты задавал
d["AO_sign"] = np.where(d["AO"] > 0, 1, -1).astype(int)

# три подряд по цвету
three_green = (d["AO_sign"]==1) & (d["AO_sign"].shift(1)==1) & (d["AO_sign"].shift(2)==1)
three_red   = (d["AO_sign"]==-1) & (d["AO_sign"].shift(1)==-1) & (d["AO_sign"].shift(2)==-1)

# блюдце (упрощённая классика: в своей стороне нуля и ускорение)
saucer_up   = (d["AO"]>0)  & (d["AO"].shift(2) > d["AO"].shift(1)) & (d["AO"] > d["AO"].shift(1))
saucer_down = (d["AO"]<0)  & (d["AO"].shift(2) < d["AO"].shift(1)) & (d["AO"] < d["AO"].shift(1))

# пересечение нуля
zero_up   = (d["AO"]>0)  & (d["AO"].shift(1)<=0)
zero_down = (d["AO"]<0)  & (d["AO"].shift(1)>=0)

ao_long_ok  = three_green | saucer_up  | zero_up
ao_short_ok = three_red   | saucer_down| zero_down

d["rule_signal"] = np.where(bull & ao_long_ok, 1,
                     np.where(bear & ao_short_ok, -1, 0)).astype(int)

# ==== 2) Breakout-вход: если есть сигнал, на следующем баре входим по пробою High/Low ====
# уровень для стоп-входа
level_long  = d["High"]
level_short = d["Low"]

next_high = d["High"].shift(-1)
next_low  = d["Low"].shift(-1)

trigger_long  = (d["rule_signal"]==1)  & (next_high >= level_long)
trigger_short = (d["rule_signal"]==-1) & (next_low  <= level_short)
trigger_any   = (trigger_long | trigger_short)

# индексы баров СИГНАЛА…
enter_signal_idx = np.where(trigger_any)[0]
# …а это индексы баров ИСПОЛНЕНИЯ (следующий бар)
enter_rule_exec_idx = set(int(i+1) for i in enter_signal_idx if i+1 < len(d))

# ==== 3) Фактические входы из твоего бэктеста (по времени входа) ====
if not isinstance(trades, (list, tuple)) or len(trades)==0:
    raise ValueError("Список trades пуст или не задан — запусти сначала свой бэктест, чтобы он его создал.")

trades_df = pd.DataFrame(trades).copy()
for col in ["entry_time","exit_time","entry_price","exit_price","side"]:
    if col not in trades_df.columns:
        raise ValueError(f"В trades отсутствует колонка '{col}'. Проверь формат trades.")

trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
dt2idx = pd.Series(range(len(d)), index=d["DateTime"].values)  # map DateTime -> index

fact_idx = []
for t in trades_df["entry_time"]:
    if t in dt2idx.index:
        fact_idx.append(int(dt2idx.loc[t]))
fact_idx = set(fact_idx)

# ==== 4) Метрики сопоставления ====
hits_same       = fact_idx & enter_rule_exec_idx
missed_by_model = enter_rule_exec_idx - fact_idx   # наш rule дал вход, а в бэктесте его нет
missed_by_bt    = fact_idx - enter_rule_exec_idx   # в бэктесте есть вход, а rule его не дал

precision = len(hits_same) / max(len(enter_rule_exec_idx), 1)
recall    = len(hits_same) / max(len(fact_idx), 1)

# среднее |смещение|, если вход «рядом», но не ровно на тот же бар (до 3 баров)
def mean_abs_shift(facts:set, rules:set, win=3):
    if not facts or not rules:
        return np.nan
    shifts = []
    rules_sorted = sorted(list(rules))
    for fi in facts:
        nearest = min((abs(fi-ri) for ri in rules_sorted), default=None)
        if nearest is not None and nearest <= win:
            shifts.append(nearest)
    return np.mean(shifts) if shifts else np.nan

avg_abs_shift = mean_abs_shift(fact_idx, enter_rule_exec_idx, win=3)

print("=== Сравнение сигналов (rule Аллигатор+АО → breakout на след. баре) с реальными входами trades ===")
print(f"Всего фактических входов (trades):            {len(fact_idx)}")
print(f"Rule-входов (exec на след. баре):             {len(enter_rule_exec_idx)}")
print(f"Совпало один-в-один (по индексу бара):        {len(hits_same)}")
print(f"Precision (качество rule-входов):             {precision:.3f}")
print(f"Recall    (покрытие входов бэктеста):         {recall:.3f}")
print(f"Среднее |смещение| (если рядом, ≤3 бара):     {avg_abs_shift:.2f} бара")

# ==== 5) Примеры несовпадений (для ручной проверки на графике) ====
def idx_to_dt(idx_set, top=10):
    idx_sorted = sorted(list(idx_set))[:top]
    cols = ["DateTime","Open","High","Low","Close","rule_signal"]
    return d.loc[idx_sorted, cols]

print("\n— Модель дала вход, а бэктест нет (первые 10):")
display(idx_to_dt(missed_by_model, 10))

print("\n— Бэктест дал вход, а модель нет (первые 10):")
display(idx_to_dt(missed_by_bt, 10))
