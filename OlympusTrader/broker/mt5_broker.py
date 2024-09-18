
import os

import MetaTrader5 as mt5


from .base_broker import BaseBroker
from .interfaces import ISupportedBrokers


class Mt5Broker(BaseBroker):
    def __init__(self, paper: bool, feed = None):
        super().__init__(ISupportedBrokers.MT5, paper, feed)
        assert os.getenv('MT5_LOGIN') , 'MT5_LOGIN not set'
        assert os.getenv('MT5_SECRET_KEY'), 'MT5_SECRET_KEY not set'
        assert os.getenv('MT5_SERVER'), 'MT5_SERVER not set'



        if not mt5.initialize(login=os.getenv('MT5_LOGIN'), server= os.getenv('MT5_SERVER'), password=os.getenv('MT5_SECRET_KEY') ):
            print("initialize() failed, error code =",mt5.last_error())
            quit()
            
        raise NotImplementedError('MetaTrader5Broker not implemented yet')

    def __del__(self):
        # Shut down connection to the MetaTrader 5
        mt5.shutdown()