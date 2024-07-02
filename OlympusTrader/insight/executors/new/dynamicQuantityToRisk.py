from ..base_executor import BaseExecutor
from ...insight import InsightState
import numpy as np


class DynamicQuantityToRiskExecutor(BaseExecutor):
    """
    ### Executor for Dynamic Quantity to Risk
    This executor uses risks a percentage of the account balance to determine the quantity to trade.

    Args:
        strategy (BaseStrategy): The strategy instance

    #### How it works:
    When a new insight is generated, the executor calculates the quantity to trade based on the percentage of the account balance which is a percentage of insight.confidence * RISK.

    Note: limit price and stop loss levels must be set in the insight before using this executor.

    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.NEW, "1.0")

    def run(self, insight):
        if insight.limit_price is None or insight.SL is None:
            return self.returnResults(False, False, "Insight does not have limit price or stop loss levels set.")

        # Calculate the quantity to trade
        try:
            # Account size at to place order
            # TODO: Add a Check if margin is enabled for this asset. If margin is enabled, then use buying_power to calculate the quantity.
            account_size_at_risk = self.STRATEGY.account['cash'] * (
                insight.confidence*self.STRATEGY.execution_risk)
            # Calculate the risk per share (PIP value)
            riskPerShare = abs(insight.limit_price - insight.SL)
        
            # Calculate the maximum quantity that can be bought
            maximun_can_buy = self.STRATEGY.account['cash']/insight.limit_price

            # Calculate the quantity to trade
            size_should_buy = account_size_at_risk/riskPerShare

            # Check if the quantity is greater than the maximum quantity that can be bought
            size_should_buy = min(size_should_buy, maximun_can_buy)

            # Check if the quantity is greater than the minimum order size
            if size_should_buy < self.STRATEGY.assets[insight.symbol]['min_order_size']:
                response = self.returnResults(False, True, f"Quantity is less than the minimum order size: {self.STRATEGY.assets[insight.symbol]['min_order_size']} : Suggested: {size_should_buy}")
                self.changeState(
                    insight, InsightState.REJECTED, response.message)
                return response

            # Round down the quantity to the nearest whole number
            if size_should_buy > 1:
                size_should_buy = np.floor(size_should_buy)

            else:
                # TODO: May want to later check if the quantity is too small due to funds available
                pass

            # Update the quantity in the insight
            self.STRATEGY.insights[insight.INSIGHT_ID].update_quantity(
                size_should_buy)

            return self.returnResults(True, True, f"Quantity set to {size_should_buy}")
        except Exception as e:
            return self.returnResults(False, False, f"Error calculating quantity: {e}")
