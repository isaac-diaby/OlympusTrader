from datetime import datetime
from typing import Literal, Optional, TypedDict, Required, List
from enum import Enum
from typing import TYPE_CHECKING


from .timeframe import TimeFrame

from pandas import Timestamp


class IMarketDataStream(TypedDict):
    symbol: str
    exchange: str
    time_frame: TimeFrame
    asset_type: Literal['stock', 'crypto'] = 'crypto'
    type: Literal['trade', 'quote', 'bar', 'news'] = 'bar'
    stored: Optional[bool] = False
    stored_path: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class IStrategyMode(Enum):
    BACKTEST = 'Backtest'
    LIVE = 'Live'
