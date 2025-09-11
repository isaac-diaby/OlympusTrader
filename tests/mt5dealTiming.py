import MetaTrader5 as mt5
import os
from datetime import datetime, timezone
from time import sleep
from dotenv import load_dotenv


if __name__ == '__main__':
    if not mt5.initialize():
                raise BaseException("initialize() failed, error code =", mt5.last_error())
    load_dotenv()

    assert os.getenv("MT5_LOGIN"), "MT5_LOGIN not set"
    assert os.getenv("MT5_SECRET_KEY"), "MT5_SECRET_KEY not set"
    assert os.getenv("MT5_SERVER"), "MT5_SERVER not set"

    auth = mt5.login(
        login=int(os.getenv("MT5_LOGIN")),
        password=os.getenv("MT5_SECRET_KEY"),
        server=os.getenv("MT5_SERVER"),
    )
    if not auth:
        raise BaseException("Failed to login to MetaTrader 5", mt5.last_error())
    terminal_info = mt5.terminal_info()
    if terminal_info.tradeapi_disabled:
        raise BaseException(
            "Please enable trades from API in MetaTrader 5", mt5.last_error()
        )
    

    lastChecked = datetime.now().replace(tzinfo=timezone.utc) # UTC TIMEZONE 
    while True:
        try:
            sleep(1 / 1)
            now = datetime.now().replace(tzinfo=timezone.utc)  # UTC TIMEZONE 
            print(f"Checking for new trades from {lastChecked} to {now}")
            new_incoming_orders = mt5.history_orders_get(lastChecked, now)
            if (new_incoming_orders == None):
                print("No history orders error code={}".format(mt5.last_error()))

            new_incoming_deals = mt5.history_deals_get(lastChecked, now)
            if (new_incoming_deals == None):
                print("No history deal error code={}".format(mt5.last_error()))

            # TODO:Check if they are sorted!

            print("Oders", new_incoming_orders)
            print("Deal", new_incoming_deals)
            if (new_incoming_orders and len(new_incoming_orders) > 0) or (
                new_incoming_deals and len(new_incoming_deals) > 0
            ):
                for order in new_incoming_orders:
                    try:
                        print("New order:", order)
                    except Exception as e:
                        print(f"Error: {e}")

            lastChecked = now
        except Exception as e:
            print("Exception occurred:", e)
            break
    mt5.shutdown()