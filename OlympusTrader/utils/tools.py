import numpy as np
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from OlympusTrader.strategy.base_strategy import BaseStrategy

from ..insight.insight import InsightState


class ITradingTools():
    STRATEGY = None

    def __init__(self, strategy):
        self.STRATEGY = strategy

    def dynamic_round(self, v: float, symbol: str) -> float:
        """Round float depending on log10 decimal places"""
        if "price_base" not in self.STRATEGY.assets[symbol] or self.STRATEGY.assets[symbol]["price_base"] == None:
            dynamic_precision = np.abs(
                int(np.log10(self.STRATEGY.assets[symbol]["min_price_increment"])))
            self.STRATEGY.UNIVERSE[symbol]["price_base"] = dynamic_precision

        return round(v, self.STRATEGY.UNIVERSE[symbol]["price_base"])
    # TODO: movethis into strategy tools
    def calculateTimeToLive(self, price: float, entry: float, ATR: float, additional: int = 2) -> int:
        """Calculate the time to live for a given price and entry based on the ATR"""
        return np.ceil((np.abs(price - entry)) / ATR)+additional
    
    def get_unrealized_pnl(self, symbol: str) -> float:
        """Calculate unrealized PnL for a given symbol"""
        if symbol not in self.STRATEGY.positions:
            return 0
        position = self.STRATEGY.positions[symbol]
        if position["side"] == "long":
            return (position["current_price"] - position["avg_entry_price"]) * position["qty"]
        else:
            return (position["avg_entry_price"] - position["current_price"]) * position["qty"]
    
    def get_all_unrealized_pnl(self) -> float:
        """Calculate unrealized PnL for a given symbol"""
        unrealized_pnl = 0
        for symbol in self.STRATEGY.positions:
            unrealized_pnl += self.get_unrealized_pnl(symbol)
        return unrealized_pnl
    
    def get_filled_insights(self) -> list:
        """Get all filled insights"""
        filled_insights = []
        for symbol in self.STRATEGY.insights:
           for insight in self.STRATEGY.insights[symbol]:
               if insight["status"] == InsightState.FILLED:
                   filled_insights.append(insight)
        return filled_insights

def dynamic_round(v: float) -> float:
    """Round float depending on log10 decimal places"""
    dynamic_precision = np.abs(int(np.log10(v)))+2
    return round(v, dynamic_precision)


if __name__ == '__main__':
    # tools = TradingTools()
    print(dynamic_round(0.0045456171111))  # 0.0045456171111
    print(dynamic_round(0.000045456171111))  # 0.0045456171111
    print(dynamic_round(18.82666666))  # 18.83
    print(dynamic_round(12.2222222))  # 12.22
    print(dynamic_round(122222222))  # 12.22
    print(dynamic_round(0.291))  # 0.25
    print(dynamic_round(0.000000001))  # 0.0
    print(dynamic_round(5505999.68))
