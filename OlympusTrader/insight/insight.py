from datetime import datetime
from enum import Enum
from types import NoneType
from typing import List, Literal, TYPE_CHECKING, Optional, Self, Type, Union
from uuid import uuid4, UUID


from ..utils.timeframe import ITimeFrame
from ..broker.interfaces import IAsset, IOrderSide, IOrderType, IOrderClass, IOrderLegs, IOrderLeg
from ..strategy.interfaces import IStrategyMode


if TYPE_CHECKING:
    from ..broker.base_broker import BaseBroker


def get_BaseBroker():
    from ..broker.base_broker import BaseBroker
    return BaseBroker


class StrategyTypes(Enum):
    MANUAL = 'MANUAL'
    TEST = 'TESTING'


class StrategyDependantConfirmation(Enum):
    NONE = 'NONE'
    HRVCM = 'High Relative Volume Confirmation Model'
    LRVCM = 'Low Relative Volume Confirmation Model'
    HTFCM = 'High Time Frame Confirmation Model'
    LTFCM = 'Low Time Frame Confirmation Model'
    HCCM = 'High Confidence Confirmation Model'
    LCCM = 'Low Confidence Confirmation Model'
    UPSTATE = 'Up State Confirmation Model'
    DOWNSTATE = 'Down State Confirmation Model'
    FLATSTATE = 'Flat State Confirmation Model'


class InsightState(Enum):
    NEW = 'NEW'
    EXECUTED = 'EXECUTED'
    FILLED = 'FILLED'
    CLOSED = 'CLOSED'
    CANCELED = 'CANCELED'
    REJECTED = 'REJECTED'  # EXPIRED = 'EXPIRED'


class PartialCloseResult:
    order_id: str
    side: IOrderSide
    quantity: float
    entry_price: float
    filled_price: float

    def __init__(self, order_id: str, side: IOrderSide, quantity: float, price: float):
        self.order_id = order_id
        self.side = side
        self.quantity = quantity
        self.entry_price = price

    def __str__(self):
        return f"Partial Close: {self.order_id} - {self.quantity} @ {self.entry_price} - Filled At: {self.filled_price if self.filled_price else 'N/A'}"

    def set_filled_price(self, filled_price: float):
        self.filled_price = filled_price

    def getPL(self):
        assert self.filled_price != None, 'Filled price is not set'
        if self.side == IOrderSide.BUY:
            return round((self.filled_price - self.entry_price) * self.quantity, 2)
        else:
            return round((self.entry_price - self.filled_price) * self.quantity, 2)

