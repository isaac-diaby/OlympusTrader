import abc
from typing import TYPE_CHECKING, List, Optional, override

from pandas import DataFrame
import pandas_ta as ta
import numpy as np

from OlympusTrader.broker.interfaces import IAsset
from OlympusTrader.insight.insight import Insight


def get_BaseStrategy():
    from ..strategy.base_strategy import BaseStrategy
    return BaseStrategy


if TYPE_CHECKING:
    from ..strategy.base_strategy import BaseStrategy

class AlphaResults():
    """
    ### Alpha Results
    This class is used to store the results of the Alpha.
    """
    insight: Insight
    """Insight generated by the alpha."""
    success: bool
    """Boolean value indicating if the executor was ran successful or not."""
    alpha: str
    """Name of the executor."""
    message: str
    """Message indicating the result of the alpha."""

    def __init__(self, insight: Optional[Insight] = None, success: bool = True, message: str = None, alpha: str = None):
        self.insight = insight
        if insight:
            # If the executor passed, then it was successfully ran
            success = True
        self.success = success
        if self.success == False:
            # If the executor was not successfully ran, then it did not pass
            self.insight = None
        self.message = message
        self.alpha = alpha
class BaseAlpha(abc.ABC):
    """
    ### Abstract class for alpha implementations.
    Used to generate insights based on the strategy.
    """
    NAME: str
    """Name of the alpha model."""
    VERSION: str
    """Version of the alpha model."""

    STRATEGY: get_BaseStrategy
    """Reference to the strategy instance."""

    TA: List[dict] = []
    """List of technical analysis needed for the alpha model."""

    baseConfidenceModifierField: str
    """Field to modify base confidence."""
    @abc.abstractmethod
    def __init__(self, strategy: get_BaseStrategy, name: str, version: str = "1.0", baseConfidenceModifierField: Optional[str] = None) -> None:
        self.NAME = name
        self.VERSION = version

        # Reference to the strategy instance
        self.STRATEGY = strategy
        if baseConfidenceModifierField:
            self.baseConfidenceModifierField = baseConfidenceModifierField


    @abc.abstractmethod
    def start(self):
        """Initialize the alpha model once at the start. data, etc. in the state of the Strategy."""
        pass

    @abc.abstractmethod
    def init(self,  asset: IAsset):
        """Initialize the alpha model for each assets. variables, data, etc. in the state of the Strategy."""
        pass

    @abc.abstractmethod
    def generateInsights(self, symbol: str) -> AlphaResults:
        """Generate insights based on the alpha model."""
        pass

    def registerAlpha(self):
        self.STRATEGY.ALPHA_MODELS.append(self)
        # Set the technical analysis needed for the alpha
        self._loadTa()

    def returnResults(self, insight: Optional[Insight] = None, success: bool = True, message: str = None) -> AlphaResults:
        return AlphaResults(insight, success, message, self.NAME)

    def get_history(self, symbol: str) -> DataFrame:
        return self.STRATEGY.history[symbol].loc[symbol]

    def get_latest_bar(self, symbol: str) -> DataFrame:
        return self.get_history(symbol).iloc[-1]

    def get_previos_bar(self, symbol: str) -> DataFrame:
        return self.get_history(symbol).iloc[-2]

    def get_baseConfidenceModifier(self, symbol: str):
        if self.baseConfidenceModifierField:
            baseConfidenceModifier = self.STRATEGY.state[self.baseConfidenceModifierField][symbol]
            if baseConfidenceModifier:
                return baseConfidenceModifier

        return 1
    def _loadTa(self):
        if self.TA:
            self.STRATEGY.add_ta(self.TA)
