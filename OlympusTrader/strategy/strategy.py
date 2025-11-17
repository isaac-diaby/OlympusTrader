from typing import override

from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit
from OlympusTrader.utils.types import AttributeDict


from .base_strategy import BaseStrategy
from ..broker.base_broker import BaseBroker
from ..insight.insight import Insight


class Strategy(BaseStrategy):
    def __init__(self, broker: BaseBroker,
                 variables: AttributeDict = AttributeDict({}),
                 resolution: ITimeFrame = ITimeFrame(1, ITimeFrameUnit.Minute),
                 verbose: int = 0,
                 ui: bool = True,
                 ssm: bool = True,
                 mode: IStrategyMode = IStrategyMode.LIVE,
                 tradeOnFeatureEvents: bool = False,
                 **kwargs):

        if type(variables) is not AttributeDict:
            variables = AttributeDict(variables)

        super().__init__(BROKER=broker,
                         RESOLUTION=resolution,
                         MODE=mode,
                         VARIABLES=variables,
                         VERBOSE=verbose,
                         WITHUI=ui,
                         WITHSSM=ssm,
                         tradeOnFeatureEvents=tradeOnFeatureEvents,
                         **kwargs)

    @override
    def start(self):
        super().start()

    @override
    def init(self, asset):
        super().init(asset)

    @override
    def universe(self) -> set[str]:
        super().universe()
        return {"AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"}

    @override
    def on_bar(self, symbol, bar):
        super().on_bar(symbol, bar)

    @override
    def teardown(self):
        super().teardown()

    @override
    def generateInsights(self, symbol: str):
        # Execute Orders If there should be any
        super().generateInsights(symbol)

    @override
    def executeInsight(self, insight: Insight):
        super().executeInsight(insight)
