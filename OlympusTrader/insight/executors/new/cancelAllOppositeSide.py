from ..base_executor import BaseExecutor
from ...insight import InsightState


class CancelAllOppositeSidetExecutor(BaseExecutor):
    """
    ### Executor for Cancel All Opposite Side
    This executor is used to cancel all opposite side Insights generated for the insight symbol.
    This is done by setting the market changed flag to True for all opposite side insights and closing or cancelling the trades insights.

    :param strategy (BaseStrategy): The strategy instance

    Author:
        @isaac-diaby
    """

    def __init__(self, strategy):
        super().__init__(strategy, InsightState.NEW, "1.0")

    def run(self, insight):
        try:
            # Check if we have any current positions for the symbol
            holding = self.STRATEGY.positions.get(insight.symbol)
            if holding is None:
                return self.returnResults(True, True, "No current positions for symbol.")

            if holding["side"] != insight.side:
                # Set the market changed flag to True for all opposite side insights
                numberOfInsightsAffected = 0
                numberOfInsightsFailed = 0

                for id, otherInsight in self.STRATEGY.insights.items():
                    if otherInsight.symbol == insight.symbol and otherInsight.side != insight.side:
                        try:
                            if self.STRATEGY.insights[otherInsight.INSIGHT_ID].update_market_changed(marketChanged=True, shouldCloseOrCancel=True):
                                numberOfInsightsAffected += 1
                        except Exception as e:
                            numberOfInsightsFailed += 1
                            continue

                return self.returnResults(True, True, f"Updated {numberOfInsightsAffected} insights. Failed to update {numberOfInsightsFailed} insights.")
            return self.returnResults(True, True)
        except Exception as e:
            return self.returnResults(False, False, f"Error rejecting expired insight: {e}")
