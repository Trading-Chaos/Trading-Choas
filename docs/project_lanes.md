# Структура проекта

Рабочие контуры разделены, чтобы простой live-путь не смешивался с ML и оптимизацией.

## 1. Обычный бектест

Папка: `src/basic_backtest`

Без ML. Текущий поток:

```text
MetaTrader 5 -> input/data/BRENT_H1.csv -> input/Cleaner.py -> input/clean_df/BRENT_H1_clean.csv -> базовый сигнал -> заявка MT5 -> Telegram
```

Запуск:

```bash
set PYTHONPATH=src;.
python -m basic_backtest.live_brent_h1_pipeline --symbol BRENT --volume 1
```

## 2. Бектест с ML-фильтром

Папка: `src/ml_backtest`

Здесь базовая стратегия будет дополнительно фильтроваться ML-моделью перед входом.

## 3. Бектест с ML-фильтром и оптимизацией

Папка: `src/opt_backtest`

Здесь будет ML-фильтр плюс подбор параметров и walk-forward оптимизация.
