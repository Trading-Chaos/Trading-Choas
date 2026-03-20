import time
from datetime import datetime

import metarader5 as mt5

from .LiveBacktester import LiveBacktester
from .LiveFeatureEngine import LiveFeatureEngine
from .MT5Executor import MT5Executor


class LiveRunner:

    def __init__(
        self,
        cfg,
        calendar,
        start_symbol,
        lot_step=1.0,
        polling_seconds=1
    ):

        self.cfg = cfg
        self.calendar = calendar
        self.symbol = start_symbol
        self.polling_seconds = polling_seconds

        # стратегия
        self.strategy = LiveBacktester(cfg, calendar, start_symbol)

        # исполнитель
        self.executor = MT5Executor(symbol=start_symbol, lot_step=lot_step)

        # генератор фичей
        self.engine = LiveFeatureEngine()

        # контроль последнего бара
        self.last_bar_time = None

    # ======================================================
    # ПОДКЛЮЧЕНИЕ К MT5
    # ======================================================
    def connect(self):

        if not mt5.initialize():
            raise RuntimeError("MT5 initialize failed")

        print("MT5 connected")

    # ======================================================
    # ПОЛУЧЕНИЕ ТЕКУЩЕЙ ПОЗИЦИИ
    # ======================================================
    def get_current_position(self):

        positions = mt5.positions_get(symbol=self.symbol)

        if positions is None or len(positions) == 0:
            return None

        return positions[0]

    # ======================================================
    # ПОЛУЧЕНИЕ АКТУАЛЬНОГО ГО
    # ======================================================
    def get_margin_info(self):

        info = mt5.symbol_info(self.symbol)

        if info is None:
            raise RuntimeError("No symbol info")

        return info.margin_initial, info.margin_initial

    # ======================================================
    # ПОЛУЧЕНИЕ ПОСЛЕДНЕГО БАРА
    # ======================================================
    def get_last_bar(self):

        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_H1, 0, 2)

        if rates is None or len(rates) < 2:
            return None

        bar = rates[-1]

        return {
            "DateTime": datetime.fromtimestamp(bar["time"]),
            "Open": bar["open"],
            "High": bar["high"],
            "Low": bar["low"],
            "Close": bar["close"]
        }

    # ======================================================
    # ОСНОВНОЙ ЦИКЛ
    # ======================================================
    def run(self):

        self.connect()

        print("Live trading started...")

        while True:

            bar = self.get_last_bar()

            if bar is None:
                time.sleep(self.polling_seconds)
                continue

            # не обрабатываем один и тот же бар дважды
            if self.last_bar_time == bar["DateTime"]:
                time.sleep(self.polling_seconds)
                continue

            self.last_bar_time = bar["DateTime"]

            # обновляем фичи
            features = self.engine.on_new_bar(bar)

            bar.update(features)

            # синхронизация позиции
            mt5_position = self.get_current_position()
            self.strategy.sync_with_mt5(mt5_position)

            # equity
            account_info = mt5.account_info()
            equity = account_info.equity

            # ГО
            go_long, go_short = self.get_margin_info()

            # стратегия
            event = self.strategy.on_new_bar(
                bar,
                equity,
                go_long,
                go_short
            )

            # если нет действия — продолжаем
            if event["action"] is None:
                time.sleep(self.polling_seconds)
                continue

            # ==================================================
            # ОБРАБОТКА ROLL
            # ==================================================
            if event["action"] == "roll":

                print(f"ROLL {event['from_symbol']} -> {event['to_symbol']}")

                success = self.executor.roll_position(
                    from_symbol=event["from_symbol"],
                    to_symbol=event["to_symbol"],
                    side=event["side"],
                    volume=event["volume"]
                )

                if success:
                    # обновляем символ
                    self.symbol = event["to_symbol"]
                    self.strategy.current_symbol = event["to_symbol"]
                    self.executor.set_symbol(event["to_symbol"])

                time.sleep(self.polling_seconds)
                continue

            # ==================================================
            # ОБЫЧНОЕ ИСПОЛНЕНИЕ
            # ==================================================
            self.executor.process_event(event)

            time.sleep(self.polling_seconds) 