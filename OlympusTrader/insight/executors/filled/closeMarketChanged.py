from ..base_executor import BaseExecutor
from ...insight import InsightState


class CloseMarketChangedExecutor(BaseExecutor):
    """
    ### Executor for Closing Market Changed Insights
    This executor is used to close insights that have the market changed flag to true.

    Args:
        strategy (BaseStrategy): The strategy instance

    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.FILLED, "1.0")

    def run(self, insight):
        # Close the imarket channel
        try:
            if self.STRATEGY.insights[insight.INSIGHT_ID].marketChanged == True:
                self.STRATEGY.insights[insight.INSIGHT_ID].close()
                return self.returnResults(False, True, "Insight closed due to market change.")
            return self.returnResults(True, True, "Insight has not expired.")
        except Exception as e:
            return self.returnResults(False, False, f"Error closing market changed insight: {e}")
