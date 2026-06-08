# Обычный бектест без ML

Эта папка отвечает за базовый контур без ML-фильтра.

Текущий live-поток:

```text
MetaTrader 5
-> input/data/BRENT_H1.csv
-> input/Cleaner.py
-> input/clean_df/BRENT_H1_clean.csv
-> базовый сигнал
-> заявка в MetaTrader 5
-> уведомление Telegram из output/telegram_bot.py
```

Запуск на Windows с установленным MetaTrader 5:

```bash
set PYTHONPATH=src;.
python -m basic_backtest.live_brent_h1_pipeline --symbol BRENT --volume 1
```

Проверка одного шага без реальной заявки:

```bash
python -m basic_backtest.live_brent_h1_pipeline --symbol BRENT --volume 1 --once --dry-run
```
