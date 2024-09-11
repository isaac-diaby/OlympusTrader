
import os
from typing import Any, Union

from ccxt.base.exchange import Exchange
from ccxt.base.types import Order, OrderSide, Ticker
import pandas as pd

from OlympusTrader.broker.interfaces import IQuote
from OlympusTrader.insight.insight import Insight

from .base_broker import BaseBroker
from .interfaces import IAccount, IAsset, IOrder, IOrderLeg, IOrderLegs, IOrderSide, IOrderType, IPosition, ISupportedBrokers


class CCXTBroker(BaseBroker):
    """CCXT
    CCXT Broker.
    """

    exchange: Exchange
    """Yout CCXT Exchange. instance of ccxt.Exchange"""

    def __init__(self, exchange: Exchange,  paper: bool, feed=None):
        assert issubclass(
            type(exchange), Exchange), 'exchange must be a subclass of ccxt.Exchange'
        self.exchange = exchange
        if paper:
            if exchange.has['sandbox']:
                self.exchange.set_sandbox_mode(True)
            else:
                raise Exception(
                    'This exchange does not support sandbox mode', 'sandbox')
        super().__init__(f"{ISupportedBrokers.CCXT}_{
            self.exchange.id}", paper, feed)

    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
        try:
            if symbol in self.TICKER_INFO:
                return self.TICKER_INFO[symbol]

            # May want to also try  exchange.has['fetchMarkets']:
            if self.exchange.has['load_markets']:
                markets = self.exchange.load_markets()
                tickerInfo = markets[symbol]

                # CCXT doesnt really have stocks so we will just assume its a crypto
                tickerAsset: IAsset = IAsset(
                    id=tickerInfo['info']['id'],
                    symbol=tickerInfo['symbol'],
                    name=tickerInfo['info']['name'],
                    asset_type='crypto' if tickerInfo['info']['class'] == 'crypto' else 'stock',
                    exchange=tickerInfo['info']['exchange'],
                    status=tickerInfo['info']['status'],
                    tradable=tickerInfo['info']['tradable'],
                    marginable=tickerInfo['info']['marginable'],
                    shortable=tickerInfo['info']['shortable'],
                    fractionable=tickerInfo['info']['fractionable'],
                    min_order_size=tickerInfo['info']['min_order_size'],
                    min_price_increment=tickerInfo['info']['price_increment']
                )
                self.TICKER_INFO[symbol] = tickerAsset
                return tickerAsset
            else:
                raise Exception('This exchange does not support load_markets')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_account(self):
        try:
            if self.exchange.has['fetch_balance']:
                res = self.exchange.fetch_balance()
                account: IAccount = IAccount(account_id=res.id, equity=float(res.equity), cash=float(res.cash), currency=res.currency,
                                             buying_power=float(res.buying_power), leverage=float(res.multiplier), shorting_enabled=res.shorting_enabled)
            else:
                # TODO: Implement this for alpaca etc
                raise Exception('This exchange does not support fetch_balance')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_position(self, symbol: str):
        try:
            if self.exchange.has['fetch_position']:
                res = self.exchange.fetch_position(symbol)
                position: IPosition = IPosition(asset=self.get_ticker_info(symbol), avg_entry_price=float(res.avg_entry_price), qty=float(res.qty), side=res.side, market_value=float(
                    res.market_value), cost_basis=float(res.cost_basis), current_price=float(res.current_price), unrealized_pl=float(res.unrealized_pl))
            else:
                raise Exception(
                    'This exchange does not support fetch_position')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_position(self, position: Any) -> IPosition:
        try:
            return IPosition(
                asset=self.get_ticker_info(position.symbol),
                avg_entry_price=float(position.avg_entry_price),
                qty=float(position.qty),
                side=position.side.value,
                market_value=float(position.market_value),
                cost_basis=float(position.cost_basis),
                current_price=float(position.current_price),
                unrealized_pl=float(position.unrealized_pl)
            )
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_history(self, asset, start, end, resolution):
        try:
            if self.exchange.has['fetch_ohlcv']:
                history = self.exchange.fetch_ohlcv(
                    asset.symbol, resolution.value, start, end)
                return self.format_on_bar(history, asset.symbol)
            else:
                raise Exception('This exchange does not support fetch_ohlcv')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_on_bar(self, bar: Any, symbol: str) -> dict:
        # if bar is None:
        #     return None

        if isinstance(bar, list):
            pass
            # index = pd.MultiIndex.from_product(
            #     [[bar.symbol], [bar.timestamp]], names=['symbol', 'date'])
            # data = pd.DataFrame(data={
            #     'open': bar.open,
            #     'high': bar.high,
            #     'low': bar.low,
            #     'close': bar.close,
            #     'volume': bar.volume,
            # }, index=index, columns=['open', 'high', 'low', 'close', 'volume'])
        # data.set_index(['symbol', )], inplace=True)
            # return data
        elif bar is None:
            return None
        else:
            raise Exception('Cant format bar')

    def get_position(self, symbol: str):
        try:
            if self.exchange.has['fetch_position']:
                res = self.exchange.fetch_position(symbol)
                position: IPosition = IPosition(asset=self.get_ticker_info(symbol), avg_entry_price=float(res.avg_entry_price), qty=float(res.qty), side=res.side, market_value=float(
                    res.market_value), cost_basis=float(res.cost_basis), current_price=float(res.current_price), unrealized_pl=float(res.unrealized_pl))
            else:
                raise Exception(
                    'This exchange does not support fetch_position')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_positions(self):
        try:
            if self.exchange.has['fetch_positions']:
                res = self.exchange.fetch_positions()
                positions: dict[str, IPosition] = []
                for position in res:
                    positions.append(self.format_position(position))
                return positions
            else:
                raise Exception(
                    'This exchange does not support fetch_positions')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_position(self, position: Any) -> IPosition:
        print("Position:", position)
        pos = IPosition(
            asset=self.get_ticker_info(position.symbol),
            # avg_entry_price=float(position.avg_entry_price),
            # qty=float(position.qty),
            # side=position.side.value,
            # market_value=float(position.market_value),
            # cost_basis=float(position.cost_basis),
            # current_price=float(position.current_price),
            # unrealized_pl=float(position.unrealized_pl)
        )
        return pos

    def get_orders(self):
        try:
            if self.exchange.has['fetch_orders']:
                res = self.exchange.fetch_orders()
                orders: dict[str, IOrder] = []
                for order in res:
                    orders.append(self.format_order(order))
                return orders
            else:
                raise Exception(
                    'This exchange does not support fetch_orders')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_order(self, order_id: str):
        try:
            if self.exchange.has['fetch_order']:
                res = self.exchange.fetch_order(order_id)
                # position: IPosition = IPosition(asset=self.get_ticker_info(symbol), avg_entry_price=float(res.avg_entry_price), qty=float(res.qty), side=res.side, market_value=float(
                #     res.market_value), cost_basis=float(res.cost_basis), current_price=float(res.current_price), unrealized_pl=float(res.unrealized_pl))
            else:
                raise Exception(
                    'This exchange does not support fetch_order')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_order(self, order: Order) -> IOrder:
        try:
            if order is None:
                return None
            if isinstance(order, Order):
                legs = IOrderLegs()
                if order['takeProfitPrice']:
                    print(order['trades'])
                    legs["take_profit"] = IOrderLeg(
                        limit_price=order['takeProfitPrice'],
                        filled_price=None,
                        type=IOrderType.LIMIT,
                        status=None,
                        order_class=None,
                        created_at=None,
                        updated_at=None,
                        submitted_at=None,
                        filled_at=None
                    )
                if order['stopLossPrice']:
                    print(order['trades'])
                    legs["stop_loss"] = IOrderLeg(
                        limit_price=order['stopLossPrice'],
                        filled_price=None,
                        type=IOrderType.STOP,
                        status=None,
                        order_class=None,
                        created_at=None,
                        updated_at=None,
                        submitted_at=None,
                        filled_at=None
                    )
                return IOrder(
                    order_id=order["clientOrderId"],
                    asset=self.get_ticker_info(order["symbol"]),
                    side=IOrderSide.BUY if (
                        order["side"] == 'buy') else IOrderSide.SELL,
                    qty=float(order["amount"]),
                    type=order["type"],
                    order_class=order["trades"][0]["type"],
                    time_in_force=order["timeInForce"],
                    status=order["status"],
                    limit_price=float(order["price"]),
                    stop_price=float(order["stopPrice"]),
                    filled_price=float(order["average"]),
                    filled_qty=float(order["filled"]),
                    created_at=order["datetime"],
                    updated_at=order["lastUpdateTimestamp"],
                    filled_at=order["lastTradeTimestamp"],
                    submitted_at=order["timestamp"],
                    extra=order["info"],
                )
        except Exception as e:
            print(f"Error: {e}")
            return None
    def get_latest_quote(self, asset: IAsset) -> IQuote:
        if self.exchange.has['fetch_ticker']:
            res = self.exchange.fetch_ticker(asset.symbol)
            return IQuote(
                symbol=asset.symbol,
                ask=float(res['ask']),
                bid=float(res['bid']),
                last=float(res['last'])
            )
    def format_on_quote(self, quote: Ticker) -> IQuote:
        data =  IQuote(
            symbol=quote.symbol,
            ask=float(quote['ask']),
            ask_size=float(quote['askVolume']),
            bid=float(quote['bid']),
            bid_size=float(quote['bidVolume']),
            volume=float(quote['quoteVolume']),
            timestamp=quote['timestamp']
        )
        return data
    
    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        super().execute_insight_order(insight, asset)
        self.exchange.create