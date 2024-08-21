from datetime import datetime
from typing import Literal, Optional, TypedDict, Required, List
from enum import Enum
import pandas_ta as ta



from ..utils.timeframe import ITimeFrame



class IMarketDataStream(TypedDict):
    symbol: Required[str]
    exchange: str
    time_frame: Required[ITimeFrame]
    feature: Optional[str] = None
    asset_type: Literal['stock', 'crypto'] = 'crypto'
    type: Required[Literal['trade', 'quote', 'bar', 'news']] = 'bar'
    stored: Optional[bool] = False
    stored_path: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    applyTA: Optional[bool] = False
    TA: Optional[ta.Strategy] = None

class IBacktestingConfig(TypedDict):
    preemptiveTA: Optional[bool] = False

class IStrategyMode(Enum):
    BACKTEST = 'Backtest'
    LIVE = 'Live'
