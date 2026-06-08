# Telegram-бот

В этой папке лежат Telegram-интеграции проекта.

- `telegram_bot.py` отправляет уведомления при каждой выставленной заявке или закрытии сделки.
- `telegram_trading_bot.py` принимает команды из Telegram и управляет live-контуром `basic_backtest`.

## Уведомления о сделках

Нужные переменные окружения для отправки сообщений:

```bash
set TELEGRAM_BOT_TOKEN=123456:token
set TELEGRAM_CHAT_ID=123456789
```

Сообщение содержит:

- какой бектест сработал;
- какая заявка или сделка была отправлена;
- инструмент, направление, объем, цену и stop-loss;
- баланс и equity счета;
- причину входа.

## Управление торговлей из Telegram

Торговый бот запускается локально на Windows-машине, где установлен MetaTrader 5.

Сначала узнай свой `chat_id`:

```bash
set TELEGRAM_BOT_TOKEN=123456:token
set PYTHONPATH=src;.
python -m output.telegram_trading_bot
```

В Telegram отправь боту команду:

```text
/whoami
```

После этого останови процесс, задай разрешенный chat id и запусти бота снова:

```bash
set TELEGRAM_ALLOWED_CHAT_ID=123456789
set TELEGRAM_CHAT_ID=123456789
set PYTHONPATH=src;.
python -m output.telegram_trading_bot
```

Команды:

```text
/connect <login> <server> <password>
/set_path <путь к terminal64.exe>
/set_symbol BRENT
/set_volume 1
/set_risk 0.02
/set_poll 60
/test_mt5
/status
/start_basic_dry
/start_basic_live
/stop_basic
/clear_account
```

Для реальных заявок нужна дополнительная защита:

```bash
set TELEGRAM_ALLOW_LIVE_TRADING=1
```

Без этой переменной команда `/start_basic_live` не запустит реальные заявки. Команда `/start_basic_dry` работает без реальных сделок и нужна для первой проверки.

Данные счета сохраняются локально в `output/telegram_trading_config.local.json`. Этот файл добавлен в `.gitignore`; не отправляй его в репозиторий.
