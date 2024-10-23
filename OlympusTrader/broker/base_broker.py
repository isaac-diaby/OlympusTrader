
import abc
import datetime
from typing import Any, Awaitable, Callable, List, Literal, Optional, Union

from typing_extensions import override
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

from .interfaces import IQuote, ISupportedBrokerFeatures, ISupportedBrokers, ITradeUpdate

from .interfaces import IAsset, IAccount, IOrder, IPosition, ITradeUpdateEvent
from ..insight.insight import Insight
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit
from ..strategy.interfaces import IMarketDataStream


class BaseBroker(abc.ABC):
    NAME: ISupportedBrokers = ISupportedBrokers.BASE
    DataFeed: Optional[str]
    PAPER: bool

    supportedFeatures: ISupportedBrokerFeatures

    TICKER_INFO: dict[str, IAsset] = {}

    @abc.abstractmethod
    def __init__(self, name: ISupportedBrokers = ISupportedBrokers.BASE, paper: bool = True, feed: Optional[str] = None) -> None:
        """Abstract class for broker implementations."""
        load_dotenv()
        self.NAME = name
        self.PAPER = paper
        self.DataFeed = feed


    @abc.abstractmethod
    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
        pass


    @abc.abstractmethod
    def get_account(self) -> IAccount:
        pass


    @abc.abstractmethod
    def get_position(self, symbol) -> IPosition:
        pass


    @abc.abstractmethod
    def get_positions(self) -> dict[str, IPosition]:
        pass


    @abc.abstractmethod
    def close_position(self, symbol: str, qty: Optional[float] = None, percent: Optional[float] = None) -> Optional[IOrder] :
        """Close a position by symbol"""
        assert qty or percent, "qty or percent must be provided"
        if percent:
            assert (percent > 0) and (percent <= 1), "percent must be with in the range of 0-1"
        pass

    @abc.abstractmethod
    def close_all_positions(self):
        """Close all open positions and cancel all open orders"""
        pass


    @abc.abstractmethod
    def get_orders(self) -> Optional[dict[str, IOrder]]:
        """Get all orders"""
        pass


    @abc.abstractmethod
    def get_order(self, order_id) -> Optional[IOrder]:
        pass


    @abc.abstractmethod
    def get_latest_quote(self, asset: IAsset) -> IQuote:
        pass

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> Optional[str]:
        pass


    @abc.abstractmethod
    def get_history(self, asset: IAsset, start=(datetime.now() - timedelta(days=7)), end=datetime.now(), resolution=ITimeFrame(5, ITimeFrameUnit.Minute)) -> pd.DataFrame:
        """Get historical data for a given asset open, high, low, close, volume"""

        assert isinstance(
            resolution, ITimeFrame), 'resolution must be of type TimeFrame object'


    @abc.abstractmethod
    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        """Manage insight order by planing entry and exit orders for a given insight"""
        assert isinstance(
            insight, Insight), 'insight must be of type Insight object'
        valid, message = insight.validate()
        if not valid:
            raise ValueError("Invalid Entry Insight:", message)
        # assert isinstance(asset, Asset), 'asset must be of type Asset object'


    @abc.abstractmethod
    def startTradeStream(self, callback: Awaitable):
        """Listen to trades and order updates and call the callback function with the data"""
        print("Start Trade Stream -", self.NAME)
        pass


    @abc.abstractmethod
    async def closeTradeStream(self):
        pass


    @abc.abstractmethod
    def streamMarketData(self, callback: Awaitable, assetStreams: List[IMarketDataStream]):
        """Listen to market data and call the callback function with the data"""
        for assetStream in assetStreams:
            assert assetStream['symbol'], 'assetStream must have a symbol'
            assert assetStream['time_frame'], 'assetStream must have a time_frame'
            assert assetStream['type'], 'assetStream must have a type'
        print("Stream Market Data -", self.NAME)
        pass


    @abc.abstractmethod
    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        pass


    @abc.abstractmethod
    def format_on_bar(self, bar: Any, symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Format stream bar data to { symbol: str, bar: -> open, high, low, close, volume}
        -  (data={}, index=MultiIndex[(str, pd.Timestamp)], columns=['open', 'high', 'low', 'close', 'volume']):
        """
        pass

    @abc.abstractmethod
    def format_on_quote(self, quote: Any) -> IQuote:
        """Format stream quote data"""
        pass

    @abc.abstractmethod
    def format_order(self, order: Any) -> IOrder:
        """Format stream Order data"""
        pass
    
    @abc.abstractmethod
    def format_on_trade_update(self, trade: Any) -> tuple[IOrder, ITradeUpdateEvent]:
        """Format stream Trade Order data and event"""
        if isinstance(trade, ITradeUpdate):
            return trade.order, trade.event
        
    @property
    def get_current_time(self) -> datetime:
        """Get the current broker time"""
        return datetime.now()
