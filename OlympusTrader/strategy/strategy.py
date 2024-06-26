from typing import override


from .base_strategy import BaseStrategy
from ..broker.base_broker import BaseBroker
from ..utils.insight import Insight

from ..utils.types import AttributeDict


class Strategy(BaseStrategy):
    def __init__(self, broker: BaseBroker, **kwargs):
        super().__init__(broker, **kwargs)

    @override
    def start():
        super().start()
    
    @override
    def init(self, asset):
        super().init()

    @override
    def universe(self):
        super().universe()

    @override
    async def on_bar(self, bar):
        super().on_bar(bar)

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
