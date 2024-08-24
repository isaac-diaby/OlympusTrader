from ..base_executor import BaseExecutor
from ...insight import InsightState


class DefaultOnRejectExecutor(BaseExecutor):
    """
    ### Executor for Default On Reject
    This executor is used to delete the insight from the strategy when it is rejected.

    :param strategy (BaseStrategy): The strategy instance

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.REJECTED, "1.0")

    def run(self, insight):
        # Set the default state of the insight
        try:
            del self.STRATEGY.insights[insight.INSIGHT_ID]
            return self.returnResults(False, True, "Insight Rejected Successfully.")
        except Exception as e:
            return self.returnResults(False, False, f"Error deleting insight: {e}")
