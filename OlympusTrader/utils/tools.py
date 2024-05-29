import numpy
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..strategy.base_strategy import BaseStrategy
# from OlympusTrader.strategy.base_strategy import BaseStrategy
class TradingTools():
    STRATEGY = None
    def __init__(self, strategy):
        self.STRATEGY = strategy
        

    def dynamic_round(self, v: float, symbol: str) -> float:
        """Round float depending on log10 decimal places"""
        if "price_base" not in self.STRATEGY.assets[symbol] or self.STRATEGY.assets[symbol]["price_base"] == None:
            dynamic_precision = numpy.abs(int(numpy.log10(self.STRATEGY.assets[symbol]["min_price_increment"])))
            self.STRATEGY.UNIVERSE[symbol]["price_base"]= dynamic_precision+2
            
        return round(v, self.STRATEGY.UNIVERSE[symbol]["price_base"])
            



def dynamic_round(self, v: float) -> float:
        """Round float depending on log10 decimal places"""
        dynamic_precision = numpy.abs(int(numpy.log10(v)))+2
        return round(v, dynamic_precision)

if __name__ == '__main__':
    # tools = TradingTools()
    print(dynamic_round(0.0045456171111)) # 0.0045456171111
    print(dynamic_round(0.000045456171111)) # 0.0045456171111
    print(dynamic_round(18.82666666)) # 18.83
    print(dynamic_round(12.2222222)) # 12.22
    print(dynamic_round(122222222)) # 12.22
    print(dynamic_round(0.291)) # 0.25
    print(dynamic_round(0.000000001)) # 0.0