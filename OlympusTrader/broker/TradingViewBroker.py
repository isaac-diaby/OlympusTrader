from concurrent.futures import ThreadPoolExecutor
import os
from time import sleep
from .base_broker import BaseBroker
from .interfaces import (
    IOrderClass,
    IOrderLeg,
    IOrderLegs,
    ISupportedBrokers,
    ISupportedBrokerFeatures,
    IAsset,
    IAccount,
    IOrder,
    IPosition,
    IQuote,
    ITimeInForce,
    ITradeUpdate,
    ITradeUpdateEvent,
)
from .interfaces import IOrderSide, IOrderType
from ..strategy.interfaces import IMarketDataStream
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, List, Optional, Union
import asyncio
import numpy as np
from ..insight.insight import Insight


class TadingViewBroker(BaseBroker):
    def __init__(self, paper: bool, feed=None):
        super().__init__(ISupportedBrokers.PAPER, paper, feed)

        assert os.getenv('xxxx'), 'xxxx not found'
        self.supportedFeatures = ISupportedBrokerFeatures()
        raise NotImplementedError( "TadingViewBroker is a template class.")

    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
        # Implement the logic to retrieve ticker information
        pass
    def get_account(self) -> IAccount:
        pass
    def get_position(self, symbol) -> IPosition:
        pass
    def get_positions(self) -> dict[str, IPosition]:
        pass
    def close_position(self, symbol: str, qty: Optional[float] = None, percent: Optional[float] = None) -> Optional[IOrder]:
        pass
    def close_all_positions(self):
        pass
    def get_orders(self) -> Optional[dict[str, IOrder]]:
        pass
    def get_order(self, order_id) -> Optional[IOrder]:
        pass
    def get_latest_quote(self, asset: IAsset) -> IQuote:
        pass
    def cancel_order(self, order_id: str) -> Optional[str]:
        pass
    def update_order(self, order_id: str, price: float,  qty: float) -> Optional[IOrder]:
        pass
    def get_history(self, asset: IAsset, start=(datetime.now() - timedelta(days=7)), end=datetime.now(), resolution=ITimeFrame(5, ITimeFrameUnit.Minute)) -> pd.DataFrame:
        pass
    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        pass
    def startTradeStream(self, callback: Awaitable):
        pass
    async def closeTradeStream(self):
        pass
    def streamMarketData(self, callback: Awaitable, assetStreams: List[IMarketDataStream]):
        pass
    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        pass
    def format_on_bar(self, bar: Any, symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        pass
    def format_on_quote(self, quote: Any) -> IQuote:
        pass
    def format_order(self, order: Any) -> IOrder:
        pass
    def format_position(self, position: Any) -> IPosition:
        pass
