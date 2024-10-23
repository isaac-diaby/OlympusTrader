from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any, Optional, Union

from ccxt.base.exchange import Exchange
from ccxt.base.types import Order, OrderSide, Ticker
import pandas as pd

from OlympusTrader.broker.interfaces import IQuote
from OlympusTrader.insight.insight import Insight

from .base_broker import BaseBroker
from .interfaces import IAccount, IAsset, IOrder, IOrderLeg, IOrderLegs, IOrderSide, IOrderType, IPosition, ISupportedBrokerFeatures, ISupportedBrokers, ITradeUpdate, ITradeUpdateEvent
import asyncio


class CCXTBroker(BaseBroker):
    """CCXT
    CCXT Broker.
    """

    exchange: Exchange
    """Yout CCXT Exchange. instance of ccxt.Exchange"""

    def __init__(self, exchange: Exchange,  paper: bool, feed=None):

        # FIXME: The broker is not yet supported by the broker manager
        # - considering not even using CCXT and just exchange rest api and websocket directly as we have custome implementations for each broker
        # - this will allow us to have more control over the broker and not rely on ccxt
        
        raise NotImplementedError("CCXT Broker is not yet supported by the broker manager")
    
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

            if self.exchange.has['fetchMarkets']:
                loop = asyncio.new_event_loop()
                markets = loop.run_until_complete(self.exchange.load_markets())
                # symbol = symbol.replace('-', '/')
                tickerInfo = markets.get(symbol)

                if not tickerInfo:
                    raise Exception(
                        'This exchange does not support the symbol', symbol)
            

                # CCXT doesnt really have stocks so we will just assume its a crypto
                tickerAsset: IAsset = IAsset(
                    id=tickerInfo['id'],
                    symbol=tickerInfo['symbol'],
                    name=tickerInfo['info']['fullName'],
                    asset_type='crypto',
                    exchange=self.exchange.id,
                    status="active" if tickerInfo['active'] else "inactive",
                    tradable=tickerInfo['active'],
                    marginable=tickerInfo['margin'],
                    shortable=True,
                    # shortable=tickerInfo['info']['shortable'],
                    fractionable=True,
                    # fractionable=tickerInfo['info']['fractionable'],
                    min_order_size=tickerInfo['limits']['amount']['min'],
                    min_price_increment=tickerInfo['precision']['price']
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
                account: IAccount = IAccount(account_id=str(res.id), equity=float(res.equity), cash=float(res.cash), currency=res.currency,
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

        if isinstance(bar, list[list]):
            # [timestamp, open, high, low, close, volume]?
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
        elif isinstance(bar, list[list]):
            # [[timestamp], [open], [high], [low], [close], [volume]]
            pass

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
            avg_entry_price=float(position.avg_entry_price),
            qty=float(position.qty),
            side=position.side.value,
            market_value=float(position.market_value),
            cost_basis=float(position.cost_basis),
            current_price=float(position.current_price),
            unrealized_pl=float(position.unrealized_pl)
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
                return self.format_order(res)
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
        try:
            if self.exchange.has['fetch_ticker']:
                res = self.exchange.fetch_ticker(asset.symbol)
                return IQuote(
                    symbol=asset.symbol,
                    ask=float(res['ask']),
                    bid=float(res['bid']),
                    last=float(res['last'])
                )
            else:
                raise Exception('This exchange does not support fetch_ticker')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_on_quote(self, quote: Ticker) -> IQuote:
        try:
            return IQuote(
                symbol=quote.symbol,
                ask=float(quote['ask']),
                ask_size=float(quote['askVolume']),
                bid=float(quote['bid']),
                bid_size=float(quote['bidVolume']),
                volume=float(quote['quoteVolume']),
                timestamp=quote['timestamp']
            )
        except Exception as e:
            print(f"Error: {e}")
            return None

    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        super().execute_insight_order(insight, asset)
        order_params = {
            'symbol': asset.symbol,
            'type': insight.type.value,
            'side':  'buy' if insight.side == IOrderSide.BUY else 'sell',
            'amount': insight.quantity,
            'params': {}
        }
        try:
            order_params['type'] = 'market' if insight.type == IOrderType.MARKET else 'limit'
            if insight.type == IOrderType.LIMIT:
                order_params['price'] = insight.limit_price

            if insight.type == IOrderType.STOP or insight.type == IOrderType.STOP_LIMIT:
                order_params['params']['stopPrice'] = insight.limit_price
            else:
                if insight.TP and insight.SL and self.exchange.has['createOrderWithTakeProfitAndStopLoss']:
                    order_params['params'] = self.exchange.set_take_profit_and_stop_loss_params(
                        symbol=asset.symbol, side=order_params['side'], amount=order_params['amount'], price=order_params['price'], takeProfit=insight.TP[-1], stopLoss=insight.SL, params=order_params['params'])

                elif insight.TP:
                    assert self.exchange.has['createTakeProfitOrder'], 'This exchange does not support createTakeProfitOrder'
                    order_params['params']['takeProfitPrice'] = insight.TP[-1]
                elif insight.SL:
                    assert self.exchange.has['createStopLossOrder'], 'This exchange does not support createStopLossOrder'
                    order_params['params']['stopLossPrice'] = insight.SL
        except Exception as e:
            print(f"Error composing order: {e}")
            return None
        try:
            order = self.exchange.create_order(**order_params)
            return self.format_order(order)
        except Exception as e:
            print(f"Error sending order: {e}")
            raise e

    def cancel_order(self, order_id: str):
        try:
            if self.exchange.has['cancelOrder']:
                cancelled_order = self.exchange.cancel_order(order_id)
                return self.format_order(cancelled_order)
            else:
                raise Exception('This exchange does not support cancelOrder')
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return None

    def close_all_positions(self):
        # close all positions
        self.exchange.close_all_positions()
        pass

    def close_position(self, symbol: str, qty=None, percent=None):
        # Implement logic to close a specific position
        raise NotImplementedError()
        pass

    def format_on_trade_update(self, trade: Union[ITradeUpdate, Any]):
        if isinstance(trade, ITradeUpdate):
            return super().format_on_trade_update(trade)
        event: ITradeUpdateEvent = None
        match trade['status']:
            case 'open':
                event = ITradeUpdateEvent.NEW
            case 'closed':
                event = ITradeUpdateEvent.FILLED
            case 'canceled':
                event = ITradeUpdateEvent.CANCELED
            case 'rejected':
                event = ITradeUpdateEvent.REJECTED
            case 'expired':
                event = ITradeUpdateEvent.EXPIRED
        return self.format_order(trade.order), event

    def startTradeStream(self, callback):
        # Implement logic to start trade stream
        super().startTradeStream(callback)
        self.RUNNING_TRADE_STREAM = True
        while self.RUNNING_TRADE_STREAM:
            if self.exchange.has['watchMyTradesForSymbols']:
                trades = self.exchange.watch_my_trades_for_symbols(
                    self.TICKER_INFO.keys())
            elif self.exchange.has['watchMyTrades']:
                for symbol in self.TICKER_INFO.keys():
                    trades = self.exchange.watch_my_trades(symbol)
            for trade in trades:
                tradeUpdate = self.format_on_trade_update(trade)
                if tradeUpdate:
                    callback(tradeUpdate)

    def streamMarketData(self, callback, assetStreams):
        super().streamMarketData(callback, assetStreams)
        barStreamCount = len(
            [asset for asset in assetStreams if asset['type'] == 'bar'])

        pool = ThreadPoolExecutor(max_workers=(
            barStreamCount), thread_name_prefix="MarketDataStream")
        loop = asyncio.new_event_loop()

        self.RUNNING_MARKET_STREAM = True
        while self.RUNNING_MARKET_STREAM:

            for assetStream in assetStreams:
                match assetStream['type']:
                    case 'bar':
                        async def streamBarDataHandler(assetStream, callback):
                            while self.RUNNING_MARKET_STREAM:
                                barData = self.format_on_bar(await self.exchange.watch_ohlcv(assetStream['symbol'], assetStream['time_frame']))
                                timestamp = barData.index[0][1]
                                if assetStream['time_frame'].is_time_increment(timestamp):
                                    await callback(barData, timeframe=assetStream['time_frame'])
                        # self.exchange.watch_ohlcv(assetStream['symbol'], assetStream['time_frame'])
                        pool.submit(streamBarDataHandler,
                                    assetStream, callback)

                    # case 'quote':
                    #     pool.submit(self.streamQuoteData, assetStream, callback)
                    # case 'trade':
                    #     pool.submit(self.streamTradeData, assetStream, callback)
                    case _:
                        pass

        pass

    async def closeStream(self, assetStreams):
        # Implement logic to close market data stream
        self.RUNNING_MARKET_STREAM = False

    async def closeTradeStream(self):
        # Implement logic to close trade stream
        self.RUNNING_TRADE_STREAM = False
