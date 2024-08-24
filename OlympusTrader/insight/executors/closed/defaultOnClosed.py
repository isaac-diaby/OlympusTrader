from ..base_executor import BaseExecutor
from ...insight import InsightState


class DefaultOnClosedExecutor(BaseExecutor):
    """
    ### Executor for Default On Closed
    This executor is used to delete the insight from the strategy when it is closed.

    :param strategy (BaseStrategy): The strategy instance
    
    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.CLOSED, "1.0")

    def run(self, insight):
        # Set the default state of the insight
        try:

            if insight.close_order_id is not None:
                del self.STRATEGY.insights[insight.INSIGHT_ID]
                return self.returnResults(True, True, "Insight Closed Successfully.")
            else:
                # set the insight back to filled as it has no close order id
                self.STRATEGY.insights[insight.INSIGHT_ID].updateState(
                    InsightState.FILLED, "Insight does not have a close order id but was set to Closed.")
                return self.returnResults(False, True, "Insight does not have a close order id.")

        except Exception as e:
            return self.returnResults(False, False, f"Error deleting insight: {e}")
