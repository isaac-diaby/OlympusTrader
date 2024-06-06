from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional, TypedDict


class ISupportedBrokers(Enum):
    ALPACA = 'AlpacaBroker'
    PAPER = 'PapeVrokerr'
    BASE = 'BaseBroker'


class TradeUpdateEvent(Enum):
    NEW = 'new'
    PARTIALLY_FILLED = 'partially_filled'
    FILL = 'fill'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    CLOSED = 'closed'


class TimeInForce(Enum):
    DAY = 'day'
    GTC = 'gtc'
    OPG = 'opg'
    IOC = 'ioc'
    FOK = 'fok'


class OrderClass(Enum):
    # Simple Order - with no legs
    SIMPLE = 'simple'
    # Bracket Order - (otooco) # One Triggers One Cancels Other (Take Profit and Stop Loss)
    BRACKET = 'bracket'
    # One Cancels Other (Take Profit and Stop Loss) - on active order
    OCO = 'oco'
    # One Triggers Other (Take Profit or Stop Loss) - on active order
    OTO = 'oto'
    TRO = 'tro'  # Trailing Stop Order


class OrderType(Enum):
    MARKET = 'Market'
    LIMIT = 'Limit'
    STOP = 'Stop'
    STOP_LIMIT = 'Stop_limit'
    TRAILING_STOP = 'Trailing_stop'


class OrderSide(Enum):
    BUY = 'Long'
    SELL = 'Short'


class OrderRequest(TypedDict):
    symbol: str
    qty: float
    side: OrderSide
    type: OrderType
    time_in_force: TimeInForce
    limit_price: float
    order_class: OrderClass
    take_profit: float
    stop_loss: float
    trail_price: float


class Asset(TypedDict):
    _id: str
    name: str
    asset_type: Literal['stock', 'crypto']
    exchange: str
    symbol: str
    status: Literal['active', 'inactive']
    tradable: bool
    marginable: bool
    shortable: bool
    fractionable: bool
    min_order_size: float
    min_price_increment: float
    price_base: int = None

class IAccount(TypedDict):
    account_id: str
    cash: float
    currency: str
    buying_power: float
    shorting_enabled: bool

class IPosition(TypedDict):
    asset: Asset
    avg_entry_price: float
    qty: float
    side: OrderSide
    market_value: float
    cost_basis: float
    current_price: float
    unrealized_pl: float

class IOrderLeg(TypedDict):
    order_id: str
    limit_price: float
    filled_price: Optional[float]

class IOrderLegs(TypedDict):
    take_profit: Optional[IOrderLeg]
    stop_loss: Optional[IOrderLeg]
    trailing_stop: Optional[IOrderLeg]

class IOrder(TypedDict):
    order_id: str
    asset: Asset
    limit_price: float
    filled_price: Optional[float]
    stop_price: Optional[float]
    qty: float
    side: OrderSide
    type: OrderType
    time_in_force: TimeInForce
    status: TradeUpdateEvent
    order_class: OrderClass
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime #Timestamp when the order was submitted.
    filled_at: Optional[datetime] #Timestamp when the order was filled.
    legs: Optional[IOrderLegs]
    


class IAccountState(TypedDict):
    account: IAccount
    positions: dict[str, IPosition]
    orders: List[IOrder]

class TradeUpdate():
    def __init__(self, event: TradeUpdateEvent, order: IOrder):
        self.event = event
        self.order = order

    def __str__(self):
        return f'{self.event} - {self.symbol} - {self.qty} - {self.price} - {self.side} - {self.time}'
