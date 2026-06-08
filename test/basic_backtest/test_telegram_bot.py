from output.telegram_bot import format_trade_message


def test_format_trade_message_contains_required_trading_context():
    message = format_trade_message(
        backtest_name="basic_backtest",
        event_type="заявка",
        symbol="BRENT",
        side=1,
        order_kind="LONG stop-entry",
        volume=1,
        price=82.15,
        stop_loss=80.5,
        balance=100000.0,
        equity=100250.0,
        reason="AO пересек нулевую линию",
        status="выставлена",
    )

    assert "Бектест: basic_backtest" in message
    assert "Событие: заявка" in message
    assert "Инструмент: BRENT" in message
    assert "Направление: LONG" in message
    assert "Баланс счета: 100 000.00" in message
    assert "Причина входа: AO пересек нулевую линию" in message
