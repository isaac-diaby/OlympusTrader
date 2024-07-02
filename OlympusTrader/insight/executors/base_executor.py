import abc
from typing import TYPE_CHECKING, override
from pandas import DataFrame

from ...broker.interfaces import IQuote

from ..insight import Insight, InsightState


def get_BaseStrategy():
    from ...strategy.base_strategy import BaseStrategy
    return BaseStrategy


if TYPE_CHECKING:
    from ...strategy.base_strategy import BaseStrategy


class ExecutorResults():
    """
    ### Executor Results
    This class is used to store the results of the executor.
    """
    passed: bool
    """Boolean value indicating if the executor passed or not."""
    success: bool
    """Boolean value indicating if the executor was ran successful or not."""
    executor: str
    """Name of the executor."""
    message: str
    """Message indicating the result of the executor."""

    def __init__(self, passed: bool, success: bool = True, message: str = None, executor: str = None):
        self.passed = passed
        if passed:
            # If the executor passed, then it was successfully ran
            success = True
        self.success = success
        if self.success == False:
            # If the executor was not successfully ran, then it did not pass
            self.passed = False
        self.message = message
        self.executor = executor


class BaseExecutor(abc.ABC):
    """
    ### Abstract class for BaseExecutor implementations.
    Used to manage orders based on insights.
    """
    NAME: str
    VERSION: str
    """Version of the executor model."""
    STRATEGY: get_BaseStrategy
    """Reference to the strategy instance."""

    state: InsightState
    """Reference to the working state of the executor"""

    @abc.abstractmethod
    def __init__(self, strategy: get_BaseStrategy, state: InsightState, version: float = "1.0") -> None:
        self.NAME = self.__class__.__name__
        self.VERSION = version
        # Reference to the strategy instance
        self.STRATEGY = strategy
        self.state = state

    @override
    @abc.abstractmethod
    def run(self, insight: Insight) -> ExecutorResults:
        """Run the executor."""
        pass

    def returnResults(self, passed: bool, success: bool = True, message: str = None) -> ExecutorResults:
        return ExecutorResults(passed, success, message, self.NAME)

    # @property
    # def insight(self, insight: Insight):
    #     return self.STRATEGY.insights[insight.INSIGHT_ID]

    def changeState(self, insight: Insight, state: InsightState, message: str = None) -> None:
        self.STRATEGY.insights[insight.INSIGHT_ID].updateState(state, message)

    def get_history(self, symbol: str) -> DataFrame:
        return self.STRATEGY.history[symbol].loc[symbol]

    def get_latest_bar(self, symbol: str) -> DataFrame:
        return self.get_history(symbol).iloc[-1]

    def get_previos_bar(self, symbol: str) -> DataFrame:
        return self.get_history(symbol).iloc[-2]

    def get_latest_quote(self, insight: Insight) -> IQuote:
        return self.STRATEGY.broker.get_latest_quote(insight.ASSET)

    def _override_state(self, state: InsightState) -> None:
        assert isinstance(
            state, InsightState), "State must be an instance of InsightState"
        self.state = state
