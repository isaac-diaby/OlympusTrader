import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import datetime
from time import sleep
from types import NoneType
import uuid
import numpy as np
from typing import Awaitable, List, Literal
from collections import deque
from threading import Barrier, BrokenBarrierError
from concurrent.futures import as_completed
from pathlib import Path


import pandas as pd

from .base_broker import BaseBroker
from .interfaces import IQuote, ITimeInForce, ISupportedBrokers, IOrderClass, IOrderRequest, IOrderSide, IOrderType, ITimeInForce, ITradeUpdate, ITradeUpdateEvent
from ..insight.insight import Insight
from .interfaces import IAccount, IOrder, IPosition, IAsset, IOrderLegs, IOrderLeg
from ..strategy.interfaces import IMarketDataStream, IStrategyMode
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit


import yfinance as yf


class PaperBroker(BaseBroker):
    MODE: IStrategyMode = IStrategyMode.BACKTEST

    ACCOUNT: IAccount = None
    Positions: dict[str, IPosition] = {}
    Orders: dict[str, IOrder] = {}
    LEVERAGE: int = 4

    # Backtest mode
    STARTING_CASH: float = 100_000.00
    START_DATE: datetime.date = None
    END_DATE: datetime.date = None
    CurrentTime: datetime.date = None
    PreviousTime: datetime.date = None
    HISTORICAL_DATA: dict[str, dict[Literal['trade',
                                            'quote', 'bar', 'news'], pd.DataFrame]] = {}
    RUNNING_TRADE_STREAM: bool = False
    RUNNING_MARKET_STREAM: bool = False
    BACKTEST_FlOW_CONTROL_BARRIER: Barrier = None

    PENDING_ORDERS: deque[IOrder] = deque()
    ACTIVE_ORDERS: deque[IOrder] = deque()
    CLOSE_ORDERS: deque[IOrder] = deque()
    CANCELED_ORDERS: deque[IOrder] = deque()

    ACCOUNT_HISTORY: dict[datetime.date, IAccount] = {}

    FeedDelay: int = 0


    def __init__(self, cash: float = 100_000.00, start_date: datetime.date = None, end_date: datetime.date = None, leverage: int = 4, currency: str = "GBP", allow_short: bool = True, mode: IStrategyMode = IStrategyMode.BACKTEST, feed: Literal['yf', 'eod'] = 'yf', feedDelay: int = 0):

        super().__init__(ISupportedBrokers.PAPER, True, feed)
        self.MODE = mode
        self.LEVERAGE = leverage
        self.STARTING_CASH = cash
        self.ACCOUNT = IAccount(account_id='PAPER_ACCOUNT', equity=self.STARTING_CASH, cash=self.STARTING_CASH, currency=currency,
                                buying_power=cash*self.LEVERAGE, leverage=self.LEVERAGE, shorting_enabled=allow_short)

        # Set the backtest configuration
        if self.MODE == IStrategyMode.BACKTEST:
            assert start_date and end_date, 'Start and End date must be provided for backtesting'
            assert start_date < end_date, 'Start date must be before end date'
            # self.START_DATE = start_date.replace(tzinfo=datetime.timezone.utc)
            self.START_DATE = start_date
            self.END_DATE = end_date
            self.CurrentTime = self.START_DATE
            self.update_account_history()
            self.BACKTEST_FlOW_CONTROL_BARRIER = Barrier(3)
            # self.BACKTEST_FlOW_CONTROL_BARRIER.reset()
        else:
            self.FeedDelay = feedDelay
            self.CurrentTime = datetime.datetime.now(
            ) - datetime.timedelta(minutes=self.FeedDelay)

    def get_ticker_info(self, symbol: str):
        if symbol in self.TICKER_INFO:
            return self.TICKER_INFO[symbol]

        if self.DataFeed == 'yf':
            symbol = symbol.replace('/', '-')
            yfRes = yf.Ticker(symbol)
            if not yfRes:
                return None
            tickerInfo = yfRes.info

            tickerAsset: IAsset = IAsset(
                id=tickerInfo['uuid'],
                name=tickerInfo['shortName'],
                asset_type=tickerInfo["quoteType"],
                exchange=tickerInfo["exchange"],
                symbol=tickerInfo["symbol"],
                status="active",
                tradable=True,
                marginable=True,
                shortable=self.Account['shorting_enabled'],
                fractionable=True,
                min_order_size=0.001,
                min_price_increment=1 /
                np.power(10, tickerInfo["priceHint"]
                         ) if "priceHint" in tickerInfo else 0.01
            )
            self.TICKER_INFO[symbol] = tickerAsset
            return tickerAsset
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')


    def get_history(self, asset: IAsset, start: datetime.datetime, end: datetime.datetime, resolution: ITimeFrame, shouldDelta: bool = True) -> pd.DataFrame:
        super().get_history(asset, start, end, resolution)

        if self.DataFeed == 'yf':
            symbol = asset['symbol'].replace('/', '-')
            formatTF = f'1{resolution.unit.value[0].lower()}'
            if self.MODE == IStrategyMode.BACKTEST:
                delta: datetime.timedelta = start - \
                    self.get_current_time if shouldDelta else datetime.timedelta()
                # print("start: ", self.get_current_time-start, "end: ", self.get_current_time-end)
                data = yf.download(
                    symbol, start=resolution.get_time_increment(start-delta), end=resolution.get_time_increment(end-delta), interval=formatTF)
            else:
                data = yf.download(
                    symbol, start=start, end=end, interval=formatTF)

            return self.format_on_bar(data, asset['symbol'])
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def get_account(self):
        return self.Account

    def get_position(self, symbol):
        return self.Positions.get(symbol)

    def get_positions(self):
        return self.Positions

    def get_orders(self):
        # active orders
        returned_orders: dict[str, IOrder] = {}
        active_orders = [order for order in self.Orders.values() if order['status'] == ITradeUpdateEvent.NEW or order['status'] == ITradeUpdateEvent.FILLED]
        if len(active_orders) == 0:
            return None
        for order in active_orders:
            returned_orders[order['order_id']] = order

        return returned_orders

    def get_order(self, order_id):
        return self.Orders.get(order_id)

    def close_order(self, order_id: str):
        order = self.Orders.get(order_id)
        if order:
            if order['status'] == ITradeUpdateEvent.FILLED:
                raise BaseException({
                    "code": "already_filled",
                    "data": {"order_id": order_id}
                })
            elif order['status'] == ITradeUpdateEvent.CANCELED:
                raise BaseException({
                    "code": "already_canceled",
                    "data": {"order_id": order_id}
                })
            else:

                # order['status'] = ITradeUpdateEvent.CANCELED
                order['updated_at'] = self.get_current_time
                self.CANCELED_ORDERS.append(order)
                return order
        else:
            raise BaseException({
                "code": "order_not_found",
                "data": {"order_id": order_id}
            })

    def get_latest_quote(self, asset: IAsset) -> IQuote:
        # FIXME: Temp: Get the latest quote at bar close and bid ask spread at is high and low
        if self.DataFeed == 'yf':
            currentBar = self._get_current_bar(
                asset['symbol']).iloc[0]
            quote = self.format_on_quote(currentBar)
            quote['symbol'] = asset['symbol']
            return quote

        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def startTradeStream(self, callback):
        super().startTradeStream(callback)
        self.RUNNING_TRADE_STREAM = True
        loop = asyncio.new_event_loop()
        if self.MODE == IStrategyMode.BACKTEST:
            # TODO: trade stream for all of the pending, filled, canceled oerders.
            while self.get_current_time <= self.END_DATE and self.RUNNING_TRADE_STREAM:
                try:
                    self.BACKTEST_FlOW_CONTROL_BARRIER.wait()
                    # print("pending: ", len(self.PENDING_ORDERS),
                    #       "active: ", len(self.ACTIVE_ORDERS),
                    #       "closed: ", len(self.CLOSE_ORDERS),
                    #       "canceled: ", len(self.CANCELED_ORDERS))
                    self.processPendingOrders(callback, loop)
                    self.processActiveOrders(callback, loop)
                    self.processClosedOrders(callback, loop)
                    self.processCanceledOrders(callback, loop)

                except BrokenBarrierError:
                    continue
                except Exception as e:
                    print("Error: ", e)
                    continue
            print("End of Trade Stream")

        else:
            # live trade stream
            try:
                while self.RUNNING_TRADE_STREAM:
                    self.processPendingOrders(callback, loop)
                    self.processActiveOrders(callback, loop)
                    self.processClosedOrders(callback, loop)
                    self.processCanceledOrders(callback, loop)
                    sleep(2)
            except Exception as e:
                print("Error: ", e)

    def processPendingOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.PENDING_ORDERS)):
            currentBar = self._get_current_bar(
                order['asset']['symbol'])
            if currentBar is None:
                continue
            currentBar = currentBar.iloc[0]

            if order['created_at'] == self.get_current_time:
                order['status'] = ITradeUpdateEvent.NEW
                self._update_order(order)
                loop.run_until_complete(
                    callback(ITradeUpdate(order, order['status'])))

            if order['type'] == IOrderType.MARKET:
                # Market order - FILLED at the current close price
                order['filled_price'] = currentBar.open

                order['status'] = ITradeUpdateEvent.FILLED
                order['filled_at'] = self.get_current_time
                order['updated_at'] = self.get_current_time
                # update buying power difference
                bp_change = (order['qty'] *
                             order['limit_price']) - (order['qty'] *
                                                      order['filled_price'])
                if (self.Account['buying_power'] - bp_change) < 0:
                    # cant afford the new price
                    order['status'] = ITradeUpdateEvent.REJECTED
                    self._update_order(order)
                    loop.run_until_complete(callback(ITradeUpdate(
                        order, order['status'])))
                    continue

                self.Account['cash'] -= np.round(
                    bp_change/self.LEVERAGE, 2)
                order['filled_qty'] = order['qty']
                self._update_order(order)
                loop.run_until_complete(callback(ITradeUpdate(
                    order, order['status'])))
                continue

            elif order['type'] == IOrderType.LIMIT:
                if order['limit_price'] >= currentBar.low and order['limit_price'] <= currentBar.high:
                    order['filled_price'] = order['limit_price']
                    order['filled_qty'] = order['qty']
                    order['status'] = ITradeUpdateEvent.FILLED
                    order['filled_at'] = self.get_current_time
                    order['updated_at'] = self.get_current_time
                    self._update_order(order)
                    loop.run_until_complete(callback(ITradeUpdate(
                        order, order['status'])))
                    continue

    def processActiveOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.ACTIVE_ORDERS)):
            # update the position information as the position is filled and keep track of all  positions PNL
            self._update_position(order['asset']['symbol'])

            currentBar = self._get_current_bar(
                order['asset']['symbol'])
            if currentBar is None:
                continue
            currentBar = currentBar.iloc[0]

            # check if the order has take profit or stop loss
            if order['legs']:
                # FIXME: Figure out if the take profit or stop loss is hit first

                if order['legs']['take_profit']:
                    take_profit = order['legs']['take_profit']
                    if take_profit['limit_price'] >= currentBar.low and take_profit['limit_price'] <= currentBar.high:
                        take_profit['filled_price'] = take_profit['limit_price']
                        take_profit['status'] = ITradeUpdateEvent.CLOSED
                        take_profit['filled_at'] = self.get_current_time
                        take_profit['updated_at'] = self.get_current_time

                        order['stop_price'] = take_profit['limit_price']
                        order['updated_at'] = self.get_current_time
                        order['status'] = take_profit['status']
                        order['legs']['take_profit'] = take_profit

                        self._update_order(order)
                        self._update_position(
                            order['asset']['symbol'], take_profit['filled_price'])

                        loop.run_until_complete(callback(ITradeUpdate(
                            order, order['status'])))
                        continue
                elif order['legs']['stop_loss']:
                    stop_loss = order['legs']['stop_loss']
                    if stop_loss['limit_price'] >= currentBar.low and stop_loss['limit_price'] <= currentBar.high:
                        stop_loss['filled_price'] = stop_loss['limit_price']
                        stop_loss['status'] = ITradeUpdateEvent.CLOSED
                        stop_loss['filled_at'] = self.get_current_time
                        stop_loss['updated_at'] = self.get_current_time

                        order['stop_price'] = stop_loss['limit_price']
                        order['updated_at'] = self.get_current_time
                        order['status'] = stop_loss['status']
                        order['legs']['stop_loss'] = stop_loss

                        self._update_order(order)
                        self._update_position(
                            order['asset']['symbol'], stop_loss['filled_price'])

                        loop.run_until_complete(callback(ITradeUpdate(
                            order,  order['status'])))
                        continue
            else:
                # USually a market order or limit order without take profit or stop loss
                continue

    def processClosedOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.CLOSE_ORDERS)):
            # update the position information as the position is filled and keep track of all  positions PNL
            self._update_position(order['asset']['symbol'])

            currentBar = self._get_current_bar(
                order['asset']['symbol'])
            if currentBar is None:
                continue
            currentBar = currentBar.iloc[0]

            order['stop_price'] = currentBar.open
            order['status'] = ITradeUpdateEvent.CLOSED
            order['filled_at'] = self.get_current_time
            order['updated_at'] = self.get_current_time
            self._update_order(order)
            self._update_position(
                order['asset']['symbol'], order['stop_price'])
            loop.run_until_complete(callback(ITradeUpdate(
                order, order['status'])))

    def processCanceledOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.CANCELED_ORDERS)):
            order['status'] = ITradeUpdateEvent.CANCELED
            order['updated_at'] = self.get_current_time
            self._update_order(order)
            loop.run_until_complete(callback(ITradeUpdate(
                order, order['status'])))

    async def closeTradeStream(self):
        self.RUNNING_TRADE_STREAM = False
        # if self.MODE == IStrategyMode.BACKTEST:
        # else:
        #     raise NotImplementedError(f'Mode {self.MODE} not supported')

    def _update_position(self, symbol: str, close_price: float = None):
        currentBar = self._get_current_bar(symbol)
        currentBar = currentBar.iloc[0]
        oldPosition = self.Positions[symbol].copy()
        self.Positions[symbol]['current_price'] = currentBar.close if not close_price else close_price

        if self.Positions[symbol]['qty'] != 0:
            self.Positions[symbol]['market_value'] = self.Positions[symbol]['current_price'] * \
                np.abs(self.Positions[symbol]['qty']
                       )  # qunaity can be negative for short positions
            self.Positions[symbol]['unrealized_pl'] = self.Positions[symbol]['market_value'] - \
                self.Positions[symbol]['cost_basis']
            changeInPL = round(self.Positions[symbol]['unrealized_pl'] -
                               oldPosition['unrealized_pl'], 2)
            self.Account['cash'] += changeInPL
        else:
            # self.Positions[symbol]['market_value']
            self.Account['cash'] += np.round(self.Positions[symbol]
                                             ['market_value'] / self.LEVERAGE, 2)
            # TODO: Later we can remove the position from the Positions dictionary
            # del self.Positions[symbol]
        # print("Updated Position: ",
        #       self.Positions[symbol], self.Account['cash'], self.Account['buying_power'])

    def _update_order(self, order: IOrder):
        if self.Orders.get(order['order_id']):
            oldOrder = self.Orders[order['order_id']].copy()
        else:
            oldOrder = None

        match order['status']:
            case ITradeUpdateEvent.NEW:
                if not oldOrder:
                    self.PENDING_ORDERS.append(order)

            case ITradeUpdateEvent.FILLED:
                if oldOrder['status'] == order['status']:
                    if oldOrder in self.PENDING_ORDERS:
                        self.PENDING_ORDERS.remove(oldOrder)
                        if self.Positions.get(order['asset']['symbol']):
                            # position already exists
                            self._update_position(order['asset']['symbol'])
                            if order['side'] == IOrderSide.BUY:
                                self.Positions[order['asset']
                                               ['symbol']]['qty'] += order['qty']
                            else:
                                self.Positions[order['asset']
                                               ['symbol']]['qty'] -= order['qty']
                            if self.Positions[order['asset']
                                              ['symbol']]['qty'] > 0:
                                self.Positions[order['asset']
                                               ['symbol']]['side'] = IOrderSide.BUY
                            else:
                                self.Positions[order['asset']
                                               ['symbol']]['side'] = IOrderSide.SELL

                            self.Positions[order['asset']
                                           ['symbol']]['avg_entry_price'] = (self.Positions[order['asset']
                                                                                            ['symbol']]['avg_entry_price'] + order['filled_price']) / 2
                            self.Positions[order['asset']
                                           ['symbol']]['market_value'] = (self.Positions[order['asset']
                                                                                         ['symbol']]['market_value'] + order['filled_price'] * order['qty']) / 2
                            self.Positions[order['asset']
                                           ['symbol']]['cost_basis'] = self.Positions[order['asset']
                                                                                      ['symbol']]['market_value']
                            self._update_position(order['asset']['symbol'])
                        else:
                            # add positions dictionary
                            self.Positions[order['asset']['symbol']] = IPosition(
                                asset=order['asset'],
                                avg_entry_price=order['filled_price'],
                                qty=order['qty'],
                                side=order['side'],
                                market_value=order['filled_price'] *
                                order['qty'],
                                cost_basis=order['filled_price'] *
                                order['qty'],
                                current_price=order['filled_price'],
                                unrealized_pl=0
                            )
                    # Add the order to the active orders
                    if self.Positions[order['asset']['symbol']]['qty'] != 0:
                        self.ACTIVE_ORDERS.append(order)

            case ITradeUpdateEvent.CANCELED:
                if (oldOrder['status'] == ITradeUpdateEvent.NEW) or (oldOrder in self.PENDING_ORDERS):
                    self.PENDING_ORDERS.remove(oldOrder)
                elif oldOrder['status'] == ITradeUpdateEvent.FILLED:
                    raise BaseException({
                        "code": "already_filled",
                        "data": {"symbol": order['asset']['symbol']}
                    })
                # if oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                if oldOrder in self.CANCELED_ORDERS:
                    self.CANCELED_ORDERS.remove(oldOrder)

                # Clear buying power wwithheld by the order
                self.Account['cash'] += np.round(
                    (order['qty'] * order['limit_price']) / self.LEVERAGE, 2)

            case ITradeUpdateEvent.CLOSED:
                if oldOrder:
                    if oldOrder['status'] == ITradeUpdateEvent.FILLED and oldOrder in self.ACTIVE_ORDERS:
                        self.ACTIVE_ORDERS.remove(oldOrder)
                    elif oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                        self.CANCELED_ORDERS.remove(oldOrder)
                    if order['side'] == IOrderSide.BUY:
                        self.Positions[order['asset']
                                       ['symbol']]['qty'] -= order['qty']
                    else:
                        self.Positions[order['asset']
                                       ['symbol']]['qty'] += order['qty']

                    # Clear buying power wwithheld by the order
                    # self.Account['buying_power'] += order['qty'] * order['limit_price']

                    self._update_position(order['asset']['symbol'])
                else:
                    raise BaseException({
                        "code": "order_not_found",
                        "data": {"order_id": order['order_id']}
                    })
            case _:
                pass

        self.Orders[order['order_id']] = order

    def execute_insight_order(self, insight: Insight, asset: IAsset):
        super().execute_insight_order(insight, asset)
        orderRequest: IOrderRequest = {
            "symbol": insight.symbol,
            "qty": insight.quantity,
            "side": IOrderSide.BUY if insight.side == 'long' else IOrderSide.SELL,
            "time_in_force": ITimeInForce.GTC,
            "order_class": IOrderClass.SIMPLE
        }
        if insight.TP and insight.SL:
            orderRequest["order_class"] = IOrderClass.BRACKET
            orderRequest["take_profit"] = insight.TP[-1]
            orderRequest["stop_loss"] = insight.SL
        elif insight.TP:
            orderRequest["order_class"] = IOrderClass.OTO
            orderRequest["take_profit"] = insight.TP[-1]
        elif insight.SL:
            orderRequest["order_class"] = IOrderClass.OTO
            orderRequest["stop_loss"] = insight.SL
        if insight.limit_price:
            orderRequest["limit_price"] = insight.limit_price

        if insight.type in IOrderType:
            orderRequest["type"] = insight.type
        else:
            print(f"Order Type not supported {insight.type}")
            return
        try:
            if orderRequest:
                # submit the new order to be executed in the next tick
                order = self._submit_order(orderRequest)
                return order

                # if self.MODE == IStrategyMode.BACKTEST:
                # else:
                #     raise NotImplementedError(
                #         f'Mode {self.MODE} not supported')

        except BaseException as e:
            raise e

    def _submit_order(self, orderRequest: IOrderRequest) -> IOrder:
        # check if the buying power is enough to place the order

        if orderRequest['type'] == IOrderType.MARKET:
            currentBar = self._get_current_bar(
                orderRequest['symbol'])
            currentBar = currentBar.iloc[0]
            orderRequest['limit_price'] = currentBar.close

        marginRequired = orderRequest['qty'] * orderRequest['limit_price']
        buying_power = self.Account["buying_power"]

        # Account for the market value of the position if the order is in the opposite direction
        if self.Positions.get(orderRequest['symbol']):
            if (orderRequest['side'] == IOrderSide.SELL and self.Positions.get(orderRequest['symbol'])['qty'] < 0) or \
                    (orderRequest['side'] == IOrderSide.BUY and self.Positions.get(orderRequest['symbol'])['qty'] > 0):
                buying_power += self.Positions[orderRequest['symbol']
                                               ]['market_value']

        if buying_power < marginRequired:
            raise BaseException({
                "code": "insufficient_balance",
                "data": {"symbol": orderRequest['symbol'],
                         "requires": marginRequired,
                         "available": self.Account["buying_power"],
                         "message": "Insufficient balance to place the order"}
            })
        # check if the orderRequest is valid
        # TP and SL should already be greater or less than the limit price depending on the side and  quantity based on Insight class logic
        if orderRequest['qty'] == None or orderRequest['qty'] <= 0:
            raise BaseException({
                "code": "invalid_order",
                "data": {"symbol": orderRequest['symbol'],
                         "message": "Order quantity must be greater than 0"}
            })
        if (orderRequest['type'] == IOrderType.LIMIT or orderRequest['type'] == IOrderType.STOP_LIMIT) and not orderRequest['limit_price']:
            raise BaseException({
                "code": "invalid_order",
                "data": {"symbol": orderRequest['symbol'],
                         "message": "Limit price must be provided for limit order"}
            })

        # Set up the order legs
        legs = IOrderLegs()
        if orderRequest.get('take_profit'):
            legs["take_profit"] = IOrderLeg(
                order_id=uuid.uuid4(), limit_price=orderRequest['take_profit'], filled_price=None, status=ITradeUpdateEvent.NEW, filled_at=None, created_at=self.get_current_time, updated_at=self.get_current_time, submitted_at=self.get_current_time)

        if orderRequest.get('stop_loss'):
            legs["stop_loss"] = IOrderLeg(
                order_id=uuid.uuid4(), limit_price=orderRequest['stop_loss'], filled_price=None, status=ITradeUpdateEvent.NEW, filled_at=None, created_at=self.get_current_time, updated_at=self.get_current_time, submitted_at=self.get_current_time)
        if orderRequest.get('trail_price'):
            legs["trailing_stop"] = IOrderLeg(
                order_id=uuid.uuid4(), limit_price=orderRequest['trail_price'], filled_price=None, status=ITradeUpdateEvent.NEW, filled_at=None, created_at=self.get_current_time, updated_at=self.get_current_time, submitted_at=self.get_current_time)

        order = IOrder(
            order_id=uuid.uuid4(),
            asset=self.get_ticker_info(orderRequest['symbol']),
            limit_price=orderRequest['limit_price'] if orderRequest['limit_price'] else None,
            filled_price=None,
            stop_price=None,
            qty=orderRequest['qty'],
            filled_qty=None,
            side=orderRequest['side'],
            type=orderRequest['type'],
            time_in_force=orderRequest['time_in_force'],
            status=ITradeUpdateEvent.NEW,
            order_class=orderRequest['order_class'],
            created_at=self.get_current_time,
            updated_at=self.get_current_time,
            submitted_at=self.get_current_time,
            filled_at=None,
            legs=legs

        )
        self.Account['cash'] -= np.round(marginRequired/self.LEVERAGE, 2)
        self._update_order(order)
        return order

        # if self.MODE == IStrategyMode.BACKTEST:
        # else:
        #     raise NotImplementedError(f'Mode {self.MODE} not supported')

    def update_account_history(self):
        self.ACCOUNT_HISTORY[self.get_current_time] = self.Account

    def update_account_balance(self):
        self.ACCOUNT['buying_power'] = np.round(
            self.ACCOUNT['cash'] * self.LEVERAGE, 2)
        posistion_value = 0
        if len(self.Positions) == 0:
            self.ACCOUNT['equity'] = self.ACCOUNT['cash']
        else:
            for position in self.Positions.values():
                posistion_value += np.round(position['market_value'], 2)
            self.ACCOUNT['equity'] = self.ACCOUNT['cash'] + \
                np.round(posistion_value / self.LEVERAGE, 2)

    def format_on_bar(self, bar, symbol: str):
        if self.DataFeed == 'yf':
            assert symbol, 'Symbol must be provided when using yf data feed - format_on_bar()'
            index = pd.MultiIndex.from_product(
                [[symbol], pd.to_datetime(bar.index, utc=True)], names=['symbol', 'date'])

            bar = pd.DataFrame(data={
                'open': bar['Open'].values,
                'high': bar['High'].values,
                'low': bar['Low'].values,
                'close': bar['Close'].values,
                'volume': bar['Volume'].values,
            }, index=index, columns=['open', 'high', 'low', 'close', 'volume'])
            return bar
        else:
            print('DataFeed not supported')
            return None

    def format_on_quote(self, quote):
        data = IQuote(
            symbol=None,
            bid=quote.low,
            ask=quote.high,
            bid_size=0,
            ask_size=0,
            volume=quote.volume,
            timestamp=self.get_current_time
        )
        return data

    def format_on_trade_update(self, trade: ITradeUpdate):
        assert isinstance(
            trade, ITradeUpdate), 'Trade must be an instance of ITradeUpdate'
        return trade.order, trade.event
        # else:
        #     # format trade update from data feed
        #     raise NotImplementedError(
        #         f'DataFeed {self.DataFeed} not supported')

    def _load_historical_bar_data(self, asset: IMarketDataStream):
        try:
            bar_data_path = None
            if asset.get('stored'):
                if asset['stored_path']:
                    bar_data_path = asset['stored_path'] + \
                        f'/bar/{asset["symbol"]
                                }_{asset["time_frame"].unit.value}.h5'
                    if os.path.exists(bar_data_path):
                        print("Loading data from ", bar_data_path)
                        self.HISTORICAL_DATA[asset['symbol']
                                             ]['bar'] = pd.read_hdf(bar_data_path)
                        print(
                            self.HISTORICAL_DATA[asset['symbol']]['bar'].describe())
                        return True
                    else:
                        raise BaseException({
                            "code": "file_not_found",
                            "data": {"path": bar_data_path}
                        })
                else:
                    raise BaseException({
                        "code": "path_not_provided",
                        "data": {"path": asset['stored_path']}
                    })
        except Exception as e:
            raise e
        except BaseException as e:
            print("Error: ", e.args[0]['code'], e.args[0]['data']['path'])

        if self.DataFeed == 'yf':
            # Populate the HISTORICAL_DATA with the bar data
            self.HISTORICAL_DATA[asset['symbol']]['bar'] = self.get_history(
                asset, self.START_DATE, self.END_DATE, asset['time_frame'], False)

            # check if the data is empty
            if self.HISTORICAL_DATA[asset['symbol']]['bar'].empty:
                raise Exception({
                    "code": "no_data",
                    "data": {"symbol": asset['symbol']}
                })
            print("Loaded data for ", asset['symbol'])
            print(self.HISTORICAL_DATA[asset['symbol']]['bar'].describe())
            # if a stored path is provided save the data to the path
            if asset.get('stored_path'):
                # Create the directory if it does not exist
                Path(asset['stored_path']+'/bar').mkdir(
                    parents=True, exist_ok=True)
                # Save the data to the path
                print(self.HISTORICAL_DATA[asset['symbol']]['bar'].head(10))

                # Save the data to the path in hdf5 format
                bar_data_path = asset['stored_path'] + \
                    f'/bar/{asset["symbol"]
                            }_{asset["time_frame"].unit.value}.h5'
                print("Saving data to ", bar_data_path)
                self.HISTORICAL_DATA[asset['symbol']]['bar'].to_hdf(
                    bar_data_path, mode='a', key=asset["exchange"], index=True, format='table')

                return True

        else:
            print('DataFeed not supported')

    def streamMarketData(self, callback, assetStreams):
        """Listen to market data and call the callback function with the data"""
        super().streamMarketData(callback, assetStreams)
        loop = asyncio.new_event_loop()
        self.RUNNING_MARKET_STREAM = True
        TF = assetStreams[0]['time_frame']  # strategy time frame

        if self.MODE == IStrategyMode.BACKTEST:
            # Load Market data from yfinance for all assets
            self.HISTORICAL_DATA = {}

            for asset in assetStreams:
                self.HISTORICAL_DATA[asset['symbol']] = {}
                if asset['type'] == 'bar':
                    # populate HISTORICAL_DATA
                    try:
                        self._load_historical_bar_data(asset)
                    except Exception as e:
                        print("Removing Stream", asset,  "\nError: ", e)
                        assetStreams.remove(asset)
                        continue

                else:
                    raise NotImplementedError(
                        f'Stream type not {self.DataFeed}supported')

            # Stream data to callback one by one for each IAsset

            while self.get_current_time <= self.END_DATE and self.RUNNING_MARKET_STREAM and len(assetStreams) > 0:
                try:
                    print("streaming data for:", self.get_current_time)
                    # self.BACKTEST_FlOW_CONTROL_BARRIER.reset()
                    # futures = set()
                    # with ThreadPoolExecutor(max_workers=len(assetStreams), thread_name_prefix="MarketDataStream") as pool:

                    for asset in assetStreams:
                        if asset['type'] == 'bar':
                            try:
                                # Get the current bar data with the index
                                barData = self._get_current_bar(
                                    asset['symbol'])
                                if type(barData) == NoneType:
                                    continue
                                elif barData.empty:
                                    continue
                                else:

                                    loop.run_until_complete(callback(barData))

                            except BaseException as e:
                                print("Error: ", e)
                                continue
                        else:
                            print('DataFeed not supported')

                    # Wait for all assets to be streamed and processed
                        # for future in as_completed(futures):
                        #     result = future.result()
                        #     print("Result: ", result)

                    self.BACKTEST_FlOW_CONTROL_BARRIER.wait()

                    # LOG the account history
                    self.update_account_history()
                    # Go to next time frame
                    # FIXME: Implement time frame increment
                    self.setCurrentTime(TF.get_next_time_increment(
                        self.get_current_time))
                    if self.get_current_time > self.END_DATE:
                        self.update_account_history()
                        self.BACKTEST_FlOW_CONTROL_BARRIER.abort()
                        break

                except BrokenBarrierError:
                    continue
                except Exception as e:
                    print("Error: ", e)
                    continue
            loop.run_until_complete(self.closeStream(assetStreams))
            loop.run_until_complete(self.closeTradeStream())
            self.BACKTEST_FlOW_CONTROL_BARRIER.abort()

            print("End of Market Stream")
        else:
            #  live data feed
            for asset in assetStreams:
                self.HISTORICAL_DATA[asset['symbol']] = {}
                if asset['type'] == 'bar':
                    self.HISTORICAL_DATA[asset['symbol']
                                         ]['bar'] = pd.DataFrame()

            while self.RUNNING_MARKET_STREAM:
                for asset in assetStreams:
                    if asset['type'] == 'bar':
                        try:
                            # Get the current bar data with the index
                            barData = self._get_current_bar(
                                asset['symbol'], asset['time_frame'])
                            if type(barData) == NoneType:
                                continue
                            elif barData.empty:
                                continue
                            else:
                                loop.run_until_complete(callback(barData))
                                continue

                        except BaseException as e:
                            print("Error: ", e)
                            continue
                    else:
                        print('DataFeed not supported')
                nextBarTime = TF.get_next_time_increment(self.get_current_time)
                # you can add here any additional variable to break loop if necessary
                print("Next Bar Time: ", nextBarTime,
                      " Current Time: ", self.get_current_time)
                while nextBarTime > datetime.datetime.now() - datetime.timedelta(minutes=self.FeedDelay):
                    sleep(1)

    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        self.RUNNING_MARKET_STREAM = False
        # if self.MODE == IStrategyMode.BACKTEST:
        # else:
        #     raise NotImplementedError(f'Mode {self.MODE} not supported')

    def close_position(self, symbol: str, qty=None, percent=None):
        position = self.Positions.get(symbol)
        if position:
            quantityToClose = 0
            counterPosistionSide = IOrderSide.BUY if position['qty'] < 0 else IOrderSide.SELL
            if position['qty'] == 0:
                raise BaseException({
                    "code": "no_position",
                    "data": {"symbol": symbol}
                })
            if qty:
                if np.abs(qty) > np.abs(position['qty']):
                    raise BaseException({
                        "code": "invalid_qty",
                        "data": {"symbol": symbol, "qty": qty, "available": position['qty']}
                    })

                quantityToClose = qty

            elif percent:
                if percent > 100 or percent < 0:
                    raise BaseException({
                        "code": "invalid_percent",
                        "data": {"symbol": symbol, "percent": percent, "message": "Percent must be between 0 and 100"}
                    })
                quantityToClose = np.abs(position['qty']) * (percent / 100)

            marketCloseOrder = IOrder(
                order_id=uuid.uuid4(),
                asset=self.get_ticker_info(symbol),
                limit_price=None,
                filled_price=None,
                stop_price=None,
                qty=quantityToClose,
                filled_qty=None,
                side=counterPosistionSide,
                type=IOrderType.MARKET,
                time_in_force=ITimeInForce.GTC,
                status=ITradeUpdateEvent.NEW,
                order_class=IOrderClass.SIMPLE,
                created_at=self.get_current_time,
                updated_at=self.get_current_time,
                submitted_at=self.get_current_time,
                filled_at=None,
                legs=None
            )
            self._update_order(marketCloseOrder)
            return marketCloseOrder
        else:
            raise BaseException({
                "code": "no_position",
                "data": {"symbol": symbol}
            })

    def close_all_positions(self):
        for symbol in self.Positions.keys():
            if self.Positions[symbol]['qty'] != 0:
                self.close_position(symbol, qty=self.Positions[symbol]['qty'])
        return True

    @property
    def get_current_time(self) -> datetime.datetime:
        if self.MODE == IStrategyMode.BACKTEST:
            return self.CurrentTime
        else:
            return datetime.datetime.now() - datetime.timedelta(minutes=self.FeedDelay)

    def setCurrentTime(self, time: datetime.datetime):
        self.PreviousTime = self.CurrentTime
        self.CurrentTime = time

    def _get_current_bar(self, symbol: str, timeFrame: ITimeFrame = ITimeFrame(unit=ITimeFrameUnit.Minute, amount=1)):
        currentBar = None

        def find_next_bar(start: datetime.datetime, end: datetime.datetime):
            idx = pd.IndexSlice
            nonlocal currentBar
            nonlocal symbol
            try:
                if self.HISTORICAL_DATA[symbol]['bar'].empty:
                    return None
                currentBar = self.HISTORICAL_DATA[symbol]['bar'].loc[idx[symbol, end:end], :]
                # print("Current Bar: ", currentBar)
                if currentBar.empty:
                    currentBar = self.HISTORICAL_DATA[symbol]['bar'].loc[idx[symbol, start:end], :]
                    if currentBar.empty:
                        return None
                return True
            except KeyError:
                return None

        def convert_to_utc(time: datetime.datetime):
            return time.replace(tzinfo=datetime.timezone.utc)

        if self.MODE == IStrategyMode.BACKTEST:
            if symbol in self.HISTORICAL_DATA:

                current_time = convert_to_utc(self.get_current_time)
                if self.PreviousTime == None:
                    previous_time = current_time
                else:
                    previous_time = convert_to_utc(self.PreviousTime)

                found = find_next_bar(previous_time, current_time)
                if found == None:
                    return None
                   

            else:
                raise BaseException({
                    "code": "symbol_not_found",
                    "data": {"symbol": symbol}
                })
        else:
            # live data feed
            assert timeFrame, 'TimeFrame must be provided when using live data feed - _get_current_bar()'
            tf_current_time = timeFrame.get_time_increment(
                self.get_current_time)

            current_time = convert_to_utc(tf_current_time)
            if self.PreviousTime == None:
                previous_time = current_time
            else:
                previous_time = convert_to_utc(self.PreviousTime)

            find_next_bar(previous_time, current_time)
            if type(currentBar) == NoneType:
                try:
                    if not self.TICKER_INFO[symbol]:
                        self.get_ticker_info(symbol)
                    getBarsFrom = timeFrame.add_time_increment(
                        self.get_current_time, -2)
                    recentBars = self.get_history(
                        self.TICKER_INFO[symbol], getBarsFrom, self.get_current_time, timeFrame)
                    self.HISTORICAL_DATA[symbol]['bar'] = pd.concat(
                        [self.HISTORICAL_DATA[symbol]['bar'], recentBars])
                    # Remove duplicates keys in the history as sometimes if we get duplicates
                    self.HISTORICAL_DATA[symbol]['bar'] = self.HISTORICAL_DATA[symbol]['bar'].loc[~self.HISTORICAL_DATA[symbol]['bar'].index.duplicated(
                        keep='first')]

                    found = find_next_bar(previous_time, current_time)
                    if found == None:
                        # Default to the last bar
                        currentBar = self.HISTORICAL_DATA[symbol]['bar'].iloc[-1,:]
                        return None
                except KeyError:
                    return None
            # elif currentBar.empty:
            #     return None

        return currentBar

        # raise NotImplementedError(f'Mode {self.MODE} not supported')

    def get_results(self):
        """returns the backtest results - profit and loss,  profit and loss percentage, number of orders executed and filled, cag sharp rattio, percent win. etc."""
        if self.MODE == IStrategyMode.BACKTEST:
            # Calculate the profit and loss
            pnl = self.Account['cash'] - self.STARTING_CASH
            pnl_percent = (pnl / self.STARTING_CASH) * 100
            # Calculate the number of orders executed and filled
            totalOrders = len(self.Orders)
            filledOrders = len(
                [order for order in self.Orders.values() if order['status'] == ITradeUpdateEvent.FILLED])
            # Calculate the cagr
            cagr = (pnl_percent / (self.END_DATE - self.START_DATE).days) * 365
            # Calculate the sharp ratio
            # Calculate the percent win
            if totalOrders == 0 or filledOrders == 0:
                percentWin = 0
            else:
                percentWin = (filledOrders / totalOrders) * 100
            return {
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "total_orders": totalOrders,
                "filled_orders": filledOrders,
                "cagr": cagr,
                "percent_win": percentWin
            }
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    @property
    def Account(self) -> dict:
        """ Returns the state of the strategy."""
        self.update_account_balance()
        return self.ACCOUNT

    @Account.setter
    def Account(self, account: dict):
        """ Sets the state of the strategy."""
        self.ACCOUNT = account
        self.update_account_balance()


if __name__ == '__main__':
    # os.path.join(os.path.dirname(__file__), 'data')
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 5, 27), end_date=datetime(2024, 5, 31))
