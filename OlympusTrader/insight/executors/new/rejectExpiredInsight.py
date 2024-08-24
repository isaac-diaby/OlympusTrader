from ..base_executor import BaseExecutor
from ...insight import InsightState


class RejectExpiredInsightExecutor(BaseExecutor):
    """
    ### Executor for Rejecting Expired Insights
    This executor is used to reject insights that have expired.

   :param strategy (BaseStrategy): The strategy instance
   
    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.NEW, "1.0")

    def run(self, insight):
        # Check if the insight has expired
        try:
            hasExpired = self.STRATEGY.insights[insight.INSIGHT_ID].hasExpired(
                True)
            if hasExpired == None:
                response = self.returnResults(
                    True, True, "Insight state is not applicable for expiration check.")
                return response
            if hasExpired == True:
                response = self.returnResults(
                    False, True, "Insight has expired. Rejecting insight.")
                return response

            return self.returnResults(True, True)
        except Exception as e:
            return self.returnResults(False, False, f"Error rejecting expired insight: {e}")
