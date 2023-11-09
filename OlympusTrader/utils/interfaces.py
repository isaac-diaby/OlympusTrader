from datetime import datetime
from typing import Literal, Optional, TypedDict, Required

from pandas import Timestamp
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
    side: Literal['long', 'short']
    market_value: float
    cost_basis: float
    current_price: float
    unrealized_pl: float

class IOrder(TypedDict):
    order_id: str
    asset: Asset
    limit_price: float
    filled_price: float
    stop_price: float
    qty: float
    side: Literal['long', 'short']
    type: Literal['market', 'limit', 'stop', 'stop_limit', 'trailing_stop']
    time_in_force: Literal['day', 'gtc', 'opg', 'ioc', 'fok']
    status: Literal['new', 'partially_filled', 'filled']
    order_class: Literal['simple', 'bracket', 'oco', 'oto']
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime #Timestamp when the order was submitted.
    filled_at:Optional[datetime] #Timestamp when the order was filled.


class IAccountState(TypedDict):
    account: IAccount
    positions: dict[str, IPosition]
    orders: [IOrder]



