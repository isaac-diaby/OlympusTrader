from __future__ import annotations
import abc
from typing import TYPE_CHECKING, Optional, Self, override
from pandas import DataFrame

from ...broker.interfaces import IAsset, IQuote

from ..insight import Insight, InsightState, StrategyTypes


# def get_BaseStrategy():
#     from ...strategy.base_strategy import BaseStrategy
#     return BaseStrategy


if TYPE_CHECKING:
#     from ...strategy.base_strategy import BaseStrategy
    from OlympusTrader.strategy import BaseStrategy


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
    STRATEGY: BaseStrategy
    """Reference to the strategy instance."""

    state: InsightState
    """Reference to the working state of the executor"""

    ALLOWED_ASSETS: Optional[set[str]] = set()
    """Set of allowed assets for the executor"""
    ALLOWED_ALPHAS: Optional[set[str]] = set()
    """Set of allowed alphas for the executor"""
    ALLOW_INSIGHT_CHANGE_STATE: bool = True

    @abc.abstractmethod
    def __init__(self, strategy: BaseStrategy, state: InsightState, version: float = "1.0", allowed_assets:  Optional[set[str]] = None, allowed_alphas: Optional[set[str]] = None, allowed_insight_change_state: bool = True) -> None:
        self.NAME = self.__class__.__name__
        self.VERSION = version

        # assert isinstance(strategy, BaseStrategy), "strategy must be of type BaseStrategy."
        # Reference to the strategy instance
        self.STRATEGY = strategy
        self.state = state
        if allowed_assets is not None:
            assert isinstance(
                allowed_assets, set), "Allowed assets must be a set"
            self.ALLOWED_ASSETS = allowed_assets

        self.ALLOW_INSIGHT_CHANGE_STATE = allowed_insight_change_state

        if allowed_alphas is not None:
            assert isinstance(
                allowed_alphas, set), "Allowed alpha must be a set"
            self.ALLOWED_ALPHAS = allowed_alphas

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
        """Change the state of the insight"""
        if not self.ALLOW_INSIGHT_CHANGE_STATE:
            return
        self.STRATEGY.insights[insight.INSIGHT_ID].updateState(
            state, f"{self.NAME:^20} : {message}")

    def get_history(self, symbol: str) -> DataFrame:
        """Get the history of a symbol"""
        return self.STRATEGY.history[symbol].loc[symbol]

    def get_latest_bar(self, symbol: str) -> DataFrame:
        """Get the latest bar of a symbol"""
        return self.get_history(symbol).iloc[-1]

    def get_previos_bar(self, symbol: str) -> DataFrame:
        """Get the previous bar of a symbol"""
        return self.get_history(symbol).iloc[-2]
    
    def get_asset(self, symbol: str) -> IAsset:
        """Get the asset of a symbol"""
        return self.STRATEGY.UNIVERSE.get(symbol)

    def get_latest_quote(self, insight: Insight) -> IQuote:
        """Get the latest quote of an insight"""
        return self.STRATEGY.broker.get_latest_quote(insight.ASSET)

    def isAllowedAsset(self, symbol: str) -> bool:
        """Check if the asset is allowed"""
        if self.ALLOWED_ASSETS is None or len(self.ALLOWED_ASSETS) == 0:
            return True
        return symbol in self.ALLOWED_ASSETS
    
    def isAllowedAlpha(self, alpha: str) -> bool:
        """Check if the alpha is allowed"""
        if self.ALLOWED_ALPHAS is None or len(self.ALLOWED_ALPHAS) == 0 or isinstance(alpha, StrategyTypes ):
            return True
        return alpha in self.ALLOWED_ALPHAS
    
    def should_run(self, insight: Insight) -> bool:
        """Check if the executor should run"""
        return self.isAllowedAsset(insight.symbol) and self.isAllowedAlpha(insight.strategyType)

    def _override_state(self, state: InsightState) -> Self:
        """Override the state of the executor"""
        assert isinstance(
            state, InsightState), "State must be an instance of InsightState"
        self.state = state
        return self

    def _add_allowed_asset(self, asset: str) -> Self:
        """Add an asset to the allowed assets"""
        self.ALLOWED_ASSETS.add(asset)
        return self

    def _remove_allowed_asset(self, asset: str) -> Self:
        """Remove an asset from the allowed assets"""
        self.ALLOWED_ASSETS.remove(asset)
        return self
