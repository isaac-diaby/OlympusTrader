from ..base_executor import BaseExecutor
from ...insight import InsightState, StrategyDependantConfirmation
from ....broker.interfaces import IOrderSide

class PercentageDCALevels(BaseExecutor):
    """
    ### Executor for Adding DCA Levels
    This executor is used to add DCA levels to a new insight that already had a desired quantity.

    It will append the DCA levels as childens to the insight based on the DCA percentage and levels set in the alpha.
    The child insights will have the same TP as the parent insight bur will alter the SL below / above  the last DCA level.
    The children insight strategyType will be set to the alpha name with a suffix of "_CHILD".

    :param strategy (BaseStrategy): The strategy instance
    :param includes (list[str]): The alphas to include
    :param dcaPercentage (float): The percentage to space the DCA levels
    :param dcalevels (int): The number of DCA levels to add
    Author:
        @isaac-diaby
    """
    includes: list[str]
    """alpha to include"""
    dcaPercentage: float
    dcalevels: int


    def __init__(self, strategy, includes: list[str], dcaPercentage: float = 0.01, dcalevels: int = 5):
        super().__init__(strategy, InsightState.NEW, "1.0")
        assert dcaPercentage > 0, "DCA percentage must be greater than 0."
        assert dcalevels > 0, "DCA levels must be greater than 0."
        self.includes = includes

        self.dcaPercentage = dcaPercentage
        self.dcalevels = dcalevels

    def run(self, insight):
        # check if insight strategyType alpha is part if the includes list
        if self.includes and insight.strategyType not in self.includes:
            return self.returnResults(True, True, "Alpha is not part of the includes list.")
        # Check if the insight has a desired quantity
        if insight.quantity is None:
            return self.returnResults(True, True, "Insight does not have a desired quantity.")
        # Check if the insight is a parent insight
        if insight.PARANT:
            return self.returnResults(True, True, "Insight is not a parent insight.")
        try:
            latestBar = self.get_latest_bar(insight.symbol)
            desiredQuantity = insight.quantity
            entry = insight.limit_price if insight.limit_price else latestBar['close']
            SL = insight.SL
            TP = insight.TP

            price_levels = [] # List to store the price levels for DCA

            price_levels.append(entry) # Append the entry price

            for i in range(1, self.dcalevels+1):
                # Every X% above / below the entry price
                if insight.side == IOrderSide.BUY:
                    dca_level = self.STRATEGY.tools.dynamic_round(entry * (1 - (self.dcaPercentage*i)), insight.symbol)
                else: # shorting
                    dca_level = self.STRATEGY.tools.dynamic_round(entry * (1 + (self.dcaPercentage*i)), insight.symbol)
                price_levels.append(dca_level)

            quantities = self.calculate_dca_quantities(desiredQuantity, price_levels)
            # the first quantity is the parent insight quantity
            insight.update_quantity(quantities[0])
            dca_SL = price_levels[-1] - ((entry - SL)/2)
            # Update the SL of the parent insight
            insight.SL = dca_SL


            # Add the DCA levels as children insights
            for i in range(1, len(quantities)-1):
                childInsight = insight.addChildInsight(
                    side=insight.side,
                    quantity=quantities[i] if insight.side == IOrderSide.BUY else quantities[len(quantities)-i],
                    limit_price=price_levels[i],
                    SL=dca_SL,
                    TP=TP,
                    executionDepends=[
                        StrategyDependantConfirmation.UPSTATE if insight.side == IOrderSide.BUY else StrategyDependantConfirmation.DOWNSTATE],
                )
            
            drawdowns, total_drawdowns = self.calculate_drawdowns(price_levels, quantities, dca_SL)
            print("Drawdowns: ", drawdowns)
            print("Total Drawdowns: ", total_drawdowns)
            return self.returnResults(True, True, "Added DCA levels to insight.")
        except Exception as e:
            return self.returnResults(False, False, f"Error Adding DCA to insight: {e}")
        
    def calculate_dca_quantities(self, total_quantity, price_levels):
        """
        Calculate the quantity to buy at each DCA level using the Inverse Price Proportionality method.

        :param total_quantity: Total desired quantity to accumulate.
        :param price_levels: List of prices at each DCA level.
        :return: List of quantities to buy at each level.
        """
        # Calculate the denominator (sum of inverses of prices)
        denominator = sum(1 / price for price in price_levels)
        
        # Calculate the quantity to buy at each level
        quantities = [round((total_quantity / denominator) * (1 / price), 4) for price in price_levels]
        
        return quantities
    def calculate_drawdowns(self, entry_prices, quantities, stop_loss_price):
        """
        Calculate the expected drawdown at each DCA level.
        
        :param entry_prices: List of entry prices at each DCA level.
        :param quantities: List of quantities bought at each DCA level.
        :param stop_loss_price: The stop loss price.
        :return: List of drawdowns for each level and total drawdown up to each level.
        """
        drawdowns = []
        total_drawdowns = []
        total_quantity = 0
        weighted_average_price = 0

        for i in range(len(entry_prices)):
            price = entry_prices[i]
            quantity = quantities[i]
            
            # Calculate drawdown for this level
            drawdown = (price - stop_loss_price) * quantity
            drawdowns.append(drawdown)
            
            # Update total quantity and weighted average price
            total_quantity += quantity
            weighted_average_price = ((weighted_average_price * (total_quantity - quantity)) + (price * quantity)) / total_quantity
            
            # Calculate total drawdown up to this level
            total_drawdown = (weighted_average_price - stop_loss_price) * total_quantity
            total_drawdowns.append(total_drawdown)

        return drawdowns, total_drawdowns