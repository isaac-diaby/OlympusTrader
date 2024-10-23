from ..base_executor import BaseExecutor
from ...insight import InsightState
import numpy as np


class FullAccountQuantityToRiskExecutor(BaseExecutor):
    """
    ### Executor for Full Account Quantity to Risk
    This executor uses the full account cash balance to determine the quantity to trade.
    
    :param strategy (BaseStrategy): The strategy instance

    #### How it works:
    When a new insight is generated, the executor calculates the quantity to trade based on the account balance.

    Note: limit price ust be set in the insight before using this executor.

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.NEW, "1.0")

    def run(self, insight):
        if insight.limit_price is None or insight.SL is None:
            return self.returnResults(False, False, "Insight does not have limit price or stop loss levels set.")

        # Calculate the quantity to trade
        try:
            # Account size at to place order
            account_size_at_risk = self.STRATEGY.account.buying_power if self.STRATEGY.assets[insight.symbol]['marginable'] else self.STRATEGY.account.cash
            if self.STRATEGY.broker.supportedFeatures.maxOrderValue is not None:
                # Check if the account size at risk is greater than the maximum order value supported by the broker
                account_size_at_risk = min(self.STRATEGY.broker.supportedFeatures.maxOrderValue, account_size_at_risk)

            # Calculate the quantity to trade based on the limit price and account size cash balance
            size_should_buy = account_size_at_risk/insight.limit_price


            # Round down the quantity to the nearest whole number
            if size_should_buy > 1:
                size_should_buy = np.floor(size_should_buy)

            else:
                # Check if the quantity is greater than the minimum order size
                if size_should_buy < self.STRATEGY.assets[insight.symbol]['min_order_size']:
                    response = self.returnResults(False, False, f"Quantity is less than the minimum order size: {
                                                self.STRATEGY.assets[insight.symbol]['min_order_size']}")
                    self.changeState(
                        insight, InsightState.REJECTED, response.message)
                    return response
                pass

            # Update the quantity in the insight
            self.STRATEGY.insights[insight.INSIGHT_ID].update_quantity(
                size_should_buy)

            return self.returnResults(True, True, f"Quantity set to {size_should_buy}")
        except Exception as e:
            return self.returnResults(False, False, f"Error calculating quantity: {e}")
