from ..base_executor import BaseExecutor
from ...insight import InsightState
from ....broker.interfaces import IOrderSide
from ....strategy.interfaces import IStrategyMode
from ....utils.tools import dynamic_round


class BasicTakeProfitExecutor(BaseExecutor):
    """
    ### Executor for Basic Take Profit
    This executor is used to take profit on insights that have reached the take profit price.

    :param strategy (BaseStrategy): The strategy instance
    
    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.FILLED, "1.0")

    def run(self, insight):
        # check if the insight already has a take profit order leg
        if insight.takeProfitOrderLeg: #  and self.STRATEGY.MODE != IStrategyMode.BACKTEST:
            return self.returnResults(True, True, "Insight already has a take profit order")

        # Check if the insight has reached the take profit price
        if insight.TP == None:
            return self.returnResults(True, True, "Insight does not have take profit level set.")
        try:
            # check if the insight has not already been closed 
            if insight._closing:
                return self.returnResults(False, True, "Insight is being closed.")
            # Check if price broke the first Take Profit level
            latestBar = self.get_latest_bar(insight.symbol)
            latestQuote = self.get_latest_quote(insight)
            shouldClose = False

            currentTP = insight.TP[0]
            match insight.side:
                case IOrderSide.BUY:
                    if (latestBar.high > currentTP) or (latestQuote["bid"] > currentTP):
                        shouldClose = True
                case IOrderSide.SELL:
                    if (latestBar.low < currentTP) or (latestQuote["ask"] < currentTP):
                        shouldClose = True
            if shouldClose:
                if len(insight.TP) > 1:
                    quantityToClose = dynamic_round(
                        insight.quantity/2)

                    if self.STRATEGY.insights[insight.INSIGHT_ID].close(quantity=quantityToClose):
                        return self.returnResults(False, True, f"Price broke the take profit level: {insight.symbol} : {currentTP}. Closing half position.")
                else:
                    # Close the position if the last TP level is reached
                    if self.STRATEGY.insights[insight.INSIGHT_ID].close():
                        return self.returnResults(False, True, f"Price broke the take profit level: {insight.symbol} : {currentTP}. Closing position.")
            return self.returnResults(True, True, f"Take profit price has not been reached yet: {insight.symbol} : {currentTP}")
        except Exception as e:
            return self.returnResults(False, False, f"Error taking profit: {e}")
