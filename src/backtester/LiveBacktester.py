import numpy as np

# ==========================================================
# CONTRACT CALENDAR
# ==========================================================

class ContractCalendar:

    def __init__(self, contracts, roll_shift_trading_days=4):
        self.contracts = sorted(contracts, key=lambda x: x["expiration"])
        self.roll_shift = roll_shift_trading_days
        self.trading_days = []

    def register_bar(self, dt):
        date = dt.date()
        if not self.trading_days or self.trading_days[-1] != date:
            self.trading_days.append(date)

    def is_roll_time(self, current_symbol):

        contract = next(
            (c for c in self.contracts if c["symbol"] == current_symbol),
            None
        )

        if not contract:
            return False

        exp_date = contract["expiration"].date()

        if exp_date not in self.trading_days:
            return False

        exp_index = self.trading_days.index(exp_date)
        roll_index = exp_index - self.roll_shift

        if roll_index < 0:
            return False

        roll_date = self.trading_days[roll_index]

        return self.trading_days[-1] >= roll_date

    def get_next_contract(self, current_symbol):
        for i, c in enumerate(self.contracts):
            if c["symbol"] == current_symbol:
                if i + 1 < len(self.contracts):
                    return self.contracts[i + 1]["symbol"]
        return None


# ==========================================================
# LIVE BACKTESTER (PRODUCTION VERSION)
# ==========================================================

