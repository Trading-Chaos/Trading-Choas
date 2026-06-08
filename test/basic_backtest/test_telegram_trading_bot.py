from pathlib import Path

from output.telegram_trading_bot import (
    TradingBotConfig,
    TelegramTradingBot,
    build_pipeline_command,
    build_pipeline_env,
)


def test_trading_bot_rejects_unknown_chat_for_trading_commands(tmp_path):
    bot = TelegramTradingBot(
        token="token",
        allowed_chat_id="42",
        config_path=tmp_path / "config.local.json",
    )

    answer = bot.handle_message(41, "/status")

    assert "не разрешен" in answer


def test_trading_bot_saves_account_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "output.telegram_trading_bot.check_mt5_connection",
        lambda config: "MT5 подключен.",
    )
    config_path = tmp_path / "config.local.json"
    bot = TelegramTradingBot(
        token="token",
        allowed_chat_id="42",
        config_path=config_path,
    )

    answer = bot.handle_message(42, "/connect 123456 Broker-Server password")
    config = TradingBotConfig.load(config_path)

    assert "Данные счета сохранены" in answer
    assert config.login == 123456
    assert config.server == "Broker-Server"
    assert config.password == "password"


def test_pipeline_command_uses_basic_backtest_module():
    config = TradingBotConfig(symbol="BRENT", volume=2, risk_pct=0.01, poll_seconds=30)

    command = build_pipeline_command("python", config, dry_run=True)

    assert command[:3] == ["python", "-m", "basic_backtest.live_brent_h1_pipeline"]
    assert "--dry-run" in command
    assert "--symbol" in command
    assert "BRENT" in command


def test_pipeline_env_passes_mt5_account_without_cli_password(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "existing")
    config = TradingBotConfig(
        login=123456,
        password="secret",
        server="Broker-Server",
        terminal_path=str(Path("C:/MetaTrader 5/terminal64.exe")),
    )

    env = build_pipeline_env(config, chat_id=42)

    assert env["MT5_LOGIN"] == "123456"
    assert env["MT5_PASSWORD"] == "secret"
    assert env["MT5_SERVER"] == "Broker-Server"
    assert env["TELEGRAM_CHAT_ID"] == "42"
