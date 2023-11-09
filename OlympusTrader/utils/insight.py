from datetime import datetime
from enum import Enum
from typing import List, Literal
from .timeframe import TimeFrame


class StrategyTypes(Enum):
    RSI_DIVERGANCE = 'RSI_DIVERGANCE'
    EMA_CROSSOVER = 'EMA_CROSSOVER'

class InsightState(Enum):
    NEW = 'NEW'
    EXECUTED = 'EXECUTED'
    FILLED = 'FILLED'
    CLOSED = 'CLOSED'
    CANCELED = 'CANCELED'
    REJECTED = 'REJECTED'
    EXPIRED = 'EXPIRED'

class Insight:
    order_id: str = None
    side: Literal['long', 'short'] = None # buy or sell
    symbol: str = None # symbol to trade
    quantity: float = None # quantity to trade
    type: Literal['MARKET', 'LIMIT'] = None # market, limit, stop, stop_limit, trailing_stop
    classType: Literal['SIMPLE', 'BRACKET', 'OCO', 'OTO'] = None # simple, bracket, oco, oto 
    limit_price: List[float] = None # price to enter at
    strategyType: StrategyTypes = None # strategy type
    confidence: float = None # confidence in insight
    TP: List[float] = None # take profit levels
    SL: float = None # stop loss
    tf: TimeFrame = None # timeframe
    periodUnfilled: int = None # time to live when unfilled
    periodTillTp: int = None # predicted time to live when opened to reach take profit
    executionDepends: Literal['NONE','HRVCM', 'LRVCM', 'HTFCM'] = None # execution depends on
    state: InsightState = None
    createAt: datetime = None
    updatedAt: datetime = None

    def __init__(self, side: str, symbol: str,  StrategyType: StrategyTypes, tf: TimeFrame, quantity: float = 1, limit_price: float = None, TP: List[float] = None, SL: float = None,  confidence: float = 0.1, executionDepends: Literal['NONE','HRVCM', 'LRVCM', 'HTFCM'] = 'NONE', periodUnfilled: int = None, periodTillTp: int = 3):
        self.side = side # buy or sell
        self.symbol = symbol # symbol to trade
        self.quantity = quantity # quantity to trade
        self.limit_price = limit_price # price to enter at 
        self.strategyType = StrategyType # strategy type
        self.confidence = confidence # confidence in insight
        self.TP = TP # take profit levels
        self.SL = SL # stop loss
        self.tf = tf # timeframe
        self.periodUnfilled = periodUnfilled # time to live when unfilled
        self.periodTillTp = periodTillTp # predicted time to live when opened to reach take profit
        self.executionDependends = executionDepends # execution depends on 
        self.state = InsightState.NEW
        self.createAt = datetime.now()
        self.updatedAt = datetime.now()

        if limit_price == None:
            self.type = 'MARKET'
        else:
            self.type = 'LIMIT'

        if self.TP and self.SL:
            self.classType = 'BRACKET'
        else:
            self.classType = 'SIMPLE'

    def updateState(self, state: InsightState, message: str = None):
       print(f"Updated Insight State: {self.state:^10} -> {state:^10}: {self.symbol:^8} : {self.strategyType} :", message)
       self.state = state
       self.updatedAt = datetime.now()
       return self
    
    def hasExpired(self):
        if self.periodUnfilled == None:
            return False
        
        expireAt = self.tf.add_time_increment(self.createAt, self.periodUnfilled)
        hasExpired = expireAt < datetime.now()
        if self.state == InsightState.NEW and hasExpired:
            self.updateState(InsightState.EXPIRED)

        return hasExpired
    
    def updateOrderID(self, order_id: str):
        self.order_id = order_id
        self.updatedAt = datetime.now()
        return self
    
    def getPnLRatio(self, entry_price: float):
        if self.TP and self.SL:
            return round((abs(self.TP[0] - entry_price)) / (abs(entry_price - self.SL)), 2)
        else:
            return None



