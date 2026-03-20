import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
else:
    print("MT5 connected")

account = mt5.account_info()
print("Account:", account.login if account else "No account")

mt5.shutdown()


print(mt5.__version__)
print(mt5.initialize())
print(mt5.version())
mt5.shutdown()