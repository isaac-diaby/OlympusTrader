
import abc
import datetime
from typing import Any, Awaitable, Callable, List, Literal, Union

from typing_extensions import override
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

from .interfaces import IQuote, ISupportedBrokers

from .interfaces import IAsset, IAccount, IOrder, IPosition, ITradeUpdateEvent
from ..insight.insight import Insight
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit
from ..strategy.interfaces import IMarketDataStream


class BaseBroker(abc.ABC):
    NAME: ISupportedBrokers = ISupportedBrokers.BASE
    DataFeed: str
    PAPER: bool

    @abc.abstractmethod
    def __init__(self, name: ISupportedBrokers = ISupportedBrokers.BASE, paper: bool = True, feed: str = None) -> None:
        """Abstract class for broker implementations."""
        load_dotenv()
        self.NAME = name
        self.PAPER = paper
        self.DataFeed = feed

    @override
    @abc.abstractmethod
    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
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
    def close_position(self, symbol: str, qty: float = None, percent: float = None) -> IOrder | None:
        pass

    @override
    @abc.abstractmethod
    def close_all_positions(self):
        """Close all open positions and cancel all open orders"""
        pass

    @override
    @abc.abstractmethod
    def get_orders(self) -> List[IOrder]:
        """Get all orders"""
        pass

    @override
    @abc.abstractmethod
    def get_order(self, order_id) -> IOrder | None:
        pass

    @override
    @abc.abstractmethod
    def get_latest_quote(self, asset: IAsset) -> IQuote:
        pass
    @override
    @abc.abstractmethod
    def close_order(self, order_id: str) -> any:
        pass

    @override
    @abc.abstractmethod
    def get_history(self, asset: IAsset, start=(datetime.now() - timedelta(days=7)), end=datetime.now(), resolution=ITimeFrame(5, ITimeFrameUnit.Minute)) -> pd.DataFrame:
        """Get historical data for a given asset open, high, low, close, volume"""

        assert isinstance(
            resolution, ITimeFrame), 'resolution must be of type TimeFrame object'

    @override
    @abc.abstractmethod
    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        """Manage insight order by planing entry and exit orders for a given insight"""
        assert isinstance(
            insight, Insight), 'insight must be of type Insight object'

        if not insight.validate()[0]:
            raise ValueError("Invalid Entry Insight")
        # assert isinstance(asset, Asset), 'asset must be of type Asset object'

    @override
    @abc.abstractmethod
    def startTradeStream(self, callback: Awaitable):
        """Listen to trades and order updates and call the callback function with the data"""
        print("Start Trade Stream -", self.NAME)
        pass

    @override
    @abc.abstractmethod
    async def closeTradeStream(self):
        pass

    @override
    @abc.abstractmethod
    def streamMarketData(self, callback: Awaitable, assetStreams: List[IMarketDataStream]):
        """Listen to market data and call the callback function with the data"""
        print("Stream Market Data -", self.NAME)
        pass

    @override
    @abc.abstractmethod
    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        pass

    @override
    @abc.abstractmethod
    def format_on_bar(self, bar: Any) -> pd.DataFrame:
        """
        Format stream bar data to { symbol: str, bar: -> open, high, low, close, volume}
        -  (data={}, index=[(str, pd.Timestamp)], columns=['open', 'high', 'low', 'close', 'volume']):

        """
        pass
    @override
    @abc.abstractmethod
    def format_on_quote(self, quote: Any) -> IQuote:
        """Format stream quote data"""
        pass
    @override
    @abc.abstractmethod
    def format_on_trade_update(self, trade: Any) -> tuple[IOrder, ITradeUpdateEvent]:
        """Format stream Trade Order data and event"""
        pass
