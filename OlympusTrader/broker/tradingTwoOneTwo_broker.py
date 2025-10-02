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


class TradingTwoOneTwoBroker(BaseBroker):
    BASE_URL: str = 'https://demo.trading212.com/api/v0'
    API_HEADER: dict[str, str] = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        "Authorization": "YOUR_API_KEY_HERE"
    }
    def __init__(self, paper: bool, feed=None):
        super().__init__(ISupportedBrokers.T212, paper, feed)
        if paper:
            BASE_URL = 'https://demo.trading212.com/api/v0'
        else:
            BASE_URL = 'https://live.trading212.com/api/v0'

        assert os.getenv('T212_API_KEY'), 'T212_API_KEY not found'
        self.API_HEADER['Authorization'] = os.getenv('T212_API_KEY')
        self.supportedFeatures = ISupportedBrokerFeatures()
        raise NotImplementedError( "TradingTwoOneTwoBroker is not yet implemented.")
        

    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
        cached = super().get_ticker_info(symbol)
        if cached:
            return cached
        
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
