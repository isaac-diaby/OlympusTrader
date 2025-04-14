from ..base_executor import BaseExecutor
from ...insight import InsightState
from ....broker.interfaces import IOrderSide, IOrderType


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

    def __init__(self, strategy, **kwargs):
        super().__init__(strategy, InsightState.NEW, "1.0", **kwargs)

    def run(self, insight):
        if insight.type != IOrderType.MARKET or insight.limit_price:
            return self.returnResults(True, True, "Insight already has a limit price set. Passing to next executor.")
        try:
            # Set the limit price to the current close price
            latestBar = self.get_latest_bar(insight.symbol)
            latest_quote = self.get_latest_quote(insight)
            atPrice = latestBar.close

            match insight.side:
                case IOrderSide.BUY:
                    if (latest_quote is not None )  and latest_quote["ask"]:
                        atPrice = latest_quote["ask"]
                case IOrderSide.SELL:
                    if (latest_quote is not None ) and latest_quote["bid"]:
                        atPrice = latest_quote["bid"]

            insight.update_limit_price(atPrice or latestBar.close)
            return self.returnResults(True, True, f"limit price set to current close price: {atPrice}")
        except Exception as e:
            return self.returnResults(False, False, f"Error setting limit price: {e}")
