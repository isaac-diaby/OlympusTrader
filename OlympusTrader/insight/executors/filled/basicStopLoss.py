from ..base_executor import BaseExecutor
from ...insight import InsightState
from ....broker.interfaces import IOrderSide
from ....strategy.interfaces import IStrategyMode


class BasicStopLossExecutor(BaseExecutor):
    """ 
    ### Executor for Basic Stop Loss

    This executor is used to check if the insight has crossed the stop loss level. If the price crosses the stop loss level, the position is closed.
    Ideally this executor should be used in conjunction simple orders types with no OCO or bracket orders as the broker will close the position if the stop loss level is crossed.

    :param strategy (BaseStrategy): The strategy instance

    Note: You should have already set the stop loss price in the insight before using this executor.

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.FILLED, "1.0")

    def run(self, insight):
        #  Check if the insight already has a stop loss order leg
        if insight.stopLossOrderLeg:
            return self.returnResults(True, True, "Insight already has a stop loss order")
        # Check if the insight has a stop loss price
        if insight.SL == None:
            return self.returnResults(True, True, "Insight does not have a stop loss price set.")
        try:
            # check if the insight has not already been closed 
            if insight._closing:
                return self.returnResults(False, True, "Insight is being closed.")
            # Check if price broke the stop loss level
            latestBar = self.get_latest_bar(insight.symbol)
            latestQuote = self.get_latest_quote(insight)
            shouldClose = False
            match insight.side:
                case IOrderSide.BUY:
                    if (latestBar.low < insight.SL) or (latestQuote['bid'] < insight.SL):
                        shouldClose = True
                case IOrderSide.SELL:
                    if (latestBar.high > insight.SL) or (latestQuote['ask'] > insight.SL):
                        shouldClose = True
            if shouldClose:
                if self.STRATEGY.insights[insight.INSIGHT_ID].close():
                    return self.returnResults(False, True, f"Price broke the stop loss level: {insight.symbol} : {insight.SL}. Closing position.")
                return self.returnResults(False, False, f"Error closing position.")

            return self.returnResults(True, True, f"Stop loss price has not been reached: {insight.symbol} : {insight.SL}")
        except Exception as e:
            return self.returnResults(False, False, f"Error Checking Stop Loss: {e}")
