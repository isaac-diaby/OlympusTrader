from typing import override


from .base_strategy import BaseStrategy
from ..broker.base_broker import BaseBroker
from ..insight.insight import Insight



class Strategy(BaseStrategy):
    def __init__(self, broker: BaseBroker, **kwargs):
        super().__init__(broker, **kwargs)

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
