from datetime import datetime
from typing import Literal, Optional, TypedDict, Required, List
from enum import Enum



from ..utils.timeframe import ITimeFrame



class IMarketDataStream(TypedDict):
    symbol: Required[str]
    exchange: str
    time_frame: Required[ITimeFrame]
    asset_type: Literal['stock', 'crypto'] = 'crypto'
    type: Required[Literal['trade', 'quote', 'bar', 'news']] = 'bar'
    stored: Optional[bool] = False
    stored_path: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class IStrategyMode(Enum):
    BACKTEST = 'Backtest'
    LIVE = 'Live'
