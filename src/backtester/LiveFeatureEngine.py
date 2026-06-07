import numpy as np
import pandas as pd


class LiveFeatureEngine:

    def __init__(self):

        # ===== состояние стратегии =====
        self.state = "flat"

        self.in_pos = 0
        self.anchor_set = False
        self.addon_done = False

        # ===== история для лагов =====
        self.prev_ao = None
        self.prev_ao2 = None

        self.prev_bullish = False
        self.prev_bearish = False

        self.prev_ao_sign = None
        self.prev_ao_sign2 = None

        self.prev_fractal_up = 0
        self.prev_fractal_up2 = 0

        self.prev_fractal_down = 0
        self.prev_fractal_down2 = 0

    # =====================================
    # основной метод — вызывается на каждый новый бар
    # =====================================

    def on_new_bar(self, row: pd.Series) -> dict:

        result = {}

        # ========= Фракталы =========
        fractal_up = int(pd.notna(row["Fractal_Up"]))
        fractal_down = int(pd.notna(row["Fractal_Down"]))

        fractal_up_conf = self.prev_fractal_up2
        fractal_down_conf = self.prev_fractal_down2

        # ========= AO =========
        ao = row["AO"]

        if self.prev_ao is None:
            color_ao = 0
        else:
            diff = ao - self.prev_ao
            color_ao = 1 if diff > 0 else (-1 if diff < 0 else 0)

        ao_sign = 1 if color_ao > 0 else -1

        ao_zero_up = int(self.prev_ao is not None and ao > 0 and self.prev_ao <= 0)
        ao_zero_down = int(self.prev_ao is not None and ao < 0 and self.prev_ao >= 0)

        ao_three_green = int(
            ao_sign == 1 and
            self.prev_ao_sign == 1 and
            self.prev_ao_sign2 == 1
        )

        ao_three_red = int(
            ao_sign == -1 and
            self.prev_ao_sign == -1 and
            self.prev_ao_sign2 == -1
        )

        ao_saucer_up = int(
            ao > 0 and
            self.prev_ao2 is not None and
            self.prev_ao2 > self.prev_ao and
            ao > self.prev_ao
        )

        ao_saucer_down = int(
            ao < 0 and
            self.prev_ao2 is not None and
            self.prev_ao2 < self.prev_ao and
            ao < self.prev_ao
        )

        # ========= Аллигатор =========
        jaw = row["Alligator_Jaw"]
        teeth = row["Alligator_Teeth"]
        lips = row["Alligator_Lips"]

        bullish = (lips > teeth) and (teeth > jaw)
        bearish = (jaw > teeth) and (teeth > lips)

        start_long = bullish and not self.prev_bullish
        start_short = bearish and not self.prev_bearish

        # ========= ENTRY LOGIC =========
        entry_signal = 0
        entry_reason = 0

        if self.state in ("flat", "in_long", "in_short"):
            if start_long:
                self.state = "wait_long"
            elif start_short:
                self.state = "wait_short"

        if self.state == "wait_long":
            if ao_zero_up:
                entry_signal = 1; entry_reason = 1; self.state = "in_long"
            elif ao_three_green:
                entry_signal = 1; entry_reason = 2; self.state = "in_long"
            elif ao_saucer_up:
                entry_signal = 1; entry_reason = 3; self.state = "in_long"

        elif self.state == "wait_short":
            if ao_zero_down:
                entry_signal = -1; entry_reason = 1; self.state = "in_short"
            elif ao_three_red:
                entry_signal = -1; entry_reason = 2; self.state = "in_short"
            elif ao_saucer_down:
                entry_signal = -1; entry_reason = 3; self.state = "in_short"

        # ========= обновляем память =========

        self.prev_ao2 = self.prev_ao
        self.prev_ao = ao

        self.prev_ao_sign2 = self.prev_ao_sign
        self.prev_ao_sign = ao_sign

        self.prev_bullish = bullish
        self.prev_bearish = bearish

        self.prev_fractal_up2 = self.prev_fractal_up
        self.prev_fractal_up = fractal_up

        self.prev_fractal_down2 = self.prev_fractal_down
        self.prev_fractal_down = fractal_down

        # ========= возвращаем признаки =========
        result["EntrySignal"] = entry_signal
        result["EntryReason"] = entry_reason
        result["Fractal_Up_conf"] = fractal_up_conf
        result["Fractal_Down_conf"] = fractal_down_conf

        return result