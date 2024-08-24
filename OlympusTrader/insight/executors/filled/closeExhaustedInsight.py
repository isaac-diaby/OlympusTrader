from ..base_executor import BaseExecutor
from ...insight import InsightState


class CloseExhaustedInsightExecutor(BaseExecutor):
    """
    ### Executor for Closing Exhausted Insights
    This executor is used to close exhausted insights.

   :param strategy (BaseStrategy): The strategy instance

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.FILLED, "1.0")

    def run(self, insight):
        # Close the exhausted insight
        try:
            # check if the insight has not already been closed 
            if insight._closing:
                return self.returnResults(False, True, "Insight is being closed.")
            
            if self.STRATEGY.insights[insight.INSIGHT_ID].hasExhaustedTTL(True):
                return self.returnResults(False, True, "Insight closed due to being exhausted TTL.")
            return self.returnResults(True, True, "Insight has not expired.")
        except Exception as e:
            return self.returnResults(False, False, f"Error closing exhausted insight: {e}")
