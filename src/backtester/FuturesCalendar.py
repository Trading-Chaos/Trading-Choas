import pandas as pd


class FuturesCalendar:

    def __init__(self, roll_days=4):

        self.roll_days = roll_days

        # Список контрактов по порядку
        self.contracts = [
            ("BR-4.26", "2026-04-01"),
            ("BR-5.26", "2026-05-04"),
            ("BR-6.26", "2026-06-01"),
            ("BR-7.26", "2026-07-01"),
            ("BR-8.26", "2026-08-03"),
            ("BR-9.26", "2026-08-31"),
            ("BR-10.26", "2026-10-01"),
        ]

        self.contracts = [
            (sym, pd.Timestamp(date))
            for sym, date in self.contracts
        ]

    # ==========================================
    # Получить следующий контракт
    # ==========================================
    def get_next_contract(self, current_symbol):

        for i in range(len(self.contracts) - 1):
            if self.contracts[i][0] == current_symbol:
                return self.contracts[i + 1][0]

        return None

    # ==========================================
    # Проверка: пора ли перекладываться
    # ==========================================
    def is_roll_day(self, current_symbol, today):

        for symbol, expiry in self.contracts:
            if symbol == current_symbol:

                roll_date = expiry - pd.tseries.offsets.BDay(self.roll_days)

                return today >= roll_date

        return False