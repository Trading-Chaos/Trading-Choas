import MetaTrader5 as mt5


class MT5Executor:

    def __init__(self, symbol, lot_step=1.0, magic=777000):

        self.symbol = symbol
        self.lot_step = lot_step
        self.magic = magic

    # ======================================================
    # СМЕНА СИМВОЛА (ПОСЛЕ ROLL)
    # ======================================================
    def set_symbol(self, symbol):
        self.symbol = symbol

    # ======================================================
    # ОБРАБОТКА СОБЫТИЯ СТРАТЕГИИ
    # ======================================================
    def process_event(self, event):

        action = event["action"]

        if action is None:
            return

        if event.get("cancel_all_stops", False):
            self._cancel_all_stops()

        if action == "open_main":
            self._open_stop_entry(
                side=event["side"],
                volume=event["volume"],
                stop_price=event["stop_main"]
            )

        elif action == "open_add":
            self._open_stop_entry(
                side=event["side"],
                volume=event["volume"],
                stop_price=event["stop_add"]
            )

        elif action == "flip_close":
            self._close_position()

    # ======================================================
    # ROLL (ПЕРЕКЛАДКА)
    # ======================================================
    def roll_position(self, from_symbol, to_symbol, side, volume):

        print(f"Rolling {from_symbol} -> {to_symbol}")

        # закрываем текущую позицию
        if not self._close_position():
            return False

        # переключаем символ
        self.symbol = to_symbol

        # открываем новую позицию market-ордером
        order_type = mt5.ORDER_TYPE_BUY if side == 1 else mt5.ORDER_TYPE_SELL

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            print("No tick info for new contract")
            return False

        price = tick.ask if side == 1 else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": self.magic,
            "comment": "ROLL",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print("ROLL failed:", result)
            return False

        print("ROLL success")
        return True

    # ======================================================
    # STOP ENTRY (ВХОД ПО ПРОБОЮ)
    # ======================================================
    def _open_stop_entry(self, side, volume, stop_price):

        order_type = (
            mt5.ORDER_TYPE_BUY_STOP
            if side == 1
            else mt5.ORDER_TYPE_SELL_STOP
        )

        volume = self._normalize_volume(volume)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": stop_price,
            "deviation": 20,
            "magic": self.magic,
            "comment": "STOP ENTRY",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print("Stop entry failed:", result)
        else:
            print("Stop entry placed")

    # ======================================================
    # ЗАКРЫТИЕ ПОЗИЦИИ (NETTING)
    # ======================================================
    def _close_position(self):

        positions = mt5.positions_get(symbol=self.symbol)

        if positions is None or len(positions) == 0:
            return True

        pos = positions[0]

        side = 1 if pos.type == 0 else -1
        close_type = (
            mt5.ORDER_TYPE_SELL
            if side == 1
            else mt5.ORDER_TYPE_BUY
        )

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return False

        price = tick.bid if side == 1 else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "deviation": 20,
            "magic": self.magic,
            "comment": "CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print("Close failed:", result)
            return False

        print("Position closed")
        return True

    # ======================================================
    # ОТМЕНА ВСЕХ СТОПОВ
    # ======================================================
    def _cancel_all_stops(self):

        orders = mt5.orders_get(symbol=self.symbol)

        if orders is None:
            return

        for order in orders:

            if order.type in (
                mt5.ORDER_TYPE_BUY_STOP,
                mt5.ORDER_TYPE_SELL_STOP
            ):

                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": order.ticket
                }

                mt5.order_send(request)

        print("All stop orders cancelled")

    # ======================================================
    # НОРМАЛИЗАЦИЯ ОБЪЁМА
    # ======================================================
    def _normalize_volume(self, volume):

        return round(float(volume) / self.lot_step) * self.lot_step