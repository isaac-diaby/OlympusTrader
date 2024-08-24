from ..base_executor import BaseExecutor
from ...insight import InsightState
from ....broker.interfaces import IOrderType


class MarketOrderEntryPriceExecutor(BaseExecutor):
    """
    ### Executor for Market Order Entry Price
    This executor is used to set the entry price for market orders. The entry price is set to the current close price of the asset.
    Get price from latest bar if limit price is not set.

    :param strategy (BaseStrategy): The strategy instance

    Note: This is only applicable for insights that are set to market orders and have no limit price set. 
    If a limit is set, executor passes the insight to the next executor.

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.NEW, "1.0")

    def run(self, insight):
        if insight.type != IOrderType.MARKET:
            return self.returnResults(True, True, "Insight already has a limit price set. Passing to next executor.")
        try:
            # Set the limit price to the current close price
            latestBar = self.get_latest_bar(insight.symbol)
            self.STRATEGY.insights[insight.INSIGHT_ID].update_limit_price(
                latestBar.close)
            return self.returnResults(True, True, f"limit price set to current close price: {latestBar.close}")
        except Exception as e:
            return self.returnResults(False, False, f"Error setting limit price: {e}")
