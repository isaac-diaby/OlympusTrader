from ..base_executor import BaseExecutor
from ...insight import InsightState


class MinimumRiskToRewardExecutor(BaseExecutor):
    """
    ### Executor for Minimum Risk to Reward Ratio
    This executor is used reject insights that do not meet the minimum risk to reward ratio (RRR).

    **This will update your strategy instance with the minimum risk to reward ratio required.** (STRATEGY.minRewardRiskRatio), if not already set.

    :param strategy (BaseStrategy): The strategy instance
    :param minimumRR (float): The minimum risk to reward ratio required. Default is 2.0

    Note: You will need to have already set the limit price, stop loss and  take profit levels in the insight before using this executor.
    
    Author:
        @isaac-diaby
    """

    def __init__(self, strategy, minimumRR=None):
        super().__init__(strategy, InsightState.NEW, "1.0")

        # Set the minimum risk to reward ratio required for the strategy if provided
        if minimumRR is not None:
            self.STRATEGY.minRewardRiskRatio = minimumRR

        # check that the minimum risk to reward ratio is set
        if self.STRATEGY.minRewardRiskRatio is None or self.STRATEGY.minRewardRiskRatio <= 0:
            raise ValueError(
                "Please set the minimum risk to reward ratio required for the strategy")

    def run(self, insight):
        # Check if the insight has a limit price, stop loss and take profit levels
        if insight.limit_price is None or insight.SL is None or insight.TP is None:
            return self.returnResults(False, False, "Insight does not have limit price, stop loss or take profit levels set.")
        minimumRR = self.STRATEGY.minRewardRiskRatio
        RR = insight.getPnLRatio()
        if RR < minimumRR:
            response = self.returnResults(
                False, True, f"Risk to Reward ratio (RRR) is less than the minimum required -  {RR} < {minimumRR}")
            self.changeState(insight, InsightState.REJECTED, response.message)
            return response

        return self.returnResults(True, True)
