import numpy as np
from ..base_executor import BaseExecutor
from ...insight import InsightState

from ....utils.tools import dynamic_round

class DynamicQuantityToRiskExecutor(BaseExecutor):
    """
    ### Executor for Dynamic Quantity to Risk
    This executor uses risks a percentage of the account balance to determine the quantity to trade.

    :param strategy (BaseStrategy): The strategy instance
    :param maximum_costbasis (float): The maximum cost basis for the trade. Default is 200,000.
    :param minimum_costbasis (float): The minimum cost basis for the trade. Default is 1,000.

    #### How it works:
    When a new insight is generated, the executor calculates the quantity to trade based on the percentage of the account balance which is a percentage of insight.confidence * RISK.

    Note: limit price and stop loss levels must be set in the insight before using this executor.

    Author:
        @isaac-diaby
    """
    maximum_costbasis: float
    minimum_costbasis: float
    def __init__(self, strategy, maximum_costbasis: float = 200_000.0, minimum_costbasis: float = 1_000.0):
        super().__init__(strategy, InsightState.NEW, "1.1")
        if self.STRATEGY.broker.supportedFeatures.maxOrderValue is not None:
            self.maximum_costbasis = min(self.STRATEGY.broker.supportedFeatures.maxOrderValue, maximum_costbasis)
        else:
            self.maximum_costbasis = maximum_costbasis
        self.minimum_costbasis = minimum_costbasis

        assert self.maximum_costbasis > self.minimum_costbasis, "Maximum cost basis must be greater than or equal to the minimum cost basis."

    def run(self, insight):
        if insight.limit_price is None or not insight.SL or np.isnan(insight.SL):
            return self.returnResults(False, False, "Insight does not have limit price or stop loss levels set.")
        
        # if the user has set the quantity, then we don't need to calculate it
        if insight.quantity is not None:
            return self.returnResults(True, True, "Quantity already set")

        # Calculate the quantity to trade
        try:
            #Add a Check if margin is enabled for this asset. If margin is enabled, then use buying_power to calculate the quantity.
            buying_power = self.STRATEGY.account.buying_power if self.STRATEGY.assets[insight.symbol]['marginable'] else self.STRATEGY.account.cash
            
            # Account size  to place order
            working_capital = buying_power * insight.confidence

            if working_capital < self.minimum_costbasis:
                response = self.returnResults(False, True, f"Working capital is less than the minimum cost basis: {self.minimum_costbasis} : Suggested: {working_capital}")
                self.changeState(
                    insight, InsightState.REJECTED, response.message)
                return response
            
            # Check if the working capital is greater than the maximum cost basis
            if working_capital > self.maximum_costbasis:
                working_capital = self.maximum_costbasis

            # Calculate the risk per share (PIP value)
            account_size_at_risk = working_capital * self.STRATEGY.execution_risk
            riskPerShare = abs(insight.limit_price - insight.SL)
        
            # Calculate the maximum quantity that can be bought
            maximun_can_buy = working_capital/insight.limit_price

            # Calculate the quantity to trade
            size_should_buy = account_size_at_risk/riskPerShare

            # Check if the quantity is greater than the maximum quantity that can be bought
            size_should_buy = min(size_should_buy, maximun_can_buy)

            if size_should_buy > 1:
                # Round down the quantity to the nearest whole number
                size_should_buy = np.floor(size_should_buy)
            else:
                #check if the asset is fractional or not
                if self.STRATEGY.assets[insight.symbol]['fractionable']:
                    # Although the quantity is less than 1, we can still buy a fraction of a share
                    # Round the quantity to the nearest 2 decimal places
                    # FIXME: This should always round down but right now it can round up. another function should be created to only round down dynamically to the closest minimum order size precision
                    size_should_buy = dynamic_round(size_should_buy)
                else:
                    response = self.returnResults(False, True, f"Asset is not fractionable: Suggested: {size_should_buy}")
                    self.changeState(
                        insight, InsightState.REJECTED, response.message)
                    return response

            # Check if the quantity is greater than the minimum order size
            minimum_order_size = self.STRATEGY.assets[insight.symbol]['min_order_size']

            # Check to see if we need to convert the to number of contracts
            if insight.uses_contract_size:
                size_should_buy = round(size_should_buy / self.STRATEGY.assets[insight.symbol]["contract_size"], 2)
                
            if size_should_buy < minimum_order_size:
                response = self.returnResults(False, True, f"Quantity is less than the minimum order size: {minimum_order_size} : Suggested: {size_should_buy}")
                self.changeState(
                    insight, InsightState.REJECTED, response.message)
                return response
            
            # Cap to max order size if it is set
            if self.STRATEGY.assets[insight.symbol].get('max_order_size', None) is not None:
                size_should_buy = min(size_should_buy, self.STRATEGY.assets[insight.symbol]['max_order_size'])


            # Update the quantity in the insight
            self.STRATEGY.insights[insight.INSIGHT_ID].update_quantity(
                size_should_buy)

            return self.returnResults(True, True, f"Quantity set to {size_should_buy}")
        except Exception as e:
            return self.returnResults(False, False, f"Error calculating quantity: {e}")
