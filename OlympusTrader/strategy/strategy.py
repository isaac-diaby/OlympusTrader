from typing import override

from .base_strategy import BaseStrategy
from ..broker.base_broker import BaseBroker
from ..utils.types import AttributeDict


class Strategy(BaseStrategy):
    def __init__(self, broker: BaseBroker,  **kwargs):
        super().__init__(broker, **kwargs)

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

    def executeInsight(self, symbol: str):
        super().executeInsight(symbol)
