from ..base_executor import BaseExecutor
from ...insight import InsightState


class DefaultOnCancelledExecutor(BaseExecutor):
    """
    ### Executor for Default On Cancelled
    This executor is used to delete the insight from the strategy when it is cancelled.

    :param strategy (BaseStrategy): The strategy instance

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.CANCELED, "1.0")

    def run(self, insight):
        # Set the default state of the insight
        try:
            for i, order in self.STRATEGY.orders.items():
                if i == insight.order_id:
                    # Check if the insight is already filled
                    if (self.STRATEGY.insights[insight.INSIGHT_ID].state == InsightState.FILLED):
                        return self.returnResults(True, True, "Insight already filled. Not deleting.")

            del self.STRATEGY.insights[insight.INSIGHT_ID]
            return self.returnResults(True, True, "Insight Cancelled Successfully.")
        except Exception as e:
            return self.returnResults(False, False, f"Error deleting insight: {e}")
