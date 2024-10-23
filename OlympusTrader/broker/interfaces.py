from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Literal, NotRequired, Optional, TypedDict, Union
from uuid import UUID

@dataclass
class ISupportedBrokerFeatures:
    """Supported Broker Features."""
    barDataStreaming: bool = True
    tradeEventStreaming: bool = True
    featuredBarDataStreaming: bool = True
    submitOrder: bool = True
    maxOrderValue: float = None
    cancelOrder: bool = True
    closePosition: bool = True
    getAccount: bool = True
    getPosition: bool = True
    getPositions: bool = True
    getHistory: bool = True
    getQuote: bool = True
    getTickerInfo: bool = True
    leverage: bool = True
    shorting: bool = True
    margin: bool = True
    bracketOrders: bool = True
    trailingStop: bool = True


class ISupportedBrokers(Enum):
    """Supported Brokers."""
    ALPACA = 'AlpacaBroker'
    CCXT = 'CCXTBroker'
    MT5 = 'MetaTrader5Broker'
    PAPER = 'PapeVrokerr'
    BASE = 'BaseBroker'


class ITradeUpdateEvent(Enum):
    """Trade Update Event."""
    ACCEPTED = 'accepted'
    NEW = 'new'
    PENDING_NEW = 'pending_new'
    PARTIAL_FILLED = 'partial_filled'
    FILLED = 'fill'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    CLOSED = 'closed'
    REPLACED = 'replaced'


class ITimeInForce(Enum):
    DAY = 'day'
    GTC = 'gtc'
    OPG = 'opg'
    IOC = 'ioc'
    FOK = 'fok'


class IOrderClass(Enum):
    # Simple Order - with no legs
    SIMPLE = 'simple'
    # Bracket Order - (otooco) # One Triggers One Cancels Other (Take Profit and Stop Loss)
    BRACKET = 'bracket'
    # One Cancels Other (Take Profit and Stop Loss) - on active order
    OCO = 'oco'
    # One Triggers Other (Take Profit or Stop Loss) - on active order
    OTO = 'oto'
    TRO = 'tro'  # Trailing Stop Order


class IOrderType(Enum):
    """Order Type."""
    MARKET = 'Market'
    LIMIT = 'Limit'
    STOP = 'Stop'
    STOP_LIMIT = 'Stop_limit'
    TRAILING_STOP = 'Trailing_stop'


class IOrderSide(Enum):
    """Order Side."""
    BUY = 'Long'
    SELL = 'Short'


class IOrderRequest(TypedDict):
    symbol: str
    qty: float
    side: IOrderSide
    type: IOrderType
    time_in_force: ITimeInForce
    limit_price: float
    order_class: IOrderClass
    take_profit: float
    stop_loss: float
    trail_price: float


class IAsset(TypedDict):
    id: str
    name: str
    asset_type: Literal['stock', 'crypto', 'forex']
    exchange: str
    symbol: str
    status: Literal['active', 'inactive']
    tradable: bool
    marginable: bool
    shortable: bool
    fractionable: bool
    min_order_size: float
    max_order_size: NotRequired[float]
    min_price_increment: float
    price_base: NotRequired[int]
    contract_size: NotRequired[int] # For futures and options contracts only (in the asset's base currency). else None

@dataclass
class IAccount():
    account_id: str
    equity: float
    cash: float
    currency: str
    buying_power: float
    shorting_enabled: bool
    leverage: float

class IPosition(TypedDict):
    asset: IAsset
    avg_entry_price: float
    qty: float
    side: IOrderSide
    market_value: float
    cost_basis: float
    current_price: float
    unrealized_pl: float

class IOrderLeg(TypedDict):
    order_id: str
    limit_price: float
    filled_price: Optional[float]
    type: IOrderType
    status: ITradeUpdateEvent
    order_class: IOrderClass
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime
    filled_at: Optional[datetime]

class IOrderLegs(TypedDict):
    take_profit: Optional[IOrderLeg]
    stop_loss: Optional[IOrderLeg]
    trailing_stop: Optional[IOrderLeg]

class IOrder(TypedDict):
    order_id: Union[str, UUID]
    asset: IAsset
    limit_price: float
    filled_price: Optional[float]
    stop_price: Optional[float]
    qty: float
    filled_qty: float
    side: IOrderSide
    type: IOrderType
    time_in_force: ITimeInForce
    status: ITradeUpdateEvent
    order_class: IOrderClass
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime #Timestamp when the order was submitted.
    filled_at: Optional[datetime] #Timestamp when the order was filled.
    legs: Optional[IOrderLegs]

class IQuote(TypedDict):
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    volume: float
    timestamp: datetime


class IAccountState(TypedDict):
    account: IAccount
    positions: dict[str, IPosition]
    orders: List[IOrder]

class ITradeUpdate():
    def __init__(self, order: IOrder, event: ITradeUpdateEvent):
        self.event = event
        self.order = order

    def __str__(self):
        return f'{self.event} - {self.order["asset"]["symbol"]} - {self.order["qty"]} - {self.order["side"]} - {self.order["updated_at"]}'
