# Запись Brent H1 из MetaTrader 5

Код записи новых свечей теперь находится в папке `input`.

Recorder подключается к локальному терминалу MetaTrader 5 и пишет закрытые H1-свечи Brent в `input/data/BRENT_H1.csv`.

Запуск на Windows с установленным MetaTrader 5:

```bash
pip install -r requirements.txt
set PYTHONPATH=src;.
python -m input.record_brent_h1
```

Если у брокера Brent называется иначе, переопредели только символ MT5. Файл все равно останется `input/data/BRENT_H1.csv`:

```bash
python -m input.record_brent_h1 --symbol BRN
python -m input.record_brent_h1 --symbol XBRUSD
```

Параметры подключения можно передать аргументами или переменными окружения:

```bash
set MT5_LOGIN=123456
set MT5_PASSWORD=your_password
set MT5_SERVER=Broker-Server
set MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

Полный обычный live-контур без ML:

```bash
set PYTHONPATH=src;.
python -m basic_backtest.live_brent_h1_pipeline --symbol BRENT --volume 1
```

Он делает три шага:

1. добавляет новые закрытые H1-свечи в `input/data/BRENT_H1.csv`;
2. прогоняет датасет через `input/Cleaner.py` и пишет `input/clean_df/BRENT_H1_clean.csv`;
3. при сигнале выставляет заявку в MT5 и отправляет уведомление через `output/telegram_bot.py`.