class LiveBacktester:

    def __init__(self, cfg, calendar, start_symbol):

        self.cfg = cfg
        self.calendar = calendar
        self.current_symbol = start_symbol

        self._reset_position()

    # ======================================================
    # СИНХРОНИЗАЦИЯ С MT5
    # ======================================================
    def sync_with_mt5(self, mt5_position):

        if mt5_position is None:
            self._reset_position()
            return

        volume = mt5_position.volume
        direction = 1 if mt5_position.type == 0 else -1

        self.pos = direction
        self.in_trade = True

        total = self.units_main + self.units_add

        if volume < total:
            if volume <= self.units_main:
                self.units_add = 0
                self.stop_add = None
            else:
                self.units_add = volume - self.units_main

    # ======================================================
    # ОСНОВНАЯ ЛОГИКА
    # ======================================================
    def on_new_bar(self, bar, equity, go_long, go_short):

        # регистрируем торговый день
        self.calendar.register_bar(bar["DateTime"])

        op = float(bar["Open"])
        hi = float(bar["High"])
        lo = float(bar["Low"])

        entry_signal = int(bar.get("EntrySignal", 0))
        exit_signal = int(bar.get("ExitSignal", 0))
        fract_up = int(bar.get("Fractal_Up_conf", 0))
        fract_down = int(bar.get("Fractal_Down_conf", 0))

        event = self._empty_event()

        # ==================================================
        # ROLL (ПЕРЕКЛАДКА)
        # ==================================================
        if self.in_trade and self.calendar.is_roll_time(self.current_symbol):

            next_symbol = self.calendar.get_next_contract(self.current_symbol)

            if next_symbol is None:
                # Нет следующего контракта — ничего не делаем
                return event

            total_vol = self.units_main + self.units_add

            event.update({
                "action": "roll",
                "side": self.pos,
                "volume": total_vol,
                "from_symbol": self.current_symbol,
                "to_symbol": next_symbol,
                "cancel_all_stops": True
            })

            # ВАЖНО:
            # self.current_symbol НЕ меняем здесь.
            # Его обновит LiveRunner после успешного roll.

            return event

        # ==================================================
        # FLIP EXIT
        # ==================================================
        if self.in_trade:
            if (self.pos == 1 and exit_signal == 1) or \
               (self.pos == -1 and exit_signal == -1):

                event.update({
                    "action": "flip_close",
                    "cancel_all_stops": True
                })

                self._reset_position()
                return event

        # ==================================================
        # PENDING ENTRY
        # ==================================================
        if not self.in_trade and self.pending:

            side = self.pending["side"]
            level = self.pending["level"]

            trigger = (side == 1 and hi >= level) or \
                      (side == -1 and lo <= level)

            if trigger:

                fill = max(level, op) if side == 1 else min(level, op)

                qty, stop = self._calc_main(
                    side, fill, equity, go_long, go_short
                )

                if qty >= 1:

                    self._register_main(side, qty, fill, stop)

                    event.update({
                        "action": "open_main",
                        "side": side,
                        "volume": qty,
                        "stop_main": stop
                    })

            self.pending = None
            return event

        # ==================================================
        # ADD-ON
        # ==================================================
        if self.in_trade and self.wait_addon and not self.addon_done:

            trigger = (self.pos == 1 and fract_up == 1) or \
                      (self.pos == -1 and fract_down == 1)

            if trigger:

                fill = op

                if self.cfg.MIN_MOVE_FOR_ADD_PCT > 0:
                    move_pct = (fill / self.entry_px_main - 1) * \
                               (1 if self.pos == 1 else -1)

                    if move_pct < self.cfg.MIN_MOVE_FOR_ADD_PCT:
                        self.addon_done = True
                        self.wait_addon = False
                        return event

                qty, stop = self._calc_add(
                    fill, equity, go_long, go_short
                )

                if qty >= 1:

                    self.units_add = qty
                    self.entry_px_add = fill
                    self.stop_add = stop

                    if self.cfg.TIGHTEN_MAIN_STOP_AFTER_ADD:
                        self.stop_main = self._tighten_main()

                    self.addon_done = True
                    self.wait_addon = False

                    event.update({
                        "action": "open_add",
                        "side": self.pos,
                        "volume": qty,
                        "stop_main": self.stop_main,
                        "stop_add": stop
                    })

                    return event

        # ==================================================
        # NEW ENTRY SIGNAL
        # ==================================================
        if not self.in_trade and entry_signal != 0:
            level = hi if entry_signal == 1 else lo
            self.pending = {"side": entry_signal, "level": level}

        return event

    # ======================================================
    # РАСЧЕТ MAIN
    # ======================================================
    def _calc_main(self, side, price, equity, go_long, go_short):

        go = go_long if side == 1 else go_short

        max_margin_total = equity * self.cfg.EXPOSURE_FRACTION * self.cfg.MAX_LEVERAGE
        margin_for_main = max_margin_total / (1 + self.cfg.ADDON_RATIO)

        qty = np.floor(margin_for_main / go)
        qty = min(qty, self.cfg.MAX_QTY_MAIN)

        if qty < 1:
            return 0, None

        risk = self.cfg.STOP_RISK_PCT_MAIN * equity
        stop_dist = risk / (qty * self.cfg.MULTIPLIER)

        stop = price - stop_dist if side == 1 else price + stop_dist

        return float(qty), stop

    # ======================================================
    # РАСЧЕТ ADD
    # ======================================================
    def _calc_add(self, price, equity, go_long, go_short):

        go = go_long if self.pos == 1 else go_short

        qty_ratio = np.floor(self.units_main * self.cfg.ADDON_RATIO)

        max_margin_total = equity * self.cfg.EXPOSURE_FRACTION * self.cfg.MAX_LEVERAGE
        margin_used = self.units_main * go
        margin_remaining = max(max_margin_total - margin_used, 0)

        qty_margin = np.floor(margin_remaining / go)

        qty = min(qty_ratio, qty_margin, self.cfg.MAX_QTY_ADD)

        if qty < 1:
            return 0, None

        risk = self.cfg.STOP_RISK_PCT_ADD * equity
        stop_dist = risk / (qty * self.cfg.MULTIPLIER)

        stop = price - stop_dist if self.pos == 1 else price + stop_dist

        return float(qty), stop

    # ======================================================
    def _tighten_main(self):

        orig_dist = abs(self.entry_px_main - self.stop_main)
        new_dist = orig_dist * self.cfg.STOP_MAIN_TIGHTEN_FACTOR_AFTER_ADD

        if self.pos == 1:
            return self.entry_px_main - new_dist
        else:
            return self.entry_px_main + new_dist

    # ======================================================
    def _register_main(self, side, qty, price, stop):

        self.pos = side
        self.in_trade = True

        self.units_main = qty
        self.entry_px_main = price
        self.stop_main = stop

        self.wait_addon = True
        self.addon_done = False

    # ======================================================
    def _reset_position(self):

        self.pos = 0
        self.in_trade = False

        self.units_main = 0
        self.units_add = 0

        self.entry_px_main = None
        self.entry_px_add = None

        self.stop_main = None
        self.stop_add = None

        self.wait_addon = False
        self.addon_done = False

        self.pending = None

    # ======================================================
    def _empty_event(self):
        return {
            "action": None,
            "side": None,
            "volume": None,
            "stop_main": None,
            "stop_add": None,
            "cancel_all_stops": False,
            "from_symbol": None,
            "to_symbol": None
        }