class Insight:
    INSIGHT_ID: UUID
    """Unique Insight ID"""
    PARANT: Optional[UUID] = None
    """Parent Insight ID"""
    CHILDREN: dict[UUID, Self]
    
    order_id: str = None
    """Main Order ID for the Insight that entered the position"""
    side: IOrderSide = None  # buy or sell
    opposite_side: IOrderSide = None
    symbol: str = None  # symbol to trade
    quantity: Optional[float] = None  # quantity to trade
    type: IOrderType = None  # market, limit, stop, stop_limit, trailing_stop
    classType: IOrderClass = None  # simple, bracket, oco, oto
    limit_price: Optional[float] = None
    """Entry Price"""
    TP: Optional[List[float]] = None
    """Take profit levels - The last index is the final take profit level"""
    SL: Optional[float] = None
    """Stop loss level"""
    strategyType: Optional[Union[StrategyTypes, str]] = None  # strategy type
    confidence: float = None  # confidence in insight
    tf: ITimeFrame = None  # timeframe
    periodUnfilled: Optional[int] = None  # time to live when unfilled
    # predicted time to live when opened to reach take profit
    periodTillTp: Optional[int] = None
    executionDepends: List[StrategyDependantConfirmation] = [
        StrategyDependantConfirmation.NONE]  # execution depends on
    state: InsightState = InsightState.NEW
    """State of the Insight"""
    createAt: datetime = datetime.now()
    updatedAt: datetime = datetime.now()
    filledAt: Optional[datetime] = None
    closedAt: Optional[datetime] = None
    close_order_id = None
    """Close Order ID for the Insight that closed the position"""
    partial_closes: list[PartialCloseResult] = []
    legs: IOrderLegs = IOrderLegs(
        take_profit=None, stop_loss=None, trailing_stop=None)
    close_price: Optional[float] = None  # price to close at

    marketChanged: bool = False
    _cancelling: bool = False
    """Flag to check if the insight is being canceled"""
    _closing: bool = False
    """Flag to check if the insight is being closed"""
    _partial_filled_quantity: Optional[float] = None

    MODE: IStrategyMode = IStrategyMode.LIVE
    BROKER: get_BaseBroker = None
    ASSET: IAsset = None



    def __init__(self, side: IOrderSide, symbol: str,  strategyType: Union[StrategyTypes, str], tf: ITimeFrame, quantity: Optional[float] = 1, limit_price: Optional[float] = None, TP: Optional[List[float]] = None, SL: Optional[float] = None,  confidence: float = 0.1, executionDepends: List[StrategyDependantConfirmation] = [StrategyDependantConfirmation.NONE], periodUnfilled: int = 2, periodTillTp: int = 10,  parent: Optional[UUID] = None):
        assert side in IOrderSide, 'Invalid Order Side'
        self.INSIGHT_ID = uuid4()
        if parent:
            self.PARANT = parent  # Parent Insight ID
        self.CHILDREN = {}


        self.side = side  # buy or sell
        self.opposite_side = IOrderSide.BUY if (
            self.side == IOrderSide.SELL) else IOrderSide.SELL
        self.symbol = symbol  # symbol to trade
        self.quantity = quantity  # quantity to trade
        self.limit_price = limit_price  # price to enter at
        self.strategyType = strategyType  # strategy type
        # confidence in insight clamp between 0.01 and 1
        self.confidence = min(max(confidence, 0.01), 1)
        self.TP = TP  # take profit levels
        self.SL = SL  # stop loss
        self.tf = tf  # timeframe
        self.periodUnfilled = periodUnfilled  # time to live when unfilled
        # predicted time to live when opened to reach take profit
        self.periodTillTp = periodTillTp
        self.executionDepends = executionDepends  # execution depends on
        # self.state = InsightState.NEW
        # self.createAt = datetime.now()
        # self.updatedAt = datetime.now()

        if self.limit_price == None:
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

    def submit(self, rejectInvalid: bool = True, partialCloseInsight=None, closeInsight=False):

        if self.state == InsightState.NEW or self.state == InsightState.FILLED or self.state == InsightState.EXECUTED:
            try:
                if partialCloseInsight != None:
                    # Submit a partial close order
                    order = self.BROKER.execute_insight_order(
                        partialCloseInsight, self.ASSET)
                elif closeInsight:
                    # Submit a close order for the insight

                    #  check if the insight has a take profit or stop loss order leg that need to be canceled before closing the position
                    if self.takeProfitOrderLeg:
                        self.cancelTakeProfitLeg()
                    if self.stopLossOrderLeg:
                        self.cancelStopLossLeg()
                    order = self.BROKER.execute_insight_order(Insight(
                        self.opposite_side, self.symbol, StrategyTypes.MANUAL, self.tf, self.quantity), self.ASSET)

                else:
                    # Submit the insight to enter a position
                    order = self.BROKER.execute_insight_order(self, self.ASSET)

                if order:
                    if self.state == InsightState.NEW:
                        self.updateOrderID(
                            order['order_id'])
                        if order["legs"]:
                            self.updateLegs(order["legs"])
                        self.updateState(
                            InsightState.EXECUTED, f"Order ID: {order['order_id']}")

                    elif self.state == InsightState.FILLED:
                        # Add To Patial Close
                        if partialCloseInsight != None:
                            self.partial_closes.append(
                                PartialCloseResult(order['order_id'], self.side, partialCloseInsight.quantity, self.limit_price))
                            self.quantity -= partialCloseInsight.quantity
                        else:
                            # Close the position
                            self.updateCloseOrderID(order['order_id'])
                            # Strategy should handle the incoming closing of the position
                            # self.updateState(
                            #     InsightState.CLOSED, f"Close Order ID: {closeOrder['order_id']}")

                    return True
                else:
                    if self.state == InsightState.NEW:
                        self.updateState(
                            InsightState.REJECTED, 'Failed to place order')

            except BaseException as error:
                if self.state == InsightState.NEW:
                    self.updateState(InsightState.REJECTED, f"Error: {error}")
                else:
                    # Close function should handle the error if it was called by the close function
                    raise error

        else:
            print("Insight is not in a valid state to be submitted")
            if rejectInvalid:
                self.updateState(InsightState.REJECTED,
                                 'Invalid Entry Insight')

        return False

    def cancel_order_by_id(self, order_id: str):
        try:
            order = self.BROKER.cancel_order(order_id)
            if order:
                return order
            else:
                return False
        except BaseException as e:
            raise e

    def cancel(self):
        if self.state == InsightState.EXECUTED:
            try:
                if self._cancelling:
                    if self.state == InsightState.FILLED:
                        return False
                    return True
                order = self.cancel_order_by_id(self.order_id)
                if order:
                    self._cancelling = True
                    return True

            except BaseException as e:
                if e.args[0]["code"] == "already_filled":
                    self._cancelling = False
                    # self.updateState(InsightState.FILLED,
                    #                  'Already filled Trade')
                    # return True
                    return False
        if self.state == InsightState.NEW:
            self.updateState(InsightState.REJECTED, 'Before Executed Canceled')
            return True

        print("Insight is not in a valid state to be canceled", self.INSIGHT_ID)
        return False

    def close(self, quantity: Optional[float] = None, retry: bool = True, bypassStateCheck: bool = False):
        if (self.state == InsightState.FILLED or bypassStateCheck) and not self._closing:
            partialClose = False
            try:
                if quantity != None and self.quantity:
                    if quantity < self.quantity:
                        partialClose = True
                    else:
                        # Close 100% of the position if the quantity is greater than the insight's position size
                        quantity = self.quantity
                if partialClose == False:
                    # Close 100% of the position for this insight
                    closeOrder = self.submit(closeInsight=True)
                    if closeOrder:
                        self._closing = True
                        return True
                else:
                    closePartialOrder = self.submit(partialCloseInsight=Insight(
                        self.opposite_side, self.symbol, StrategyTypes.MANUAL, self.tf, quantity))
                    if closePartialOrder:
                        if self.TP:
                            self.TP.pop(0)  # Remove the first TP level
                        return True

            except BaseException as e:
                if e.args[0]["code"] == "insufficient_balance":
                    # '{"available":"0.119784","balance":"0.119784","code":40310000,"message":"insufficient balance for BTC (requested: 0.12, available: 0.119784)","symbol":"USD"}'
                    if e.args[0]["data"].get("balance") != None:
                        holding = float(e.args[0]["data"]["balance"])
                        if (holding > 0):
                            # Close 100% of the position
                            self.quantity = abs(holding)
                            # Retry closing the position once
                            if retry:
                                return self.close(retry=False)
                            else:
                                print(f"failed to close position: {
                                    holding} remaining!")
                        else:
                            # The position has already been closed as the balance is 0
                            self.updateState(
                                InsightState.CANCELED, f"No funds to close position")
        if not self._closing:
            print("Insight is not in a valid state to be closed", self.state)

        return False

    def addChildInsight(self, side: IOrderSide, quantity: Optional[float] = 1, limit_price: Optional[float] = None, TP: Optional[List[float]] = None, SL: Optional[float] = None, executionDepends: List[StrategyDependantConfirmation] = [StrategyDependantConfirmation.NONE], periodUnfilled: int = None, periodTillTp: int = None) -> Self:
        """Add a child insight to the parent insight. The child insight will be executed after the parent insight is filled."""
        childInsight =  Insight(
            parent=self.INSIGHT_ID, 
                       symbol=self.symbol,
                       strategyType=self.strategyType+'-CHILD',
                       tf=self.tf,
                       side=side,
                       quantity=quantity,
                       limit_price=limit_price,
                       TP=TP,
                       SL=SL,
                       confidence=self.confidence,
                       executionDepends=executionDepends,
                       periodUnfilled=periodUnfilled,
                       periodTillTp=periodTillTp,
                       )
        self.CHILDREN[childInsight.INSIGHT_ID] = childInsight
        return childInsight

    def updateState(self, state: InsightState, message: str = None):
        print(
            f"Updated Insight State: {self.state:^10} -> {state:^10}: {self.symbol:^8} : {self.strategyType} :", message)
        self.state = state
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        if self.state == InsightState.FILLED:
            if self._cancelling:
                self._cancelling = False
            self.filledAt = self.updatedAt
        if self.state == InsightState.CLOSED:
            self.closedAt = self.updatedAt
            # Print the P/L of the trade
            print(self.logPnL())

        return self

    def update_quantity(self, quantity: float):
        old_quantity = self.quantity
        self.quantity = quantity
        if self.checkValidQuantity():
            print(f"Updated quantity: {old_quantity} -> {self.quantity}")
            return True
        else:
            self.quantity = old_quantity
            return False

    def update_limit_price(self, price: float, updateToLimit: bool = False):
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
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time

        if updateToLimit:
            self.type = IOrderType.LIMIT

        # check if the insight is already executed
        if self.state == InsightState.EXECUTED:

            # TODO: update the broker order if the insight is already placed
            # TODO: Need to check if the order is already placed
            #  self.BROKER ....
            pass
        return True

    # TODO: def update_take_profit(self, price: float):
    #     if self.state == InsightState.FILLED:
    #         pass
    # TODO: def update_stop_loss(self, price: float):
    #     if self.state == InsightState.FILLED:
    #         pass
    def update_market_changed(self, marketChanged: bool, shouldCloseOrCancel: bool = False):
        self.marketChanged = marketChanged
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        if shouldCloseOrCancel:
            if self.state == InsightState.FILLED:
                if self.close():
                    return True
            else:
                if self.cancel():
                    return True
            # Failed to close or cancel the insight
            return False
        return True

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate the insight before submitting it to the broker."""
        cause = None
        # Skip the validation for manual and test insights
        if (self.strategyType == StrategyTypes.TEST or self.strategyType == StrategyTypes.MANUAL):
            return (True, None)

        if not self.checkValidEntryInsight():
            cause = 'Invalid Entry Insight'
            return (False, cause)
        if not self.checkIfCanShort(shouldUpdateState=False):
            cause = 'Short not allowed'
            return (False, cause)
        if self.state == InsightState.FILLED:
            if self.hasExhaustedTTL(shouldUpdateState=False):
                cause = 'Filled Time To Live expired'
                return (False, cause)
        else:
            if self.hasExpired(shouldUpdateState=False):
                cause = 'Unfilled Time To Live expired'
                return (False, cause)
        if not self.checkValidQuantity(shouldUpdateState=False):
            cause = 'Invalid Quantity'
            return (False, cause)

        if self.marketChanged:
            cause = 'Market has changed'
            return (False, cause)

        return (True, cause)

    def checkValidQuantity(self, shouldUpdateState: bool = False):
        # Check if quantity is invalid
        if self.quantity == None or self.ASSET['min_order_size'] > self.quantity:
            if shouldUpdateState:
                self.updateState(
                    InsightState.REJECTED, 'Invalid Quantity')
            return False
        return True

    def checkIfCanShort(self, shouldUpdateState: bool = False):
        """Check if the asset is shortable. If the asset is not shortable, the insight will be rejected."""
        # Skip the check if going long
        if self.side == IOrderSide.BUY:
            return True
        # Check if the asset is shortable
        if ((self.side == IOrderSide.SELL) and self.ASSET['shortable']):
            return True

        if shouldUpdateState:
            self.updateState(
                InsightState.REJECTED, f"Short not allowed")
        return False

    def checkValidEntryInsight(self, limit_price: float = None):
        """Check if the insight is valid. limitprice needs to be beween the take profit and stop loss."""
        if (self.strategyType == StrategyTypes.TEST or self.strategyType == StrategyTypes.MANUAL):
            return True  # skip the check for manual and test insights

        limit_price = limit_price if limit_price != None else self.limit_price
        # FIXME: use the broker to get the latest price and to check if the market order would be within range of the bracket order
        if limit_price == None:
            print("WARNING: invalid entry insight: limit price is not set, Using Market Order")
            return True

        if self.SL:
            if (limit_price < self.SL and self.side == IOrderSide.BUY) or (limit_price > self.SL and self.side == IOrderSide.SELL):
                print("invalid entry insight: limit price is below the stop loss")
                return False
        if self.TP:
            if len(self.TP) == 1:
                if (limit_price > self.TP[0] and self.side == IOrderSide.BUY) or (limit_price < self.TP[0] and self.side == IOrderSide.SELL):
                    print("invalid entry insight: limit price is below the take profit")
                    return False
            else:
                if self.side == IOrderSide.BUY:
                    self.TP.sort()
                else:
                    self.TP.sort(reverse=True)
                for tp in self.TP:
                    if (limit_price > tp and self.side == IOrderSide.BUY) or (limit_price < tp and self.side == IOrderSide.SELL):
                        print(
                            "invalid entry insight: limit price is above the take profit")
                        return False
        else:
            print("invalid entry insight: quantity is not set")
            return False

        return True

    def hasExpired(self, shouldUpdateState: bool = False) -> bool | None:
        """Check if the insight has expired. If the insight is not filled within the time to live period, it will be canceled. If the insight is filled, it will be closed after the time to live till take profit has expired."""
        if self.periodUnfilled == None:
            return False

        if self.state == InsightState.FILLED:
            # Insight has already been filled or canceled
            return None

        expireAt = self.tf.add_time_increment(
            self.createAt, self.periodUnfilled)
        hasExpired = expireAt < (datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time)

        if (self.state == InsightState.NEW or self.state == InsightState.EXECUTED) and hasExpired and shouldUpdateState:
            if self.state == InsightState.EXECUTED:
                if self.cancel():
                    pass
                    # self.updateState(InsightState.CANCELED,
                    #                  'Unfilled Time To Live expired')
            else:
                self.updateState(InsightState.REJECTED,
                                 'Expired before execution')

        return hasExpired

    def hasExhaustedTTL(self, shouldUpdateState: bool = False):
        if self.periodTillTp == None:
            return False

        if self.state != InsightState.FILLED:
            # Insight has not been filled yet
            return None

        expireAt = self.tf.add_time_increment(
            self.filledAt, self.periodTillTp)
        hasExpired = expireAt < (datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time)
        if (self.state == InsightState.FILLED) and hasExpired and shouldUpdateState:
            if self.close():
                # Close state switch should handled by the strategy
                # self.updateState(InsightState.CLOSED,
                #                  'Filled Time To Live expired')
                pass

        return hasExpired

    def updateOrderID(self, order_id: str):
        self.order_id = order_id
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    def updateCloseOrderID(self, close_order_id: str):
        self.close_order_id = close_order_id
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    def updateLegs(self, legs: IOrderLegs):
        """Update the order legs for the insight."""
        self.legs = legs
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    def updateTakeProfitLegs(self, leg: IOrderLeg):
        self.legs['take_profit'] = leg
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    @property
    def takeProfitOrderLeg(self):
        return self.legs.get('take_profit')

    def cancelTakeProfitLeg(self):
        if self.takeProfitOrderLeg:
            if self.cancel_order_by_id(self.takeProfitOrderLeg['order_id']):
                self.legs['take_profit'] = None
                self.updatedAt = datetime.now(
                ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
                return True
        return False

    def updateStopLossLegs(self, leg: IOrderLeg):
        self.legs['stop_loss'] = leg
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    @property
    def stopLossOrderLeg(self):
        return self.legs.get('stop_loss')

    def cancelStopLossLeg(self):
        if self.stopLossOrderLeg:
            if self.cancel_order_by_id(self.stopLossOrderLeg['order_id']):
                self.legs['stop_loss'] = None
                self.updatedAt = datetime.now(
                ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
                return True
        return False

    def updateTrailingStopLegs(self, leg: IOrderLeg):
        self.legs['trailing_stop'] = leg
        self.updatedAt = datetime.now(
        ) if self.MODE == IStrategyMode.LIVE else self.BROKER.get_current_time
        return self

    @property
    def trailingStopOrderLeg(self):
        return self.legs.get('trailing_stop')

    def positionFilled(self, price: float, qty: float, order_id: str = None):
        if order_id != None:
            self.updateOrderID(order_id)
        self.limit_price = price
        self.quantity = qty
        self.partialFilled(qty)
        self.updateState(InsightState.FILLED, f"Trade Filled: {
                         self.symbol} - {self.side} - {self.quantity} @ {self.limit_price}")
        return self

    def partialFilled(self, qty: float,):
        if self._partial_filled_quantity == None:
            self._partial_filled_quantity = 0
        if qty <= self.quantity:
            self._partial_filled_quantity = qty
            return self
        else:
            print(
                f"Partial Filled Quantity: {qty} is greater than the insight's position size: {self.quantity}")
            return

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

        # Close all of the child insights
        if self.PARANT == None and len(self.CHILDREN) > 0:
            for child in self.CHILDREN:
                childInsight = self.CHILDREN[child]
                if childInsight.state == InsightState.FILLED:
                    childInsight.close()
                elif childInsight.state == InsightState.EXECUTED:
                    childInsight.cancel()
                else: # childInsight.state == InsightState.NEW, InsightState.REJECTED, InsightState.CANCELED
                    childInsight.updateState(
                        InsightState.CANCELED, 'Parent Insight Closed')
        return self

    def getPL(self):
        assert self.close_price != None, 'Close price is not set'
        partialPL = 0
        if len(self.partial_closes) > 0:
            for partial in self.partial_closes:
                partialPL += partial.getPL()

        if self.side == IOrderSide.BUY:
            return round(((self.close_price - self.limit_price) * self.quantity) - partialPL, 2)
        else:
            return round(((self.limit_price - self.close_price) * self.quantity) - partialPL, 2)

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

    def set_mode(self, broker: get_BaseBroker, asset: IAsset, mode: IStrategyMode = IStrategyMode.LIVE):
        self.MODE = mode
        self.BROKER = broker
        self.ASSET = asset
        if self.MODE == IStrategyMode.BACKTEST:
            # update the created at to the current time in the simulation
            self.createAt = self.BROKER.get_current_time
            self.updatedAt = self.createAt

        if self.checkValidEntryInsight():
            print(f"Created Insight: {self}")
        else:
            self.updateState(InsightState.REJECTED, 'Invalid Entry Insight')

        return self
