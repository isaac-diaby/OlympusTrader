from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, TypedDict, Required, List
from enum import Enum
import pandas_ta as ta
from numpy import divide


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


@dataclass
class IStrategyMatrics:
    start_date: Optional[datetime] = None
    """ The start date """
    end_date: Optional[datetime] = None
    starting_cash: float = 0.0
    """ The starting cash """

    total_open: int = 0
    """ The total number of open trades """
    total_closed: int = 0
    """ The total number of closed trades """
    total_wins: int = 0
    """ The total number of winning trades """
    total_losses: int = 0
    """ The total number of losing trades """
    total_profit: float = 0.0
    """ The total profit """
    total_loss: float = 0.0
    """ The total loss """
    total_pnl: float = 0.0
    """ The total profit and loss """

    # DERIVED METRICS
    win_rate: float = 0.0
    """ The total win rate """
    avg_win: float = 0.0
    """ The average win """
    avg_loss: float = 0.0
    """ The average loss """

    # TODO: Add the following metrics
    # total_risk: float = 0.0
    # """ The total risk - market value of the trades """
    # total_risk_reward_ratio: float = 0.0
    # """ The total risk reward ratio """
    # total_fees: float = 0.0
    # """ The total fees """
    # total_profit_factor: float = 0.0
    # """ The total profit factor """
    # total_sharpe_ratio: float = 0.0
    # """ The total sharpe ratio """

    def updateStart(self, start_date: datetime, starting_cash: float):
        """ Update the start date and starting cash """
        self.start_date = start_date
        self.starting_cash = starting_cash

    def updateDerivedMetrics(self):
        """ Update the derived metrics """
        if self.total_wins == 0 or self.total_closed == 0:
            self.win_rate = 0.0
        else:
            self.win_rate = round(divide(self.total_wins,  self.total_closed),2)

        if self.total_profit == 0 or self.total_wins == 0:
            self.avg_win = 0.0
        else:
            self.avg_win = divide(self.total_profit, self.total_wins)

        if self.total_loss == 0 or self.total_losses == 0:
            self.avg_loss = 0.0
        else:
            self.avg_loss = divide(self.total_loss, self.total_losses)

    def positionOpened(self):
        """ Update the metrics when a position is opened """
        self.total_open += 1

    def positionClosed(self, pnl: float):
        """ Update the metrics when a position is closed """
        if pnl > 0:
            self.total_wins += 1
            self.total_profit += pnl
        else:
            self.total_losses += 1
            self.total_loss += pnl
        self.total_pnl += pnl
        self.total_closed += 1
        self.updateDerivedMetrics()
