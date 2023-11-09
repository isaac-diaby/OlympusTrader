
import abc
import datetime
from typing import Any, Awaitable, Callable, List, Literal, override, Union

import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

from ..utils.interfaces import Asset, IAccount, IOrder, IPosition
from ..utils.insight import Insight
from ..utils.timeframe import TimeFrame, TimeFrameUnit


class BaseBroker(abc.ABC):
    name = 'BaseBroker'
    DataFeed: str
    PAPER: bool

    @abc.abstractmethod
    def __init__(self, paper: bool = True, feed: str = None, name='BaseBroker') -> None:
        """Abstract class for broker implementations."""
        # super().__init__()
        load_dotenv()
        self.name = name
        self.PAPER = paper
        self.DataFeed = feed

    @override
    @abc.abstractmethod
    def get_ticker_info(self, symbol: str) -> Union[Asset, None]:
        pass

    @override
    @abc.abstractmethod
    def get_account(self) -> IAccount:
        pass

    @override
    @abc.abstractmethod
    def get_position(self, symbol) -> IPosition:
        pass

    @override
    @abc.abstractmethod
    def get_positions(self) -> dict[str, IPosition]:
        pass

    @override
    @abc.abstractmethod
    def get_orders(self) -> List[IOrder]:
        pass

    @override
    @abc.abstractmethod
    def get_order(self, order_id) -> IOrder:
        pass

    @override
    @abc.abstractmethod
    def get_history(self, asset: Asset, start=(datetime.now() - timedelta(days=7)), end=datetime.now(), resolution=TimeFrame(5, TimeFrameUnit.Minute)) -> pd.DataFrame:
        """Get historical data for a given asset open, high, low, close, volume"""

        assert isinstance(
            resolution, TimeFrame), 'resolution must be of type TimeFrame object'

    @override
    @abc.abstractmethod
    def close_position(self, symbol: str, qty:int =None, percent: int=None):
        pass

    @override
    @abc.abstractmethod
    def close_all_positions(self):
        """Close all open positions and cancel all open orders"""
        pass

    @override
    @abc.abstractmethod
    def manage_insight_order(self, insight: Insight, asset: Asset):
        """Manage insight order by planing entry and exit orders for a given insight"""
        assert isinstance(insight, Insight), 'insight must be of type Insight object'
        # assert isinstance(asset, Asset), 'asset must be of type Asset object'
        
    @override
    @abc.abstractmethod
    def startTradeStream(self, callback: Awaitable):
        pass

    @override
    @abc.abstractmethod
    async def closeTradeStream(self):
        pass

    @override
    @abc.abstractmethod
    def streamBar(self,  callback: Awaitable, symbol: str, AssetType: Literal['stock', 'crypto'] = 'stock'):
        pass

    @override
    @abc.abstractmethod
    def startStream(self, assetType: Literal['stock', 'crypto'], type: Literal['bars', 'quotes', 'trades'] = 'bars'):
        pass

    @override
    @abc.abstractmethod
    async def closeStream(self, assetType: Literal['stock', 'crypto'], type: Literal['bars', 'quotes', 'trades'] = 'bars'):
        pass

    @override
    @abc.abstractmethod
    def format_on_bar(self, bar: Any) -> pd.DataFrame:
        """Format stream bar data to { symbol: str, bar: -> open, high, low, close, volume}"""
        pass

    @override
    @abc.abstractmethod
    def format_on_trade_update(self, trade: Any) -> pd.DataFrame:
        """Format stream quote data to { symbol: str, quote: -> bid, bidSize, ask, askSize, timestamp}"""
        pass
