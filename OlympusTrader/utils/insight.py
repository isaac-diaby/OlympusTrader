from datetime import datetime
from enum import Enum
from typing import List, Literal
from uuid import uuid4


from .timeframe import ITimeFrame
from ..broker.interfaces import IOrderSide, IOrderType, IOrderClass
# from ..broker.base_broker import BaseBroker
from ..utils.interfaces import IStrategyMode


class StrategyTypes(Enum):
    RSI_DIVERGANCE = 'RSI_DIVERGANCE'
    EMA_CROSSOVER = 'EMA_CROSSOVER'
    MANUAL = 'MANUAL'
    TEST = 'TESTING'


class StrategyDependantConfirmation(Enum):
    NONE = 'NONE'
    HRVCM = 'High Relative Volume Confirmation Model'
    LRVCM = 'Low Relative Volume Confirmation Model'
    HTFCM = 'High Time Frame Confirmation Model'


class InsightState(Enum):
    NEW = 'NEW'
    EXECUTED = 'EXECUTED'
    FILLED = 'FILLED'
    CLOSED = 'CLOSED'
    CANCELED = 'CANCELED'
    REJECTED = 'REJECTED'
    EXPIRED = 'EXPIRED'


class Insight:
    INSIGHT_ID = uuid4()
    order_id: str = None
    side: IOrderSide = None  # buy or sell
    symbol: str = None  # symbol to trade
    quantity: float = None  # quantity to trade
    type: IOrderType = None  # market, limit, stop, stop_limit, trailing_stop
    classType: IOrderClass = None  # simple, bracket, oco, oto
    limit_price: List[float] = None  # price to enter at
    strategyType: StrategyTypes = None  # strategy type
    confidence: float = None  # confidence in insight
    TP: List[float] = None  # take profit levels
    SL: float = None  # stop loss
    tf: ITimeFrame = None  # timeframe
    periodUnfilled: int = None  # time to live when unfilled
    periodTillTp: int = None  # predicted time to live when opened to reach take profit
    executionDepends: List[StrategyDependantConfirmation] = [
        StrategyDependantConfirmation.NONE]  # execution depends on
    state: InsightState = None
    createAt: datetime = None
    updatedAt: datetime = None
    filledAt: datetime = None
    closedAt: datetime = None
    close_order_id = None
    close_price: float = None  # price to close at

    marketChanged: bool = False

    MODE: IStrategyMode = IStrategyMode.LIVE
    BROKER = None

    def __init__(self, side: IOrderSide, symbol: str,  StrategyType: StrategyTypes, tf: ITimeFrame, quantity: float = 1, limit_price: float = None, TP: List[float] = None, SL: float = None,  confidence: float = 0.1, executionDepends: List[StrategyDependantConfirmation] = [StrategyDependantConfirmation.NONE], periodUnfilled: int = 2, periodTillTp: int = 10):
        assert side in IOrderSide, 'Invalid Order Side'
        self.side = side  # buy or sell
        self.symbol = symbol  # symbol to trade
        self.quantity = quantity  # quantity to trade
        self.limit_price = limit_price  # price to enter at
        self.strategyType = StrategyType  # strategy type
        self.confidence = confidence  # confidence in insight
        self.TP = TP  # take profit levels
        self.SL = SL  # stop loss
        self.tf = tf  # timeframe
        self.periodUnfilled = periodUnfilled  # time to live when unfilled
        # predicted time to live when opened to reach take profit
        self.periodTillTp = periodTillTp
        self.executionDependends = executionDepends  # execution depends on
        self.state = InsightState.NEW
        self.createAt = datetime.now()
        self.updatedAt = datetime.now()

        if limit_price == None:
            self.type = IOrderType.MARKET
        else:
            self.type = IOrderType.LIMIT

        if self.TP and self.SL:
            self.classType = IOrderClass.BRACKET
        else:
            self.classType = IOrderClass.SIMPLE

    def __str__(self):
        if self.strategyType == StrategyTypes.MANUAL:
            return f"Insight - {self.state:<5} : {self.strategyType:^16} - {self.symbol:^8} :: {self.side:^5}: {str(self.quantity)} @ MARKET"
        return f"Insight - {self.state:<5} : {self.strategyType:^16} - {self.symbol:^8} :: {self.side:^5}: {str(self.quantity)} @ {str(self.limit_price if self.limit_price else "MARKET"):^5} - TP: {str(self.TP):^5} - SL: {self.SL:^5} - Ratio: {str(self.getPnLRatio()):^10} - TTLUF/TTL: {str(self.periodUnfilled):^5}/{str(self.periodTillTp):^5} - UDA: {self.updatedAt}"

    def updateState(self, state: InsightState, message: str = None):
        print(
            f"Updated Insight State: {self.state:^10} -> {state:^10}: {self.symbol:^8} : {self.strategyType} :", message)
        self.state = state
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time()
        if self.state == InsightState.FILLED:
            self.filledAt = self.updatedAt
        if self.state == InsightState.CLOSED:
            self.closedAt = self.updatedAt
            # Print the P/L of the trade
            print(self.logPnL())

        return self

    def update_limit_price(self, price: float):
        # check if price is the same as the limit price
        if price == self.limit_price:
            print(
                f"Limit price is the same as the current limit price: {price} == {self.limit_price}")
            return False
        # check if the insight is already filled
        if self.state == InsightState.FILLED:
            print(
                f"Insight is already filled: {self.symbol} - {self.side} - {self.quantity} @ {self.limit_price}")
            return False
        # check if the price is within the take profit and stop loss
        if not self.checkValidEntryInsight(price):
            return False
        self.limit_price = price
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time()
        self.type = 'LIMIT'

        # check if the insight is already executed
        if self.state == InsightState.EXECUTED:

            # TODO: Need to check if the order is already placed and update it
            # self.updateState(InsightState.FILLED, 'Trade Filled')
            pass
        return self

    # TODO: def update_take_profit(self, price: float):
    # TODO: def update_stop_loss(self, price: float):

    def checkValidEntryInsight(self, limit_price: float = None):
        """Check if the insight is valid. limitprice needs to be beween the take profit and stop loss."""
        if (self.strategyType != StrategyTypes.TEST or self.strategyType != StrategyTypes.MANUAL):
            return True # skip the check for manual and test insights
        
        limit_price = limit_price if limit_price != None else self.limit_price
        # FIXME: use the broker to get the latest price and to check if the market order would be within range of the bracket order 
        if limit_price == None:
            print("WARNING: invalid entry insight: limit price is not set")
            return False
        if self.SL:
            if (limit_price < self.SL and self.side == 'long') or (limit_price > self.SL and self.side == 'short'):
                print("invalid entry insight: limit price is below the stop loss")
                return False
        if self.TP:
            for tp in self.TP:
                if (limit_price > tp and self.side == 'long') or (limit_price < tp and self.side == 'short'):
                    print("invalid entry insight: limit price is above the take profit")
                    return False
        # if self.quantity:
        #     print("invalid entry insight: quantity is invalid")
        #     return False
        return True

    def hasExpired(self, shouldUpdateState: bool = False):
        if self.periodUnfilled == None:
            return False

        expireAt = self.tf.add_time_increment(
            self.createAt, self.periodUnfilled)
        hasExpired = expireAt < (datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time())

        if (self.state == InsightState.EXECUTED or self.state == InsightState.NEW) and hasExpired and shouldUpdateState:
            self.updateState(InsightState.CANCELED, 'Unfilled TTL expired')

        return hasExpired

    def hasExhaustedTTL(self, shouldUpdateState: bool = False):
        if self.periodTillTp == None:
            return False

        expireAt = self.tf.add_time_increment(
            self.filledAt, self.periodTillTp)
        hasExpired = expireAt < (datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time())
        if (self.state == InsightState.FILLED) and hasExpired and shouldUpdateState:
            self.updateState(InsightState.CLOSED, 'Filled TTL expired')

        return hasExpired

    def updateOrderID(self, order_id: str):
        self.order_id = order_id
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time()
        return self
    def updateCloseOrderID(self, close_order_id: str):
        self.close_order_id = close_order_id
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time()
        return self

    def positionFilled(self, price: float, qty: float, order_id: str = None):
        if order_id != None:
            self.updateOrderID(order_id)
        self.limit_price = price
        self.quantity = qty
        self.updateState(InsightState.FILLED, f"Trade Filled: {
                         self.symbol} - {self.side} - {self.quantity} @ {self.limit_price}")
        return self

    def positionClosed(self, price: float, close_order_id: str, qty: float = None):
        if qty != None:
            self.quantity = qty
        # Handle multiple Take Profit levels
        if self.close_price != None:
            self.close_price += price
            self.close_price /= 2
        else:
            self.close_price = price
        self.updateCloseOrderID(close_order_id)
        self.updateState(InsightState.CLOSED)
        return self

    def getPL(self):
        assert self.close_price != None, 'Close price is not set'
        if self.side == 'long':
            return round((self.close_price - self.limit_price) * self.quantity, 2)
        else:
            return round((self.limit_price - self.close_price) * self.quantity, 2)

    def getPnLRatio(self):
        if self.TP and self.SL and self.limit_price != None:
            return round((abs(self.TP[-1] - self.limit_price)) / (abs(self.limit_price - self.SL)), 2)
        else:
            return 0

    def logPnL(self):
        PL = self.getPL()
        message = f"Trade Closed {"✅" if PL > 0 else "❌"}: {self.symbol} - {self.side} - {
            self.quantity} @ {self.close_price} - P/L: {PL} - UDA: {self.updatedAt}"
        return message

    def set_mode(self,  broker, mode: IStrategyMode = IStrategyMode.LIVE):
        self.MODE = mode
        self.BROKER = broker
        if self.MODE == IStrategyMode.BACKTEST:
            # update the created at to the current time in the simulation
            self.createAt = self.BROKER.get_current_time()
            self.updatedAt = self.createAt

        # check if the insight is valid except for manual or test insights
        if self.checkValidEntryInsight():
            print(f"Created Insight: {self.symbol} - {self.side} - {self.quantity} @ {self.limit_price} - TP: {
                  self.TP} - SL: {self.SL} - Ratio: {self.getPnLRatio()} - UDA: {self.updatedAt}")
        else:
            # print(f"Invalid Insight: {self.symbol} - {self.side} - {self.quantity} @ {self.limit_price} - TP: {self.TP} - SL: {self.SL} - Ratio: {self.getPnLRatio()} - UDA: {self.updatedAt}")
            self.updateState(InsightState.REJECTED, 'Invalid Entry Insight')

        return self
