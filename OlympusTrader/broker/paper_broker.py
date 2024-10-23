import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import datetime
from time import sleep
from types import NoneType
import uuid
import numpy as np
from typing import Awaitable, List, Literal, Optional, overload
from collections import deque
from threading import Barrier, BrokenBarrierError
from concurrent.futures import as_completed
from pathlib import Path

import vectorbt as vbt

import pandas as pd
from tqdm import tqdm

from .base_broker import BaseBroker
from .interfaces import IQuote, ISupportedBrokerFeatures, ITimeInForce, ISupportedBrokers, IOrderClass, IOrderRequest, IOrderSide, IOrderType, ITimeInForce, ITradeUpdate, ITradeUpdateEvent
from ..insight.insight import Insight
from .interfaces import IAccount, IOrder, IPosition, IAsset, IOrderLegs, IOrderLeg
from ..strategy.interfaces import IMarketDataStream, IStrategyMode
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit


import yfinance as yf


class PaperBroker(BaseBroker):
    MODE: IStrategyMode = IStrategyMode.BACKTEST

    ACCOUNT: IAccount = None
    Positions: dict[str, dict[uuid.UUID, IPosition]] = {}
    Orders: dict[uuid.UUID, IOrder] = {}
    LEVERAGE: int = 4

    # Backtest mode
    STARTING_CASH: float = 100_000.00
    START_DATE: datetime.datetime = None
    END_DATE: datetime.datetime = None
    CurrentTime: datetime.datetime = None
    PreviousTime: datetime.datetime = None
    HISTORICAL_DATA: dict[str, dict[Literal['trade',
                                            'quote', 'bar', 'news', 'signals'], pd.DataFrame]] = {}
    RUNNING_TRADE_STREAM: bool = False
    RUNNING_MARKET_STREAM: bool = False
    BACKTEST_FlOW_CONTROL_BARRIER: Barrier = None

    PENDING_ORDERS: deque[IOrder] = deque()
    ACTIVE_ORDERS: deque[IOrder] = deque()
    CLOSE_ORDERS: deque[IOrder] = deque()
    CANCELED_ORDERS: deque[IOrder] = deque()

    ACCOUNT_HISTORY: dict[datetime.date, IAccount] = {}

    _MARKET_STREAMS: dict[IMarketDataStream, asyncio.Future] = {}
    """Market Streams"""

    FeedDelay: int = 0
    # DEBUG
    VERBOSE: int = 0

    def __init__(self, cash: float = 100_000.00, start_date: datetime.date = None, end_date: datetime.date = None, leverage: int = 4, currency: str = "GBP", allow_short: bool = True, mode: IStrategyMode = IStrategyMode.BACKTEST, feed: Literal['yf', 'eod'] = 'yf', feedDelay: int = 0, verbose: int = 0):

        super().__init__(ISupportedBrokers.PAPER, True, feed)
        self.MODE = mode
        self.VERBOSE = verbose
        self.LEVERAGE = leverage
        self.STARTING_CASH = cash
        self.ACCOUNT = IAccount(account_id="PAPER_ACCOUNT", equity=self.STARTING_CASH, cash=self.STARTING_CASH, currency=currency,
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
            print("Live Papaer Trading Mode - There is a:",
                  feedDelay, "minute delay in the feed")
            self.FeedDelay = feedDelay
            self.CurrentTime = datetime.datetime.now(
            ) - datetime.timedelta(minutes=self.FeedDelay)

        self.supportedFeatures = ISupportedBrokerFeatures(
            barDataStreaming=True, featuredBarDataStreaming=True, trailingStop=False)

    def get_ticker_info(self, symbol: str):
        if symbol in self.TICKER_INFO:
            return self.TICKER_INFO[symbol]

        if self.DataFeed == 'yf':
            symbol = symbol.replace('/', '-')
            try:
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
                    shortable=self.Account.shorting_enabled,
                    fractionable=True,
                    min_order_size=0.001,
                    min_price_increment=1 /
                    np.power(10, tickerInfo["priceHint"]
                             ) if "priceHint" in tickerInfo else 0.01
                )
                self.TICKER_INFO[symbol] = tickerAsset
                return tickerAsset
            except Exception as e:
                print("Error: ", e)
                return None
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def get_history(self, asset: IAsset, start: datetime.datetime, end: datetime.datetime, resolution: ITimeFrame, shouldDelta: bool = True) -> pd.DataFrame:
        super().get_history(asset, start, end, resolution)

        if self.DataFeed == 'yf':
            symbol = asset['symbol'].replace('/', '-')
            formatTF = f'{resolution.amount_value}{
                resolution.unit_value[0].lower()}'
            if self.MODE == IStrategyMode.BACKTEST:
                delta: datetime.timedelta = start - \
                    self.get_current_time if shouldDelta else datetime.timedelta()
                # print("start: ", self.get_current_time-start, "end: ", self.get_current_time-end)
                data = yf.download(
                    symbol, start=resolution.get_time_increment(start-delta), end=resolution.get_time_increment(end-delta), interval=formatTF, progress=False)
            else:
                data = yf.download(
                    symbol, start=start, end=end, interval=formatTF, progress=False)

            return self.format_on_bar(data, asset['symbol'])
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def get_account(self):
        return self.Account

    def get_position(self, symbol: str, mode: Literal["all", "active"] = 'active'):
        positions = self.Positions.get(symbol)
        if positions:
            aggregated_position = {}
            for uid, position in positions.items():
                if position['qty'] != 0 and position['asset']['symbol'] == symbol:
                    if not aggregated_position:
                        aggregated_position = position.copy()
                    else:
                        aggregated_position['qty'] += position['qty']
                        aggregated_position['market_value'] += position['market_value']
                        aggregated_position['unrealized_pl'] += position['unrealized_pl']
                        aggregated_position['cost_basis'] += position['cost_basis']

            if (aggregated_position == None or (aggregated_position.get('qty') == 0 or not aggregated_position.get('qty')) and mode == 'active'):
                # del self.Positions[symbol]
                return None
            else:
                # Update the side
                aggregated_position['side'] = IOrderSide.BUY if aggregated_position['qty'] > 0 else IOrderSide.SELL

            return aggregated_position

    def get_positions(self, mode: Literal["all", "active"] = 'active'):
        aggregated_positions = {}
        for symbol in self.Positions.keys():
            aggregated_positions[symbol] = self.get_position(symbol)

        return aggregated_positions

    def get_orders(self):
        # active orders
        returned_orders: dict[str, IOrder] = {}
        active_orders = [order for order in self.Orders.values(
        ) if order['status'] == ITradeUpdateEvent.NEW or order['status'] == ITradeUpdateEvent.FILLED]
        if len(active_orders) == 0:
            return None
        for order in active_orders:
            returned_orders[order['order_id']] = order

        return returned_orders

    def get_order(self, order_id):
        return self.Orders.get(order_id)

    def format_order(self, order) -> IOrder:
        assert isinstance(order, IOrder), "Order must be a dictionary"
        return order

    def cancel_order(self, order_id: str):
        order = self.Orders.get(order_id)
        if order:
            if order['status'] == ITradeUpdateEvent.FILLED:
                raise BaseException({
                    "code": "already_filled",
                    "data": {"order_id": order_id}
                })
            elif order['status'] == ITradeUpdateEvent.CANCELED or order in self.CANCELED_ORDERS:
                raise BaseException({
                    "code": "already_canceled",
                    "data": {"order_id": order_id}
                })
            else:
                order['updated_at'] = self.get_current_time
                self.CANCELED_ORDERS.append(order)
                return order
        else:
            # check legs
            for i, leg_order in self.Orders.items():
                if leg_order['legs'] != None and leg_order not in self.CANCELED_ORDERS and (leg_order['status'] != ITradeUpdateEvent.CANCELED and leg_order['status'] != ITradeUpdateEvent.CLOSED):
                    if leg_order['legs'].get('take_profit'):
                        if leg_order['legs']['take_profit']['order_id'] == order_id:
                            # remove the take profit leg
                            del self.Orders[i]['legs']['take_profit']
                            return order_id

                    if leg_order['legs'].get('stop_loss'):
                        if leg_order['legs']['stop_loss']['order_id'] == order_id:
                            del self.Orders[i]['legs']['stop_loss']
                            return order_id

        # Order Id not found
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
            # trade stream for all of the pending, filled, canceled oerders.
            while self.get_current_time <= self.END_DATE and self.RUNNING_TRADE_STREAM:
                try:
                    self.BACKTEST_FlOW_CONTROL_BARRIER.wait()

                    self.processPendingOrders(callback, loop)
                    self.processCanceledOrders(callback, loop)
                    self.processActiveOrders(callback, loop)
                    self.processClosedOrders(callback, loop)

                except BrokenBarrierError:
                    continue
                except Exception as e:
                    print("Error: ", e)
                    continue
            print("End of Trade Stream")

        else:
            # live paper trade stream
            try:
                while self.RUNNING_TRADE_STREAM:
                    self.processPendingOrders(callback, loop)
                    self.processCanceledOrders(callback, loop)
                    self.processActiveOrders(callback, loop)
                    self.processClosedOrders(callback, loop)
                    sleep(1)
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
                order['filled_qty'] = order['qty']
                order['status'] = ITradeUpdateEvent.FILLED
                order['filled_at'] = self.get_current_time
                order['updated_at'] = self.get_current_time

                try:
                    self._update_order(order)
                    loop.run_until_complete(callback(ITradeUpdate(
                        order, order['status'])))
                except BaseException as e:
                    if e.code == "insufficient_funds":
                        print("Error: ", e)

                continue

            elif order['type'] == IOrderType.LIMIT:
                """
                sometime the currentbar high and low can be the same as the close price when using minute data with yfinance API
                """
                autopass = False
                if currentBar.high == currentBar.low:
                    pricePadding = 0.001  # 0.1%
                    if ((currentBar.high*(1+pricePadding)) >= order['limit_price'] >= (currentBar.low*(1-pricePadding))):
                        autopass = True

                # we need to check if the limit price is within the high and low of the current bar
                if (order['limit_price'] >= currentBar.low and order['limit_price'] <= currentBar.high) or autopass:
                    order['filled_price'] = order['limit_price']
                    order['filled_qty'] = order['qty']
                    order['status'] = ITradeUpdateEvent.FILLED
                    order['filled_at'] = self.get_current_time
                    order['updated_at'] = self.get_current_time
                    try:
                        self._update_order(order)
                        loop.run_until_complete(callback(ITradeUpdate(
                            order, order['status'])))
                    except BaseException as e:
                        if e.code == "insufficient_funds":
                            print("Error: ", e)
                    continue

    def processActiveOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.ACTIVE_ORDERS)):
            # update the position information as the position is filled and keep track of all  positions PNL
            self._update_position(order)

            # check if the order has take profit or stop loss
            if order['legs']:
                currentBar = self._get_current_bar(
                    order['asset']['symbol'])
                if currentBar is None:
                    continue
                currentBar = currentBar.iloc[0]
                # FIXME: Figure out if the take profit or stop loss is hit first

                if order['legs'].get('take_profit'):
                    take_profit = order['legs']['take_profit']
                    if (currentBar.high >= take_profit['limit_price'] >= currentBar.low) or ((currentBar.close >= take_profit['limit_price'] and order['side'] == IOrderSide.BUY) or (currentBar.close <= take_profit['limit_price'] and order['side'] == IOrderSide.SELL)):
                        take_profit['filled_price'] = take_profit['limit_price']
                        take_profit['status'] = ITradeUpdateEvent.CLOSED
                        take_profit['filled_at'] = self.get_current_time
                        take_profit['updated_at'] = self.get_current_time

                        order['stop_price'] = take_profit['limit_price']
                        order['updated_at'] = self.get_current_time
                        order['status'] = take_profit['status']
                        order['legs']['take_profit'] = take_profit
                        order['side'] = IOrderSide.SELL if order['side'] == IOrderSide.BUY else IOrderSide.BUY

                        self._update_order(order)
                        loop.run_until_complete(callback(ITradeUpdate(
                            order, order['status'])))
                        continue
                if order['legs'].get('stop_loss'):
                    stop_loss = order['legs']['stop_loss']
                    if (currentBar.high >= stop_loss['limit_price'] >= currentBar.low or ((currentBar.close <= stop_loss['limit_price'] and order['side'] == IOrderSide.BUY) or (currentBar.close >= stop_loss['limit_price'] and order['side'] == IOrderSide.SELL))):
                        stop_loss['filled_price'] = stop_loss['limit_price']
                        stop_loss['status'] = ITradeUpdateEvent.CLOSED
                        stop_loss['filled_at'] = self.get_current_time
                        stop_loss['updated_at'] = self.get_current_time

                        order['stop_price'] = stop_loss['limit_price']
                        order['updated_at'] = self.get_current_time
                        order['status'] = stop_loss['status']
                        order['legs']['stop_loss'] = stop_loss
                        order['side'] = IOrderSide.SELL if order['side'] == IOrderSide.BUY else IOrderSide.BUY

                        self._update_order(order)
                        loop.run_until_complete(callback(ITradeUpdate(
                            order,  order['status'])))
                        continue
            else:
                # USually a market order or limit order without take profit or stop loss
                continue

    def processClosedOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.CLOSE_ORDERS)):
            currentBar = self._get_current_bar(
                order['asset']['symbol'])
            if currentBar is None:
                continue
            currentBar = currentBar.iloc[0]

            order['stop_price'] = currentBar.open
            order['filled_qty'] = order['qty']
            order['status'] = ITradeUpdateEvent.CLOSED
            order['filled_at'] = self.get_current_time
            order['updated_at'] = self.get_current_time
            self._update_order(order)

            loop.run_until_complete(callback(ITradeUpdate(
                order, order['status'])))

    def processCanceledOrders(self, callback: Awaitable, loop: asyncio.AbstractEventLoop):
        for i, order in enumerate(list(self.CANCELED_ORDERS)):
            if order['status'] != ITradeUpdateEvent.FILLED and order['status'] != ITradeUpdateEvent.CLOSED:
                order['status'] = ITradeUpdateEvent.CANCELED
                order['updated_at'] = self.get_current_time
                self._update_order(order)
                loop.run_until_complete(callback(ITradeUpdate(
                    order, order['status'])))
            else:
                self.CANCELED_ORDERS.remove(order)

    async def closeTradeStream(self):
        self.RUNNING_TRADE_STREAM = False
        # if self.MODE == IStrategyMode.BACKTEST:
        # else:
        #     raise NotImplementedError(f'Mode {self.MODE} not supported')

    def _update_position(self, order: IOrder):
        symbol = order['asset']['symbol']
        orderId = order['order_id']
        currentBar = self._get_current_bar(symbol)
        if currentBar is None:
            return
        currentBar = currentBar.iloc[0]
        oldPosition: IPosition = None

        # check if there is a position for the symbol
        if not self.Positions.get(symbol):
            self.Positions[symbol] = {}

        # Check if this is a tracked open position
        if self.Positions[symbol].get(orderId):
            oldPosition = self.Positions[symbol].get(orderId).copy()
            match order['status']:
                case ITradeUpdateEvent.FILLED:
                    # watch changes in the position - order filled
                    pass

                case ITradeUpdateEvent.CLOSED:
                    if order['stop_price']:
                        if self.Positions[symbol][orderId]['side'] == IOrderSide.BUY:
                            # if order['side'] == IOrderSide.BUY:
                            assert order['side'] == IOrderSide.SELL, "Order side must be SELL for closing a BUY position"
                            self.Positions[symbol][orderId]['qty'] -= order['qty']
                        elif self.Positions[symbol][orderId]['side'] == IOrderSide.SELL:
                            assert order['side'] == IOrderSide.BUY, "Order side must be BUY for closing a SELL position"
                            self.Positions[symbol][orderId]['qty'] += order['qty']

                        # Clear buying power wwithheld by the order
                        entryPrince = order['filled_price'] if order[
                            'filled_price'] != None else self.Positions[symbol][orderId]['avg_entry_price']
                        self.Account.cash += np.round(
                            (order['qty'] * entryPrince) / self.LEVERAGE, 2)

                    else:
                        print("Order Close Without stop_price:", order)

        else:
            match order['status']:
                case ITradeUpdateEvent.FILLED:
                    # add positions dictionary
                    entryPrince = order['filled_price'] if order['filled_price'] != None else currentBar.close
                    market_value = entryPrince * order['qty']
                    self.Positions[symbol][orderId] = IPosition(
                        asset=order['asset'],
                        avg_entry_price=entryPrince,
                        qty=order['qty'] if order['side'] == IOrderSide.BUY else -order['qty'],
                        side=order['side'],
                        market_value=market_value,
                        cost_basis=market_value,
                        current_price=entryPrince,
                        unrealized_pl=0
                    )
                    marginRequired = order['qty'] * order['filled_price']
                    if self.Account.cash < marginRequired/self.LEVERAGE:
                        # Not enough buying power
                        order['status'] = ITradeUpdateEvent.CANCELED
                        self.CANCELED_ORDERS.append(order)
                        raise BaseException({
                            "code": "insufficient_funds",
                            "data": {"order_id": order['order_id']}
                        })
                    self.Account.cash -= np.round(
                        marginRequired/self.LEVERAGE, 2)
                    pass
                case ITradeUpdateEvent.CANCELED:
                    # ORder will just be canclled
                    pass

        if oldPosition:
            self.Positions[symbol][orderId]['current_price'] = currentBar.close if not order['stop_price'] else order['stop_price']

            if self.Positions[symbol][orderId]['current_price'] == oldPosition['current_price'] and order['status'] != ITradeUpdateEvent.CLOSED:
                # No price change in the position since the last update
                return

            # or order['status'] != ITradeUpdateEvent.CLOSED or not order['stop_price']:
            if oldPosition != 0:
                # Update the position market value
                self.Positions[symbol][orderId]['market_value'] = self.Positions[symbol][orderId]['current_price'] * \
                    np.abs(
                        # qunaity can be negative for short positions
                        oldPosition['qty'])

                # Update the unrealized PnL
                self.Positions[symbol][orderId]['unrealized_pl'] = (self.Positions[symbol][orderId]['market_value'] - self.Positions[symbol][orderId]['cost_basis']
                                                                    ) if self.Positions[symbol][orderId]['side'] == IOrderSide.BUY else (self.Positions[symbol][orderId]['cost_basis'] - self.Positions[symbol][orderId]['market_value'])

                # Update the account equity
                changeInPL = round(self.Positions[symbol][orderId]['unrealized_pl'] -
                                   oldPosition['unrealized_pl'], 2)
                self.Account.cash += changeInPL
                self.Account.equity += changeInPL

            if self.Positions[symbol][orderId]['qty'] == 0:
                # remove the position from the Positions dictionary
                del self.Positions[symbol][orderId]

        else:
            return

    def _log_signal(self, order: IOrder, signalType: Literal['entry', 'exit']):
        symbol = order['asset']['symbol']
        currentBarIndex = self._get_current_bar(symbol).index
        # Track the signals to later plot the signals, entries and exits and run against the backtester (ours and vector BT)
        if signalType == 'entry':
            # Log th entry signal
            if order['side'] == IOrderSide.BUY:
                self.HISTORICAL_DATA[symbol
                                     ]['signals'].loc[currentBarIndex, 'entries'] = True
            else:
                self.HISTORICAL_DATA[symbol
                                     ]['signals'].loc[currentBarIndex, 'short_entries'] = True
            # Record the entry price
            if order['filled_price']:
                if np.isnan(self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'][0]):
                    self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex,
                                                                'price'] = order['filled_price']
                else:
                    self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'] = (
                        self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'][0] + order['filled_price']) / 2

        elif signalType == 'exit':
            # Log the exit signal
            if order['side'] == IOrderSide.SELL:
                self.HISTORICAL_DATA[symbol
                                     ]['signals'].loc[currentBarIndex, 'exits'] = True
            else:
                self.HISTORICAL_DATA[symbol
                                     ]['signals'].loc[currentBarIndex, 'short_exits'] = True
            # Record the exit price
            if order['stop_price']:
                if np.isnan(self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'][0]):
                    self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex,
                                                                'price'] = order['stop_price']
                else:
                    self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'] = (
                        self.HISTORICAL_DATA[symbol]['signals'].loc[currentBarIndex, 'price'][0] + order['stop_price']) / 2

        if order['side'] == IOrderSide.BUY:
            self.HISTORICAL_DATA[symbol
                                 ]['signals'].loc[currentBarIndex, 'qty'] += order['qty']
        else:
            self.HISTORICAL_DATA[symbol
                                 ]['signals'].loc[currentBarIndex, 'qty'] -= order['qty']

    def _update_order(self, order: IOrder):
        if self.Orders.get(order['order_id']):
            oldOrder = self.Orders[order['order_id']].copy()
        else:
            oldOrder = None

        def onNewOrder():
            # Add the new order to the pending orders queue
            if not oldOrder:
                self.PENDING_ORDERS.append(order)

                """ Check if the order is affecting any active orders as it might be an order to close a position and update the active orders accordingly"""
                if self.get_position(order['asset']['symbol']):
                    tempCloseOrder = order.copy()
                    conflicting = False
                    for i, activeOrder in enumerate(list(self.ACTIVE_ORDERS)):
                        if activeOrder['asset']['symbol'] == order['asset']['symbol'] and \
                                activeOrder['side'] != order['side'] and \
                                activeOrder['status'] == ITradeUpdateEvent.FILLED:

                            if order in self.PENDING_ORDERS:
                                # remove the order from the pending orders
                                self.PENDING_ORDERS.remove(order)

                            if activeOrder['qty'] == tempCloseOrder['qty']:
                                # close the position
                                self.ACTIVE_ORDERS.remove(activeOrder)

                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = activeOrder['filled_qty']

                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())
                                tempCloseOrder['qty'] = 0
                                conflicting = True

                            elif (activeOrder['qty'] - tempCloseOrder['qty']) > 0:
                                # partially close the position
                                self.ACTIVE_ORDERS.remove(activeOrder)
                                # reduce the quantity of the active order
                                activeOrder['qty'] -= tempCloseOrder['qty']
                                self.ACTIVE_ORDERS.append(activeOrder)

                                # send the close order to the close orders
                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = tempCloseOrder['qty']
                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())
                                tempCloseOrder['qty'] = 0
                                conflicting = True
                            else:
                                # close multiple positions. quantityLeft > 0
                                quantityLeft = tempCloseOrder['qty'] - \
                                    activeOrder['qty']
                                self.ACTIVE_ORDERS.remove(activeOrder)
                                # send the close order for the active order
                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['qty'] = activeOrder['qty']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = tempCloseOrder['qty']
                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())

                                tempCloseOrder['qty'] = quantityLeft
                                conflicting = True
                                continue

                            if tempCloseOrder['qty'] == 0:
                                break
                    if tempCloseOrder['qty'] > 0 and conflicting:
                        # Add the order to the pending orders
                        order['qty'] = tempCloseOrder['qty']
                        self.PENDING_ORDERS.append(order)

        def onFilledOrder():
            if oldOrder in self.PENDING_ORDERS:
                self.PENDING_ORDERS.remove(oldOrder)

                # update position of the order

                self._update_position(order)
                # Add the order to the active orders
                if self.Positions[order['asset']['symbol']][order['order_id']]['qty'] != 0:
                    # check if the order has legs and update the states of the legs
                    if order['legs']:
                        if order['legs'].get('take_profit'):
                            order['legs']['take_profit']['status'] = ITradeUpdateEvent.PENDING_NEW
                            order['legs']['take_profit']['updated_at'] = self.get_current_time
                        if order['legs'].get('stop_loss'):
                            order['legs']['stop_loss']['status'] = ITradeUpdateEvent.PENDING_NEW
                            order['legs']['stop_loss']['updated_at'] = self.get_current_time
                    # Add the order to the active orders
                    self.ACTIVE_ORDERS.append(order)
                    if self.MODE == IStrategyMode.BACKTEST:
                        # log the entry signal
                        self._log_signal(order, 'entry')

            elif oldOrder in self.ACTIVE_ORDERS:
                # update position of the order
                self._update_position(order)

        def onClosedOrder():
            # This update is already done in the on trade update
            self._update_position(order)

            # Check if the position is completely closed and remove it from the positions dictionary - if the qty is 0 or None
            if self.Positions[order['asset']['symbol']].get(order['order_id']) == None:
                pass

            if oldOrder in self.ACTIVE_ORDERS:
                self.ACTIVE_ORDERS.remove(oldOrder)

            if oldOrder in self.CANCELED_ORDERS:
                self.CANCELED_ORDERS.remove(oldOrder)

            if oldOrder in self.CLOSE_ORDERS:
                self.CLOSE_ORDERS.remove(oldOrder)
            if order in self.CLOSE_ORDERS:
                # This is when the order was sent and we are closing a position with another order id than the original order id - order is the updated order with the new order id and oldOrder is the original order (in the filled state)
                self.CLOSE_ORDERS.remove(order)

            if self.MODE == IStrategyMode.BACKTEST:
                # log the exit signal
                self._log_signal(order, 'exit')

        def onCanceledOrder():
            if oldOrder in self.ACTIVE_ORDERS:
                """ Should not really happen as the order state check should be before have already happened when cancelling the order """
                # if order is already filled oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                if oldOrder in self.CANCELED_ORDERS:
                    self.CANCELED_ORDERS.remove(oldOrder)

                raise BaseException({
                    "code": "already_filled",
                    "data": {"symbol": order['asset']['symbol']}
                })

            self._update_position(order)
            if (oldOrder['status'] == ITradeUpdateEvent.NEW) or (oldOrder in self.PENDING_ORDERS):
                # Remove the order from the pending orders if it is not filled and give your money back
                self.PENDING_ORDERS.remove(oldOrder)

            if oldOrder in self.CLOSE_ORDERS:
                self.CLOSE_ORDERS.remove(oldOrder)

            if oldOrder in self.CANCELED_ORDERS:
                self.CANCELED_ORDERS.remove(oldOrder)

        match order['status']:
            case ITradeUpdateEvent.NEW:
                onNewOrder()
            case ITradeUpdateEvent.FILLED:
                onFilledOrder()
            case ITradeUpdateEvent.CANCELED:
                onCanceledOrder()
            case ITradeUpdateEvent.CLOSED:
                onClosedOrder()
            case _:
                pass

        self.Orders[order['order_id']] = order
        return order

    def execute_insight_order(self, insight: Insight, asset: IAsset):
        super().execute_insight_order(insight, asset)
        orderRequest: IOrderRequest = {
            "symbol": insight.symbol,
            "qty": insight.quantity,
            "side": insight.side,
            "time_in_force": ITimeInForce.GTC,
            "order_class": IOrderClass.SIMPLE
        }

        assert insight.quantity > 0, "Order quantity must be greater than 0"

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

        except BaseException as e:
            raise e

    def _submit_order(self, orderRequest: IOrderRequest) -> IOrder:
        # check if the buying power is enough to place the order
        try: 
            if orderRequest['type'] == IOrderType.MARKET:
                currentBar = self._get_current_bar(
                    orderRequest['symbol'])
                if currentBar.empty:
                    return
                currentBar = currentBar.iloc[0]
                orderRequest['limit_price'] = currentBar.close

            marginRequired = orderRequest['qty'] * orderRequest['limit_price']
            buying_power = self.Account.buying_power

            # Account for the market value of the position if the order is in the opposite direction
            position_agg = self.get_position(orderRequest['symbol'])
            if position_agg:
                if (orderRequest['side'] == IOrderSide.SELL and position_agg['qty'] < 0) or \
                        (orderRequest['side'] == IOrderSide.BUY and position_agg['qty'] > 0):
                    buying_power += position_agg['market_value']

            if buying_power < marginRequired:
                raise BaseException({
                    "code": "insufficient_balance",
                    "data": {"symbol": orderRequest['symbol'],
                            "requires": marginRequired,
                            "available": self.Account.buying_power,
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

            if self.Account.cash < marginRequired/self.LEVERAGE:
                # Not enough buying power
                raise BaseException({
                    "code": "insufficient_funds",
                    "data": {"order_id": order['order_id']}
                })
            # self.Account.cash -= np.round(marginRequired/self.LEVERAGE, 2)
            self._update_order(order)
            return order
        
        except BaseException as e:
            raise  e

    def update_account_history(self):
        if self.VERBOSE >= 2:
            print("Updating Account History")
            print("Account: ", self.Account)
        self.ACCOUNT_HISTORY[self.get_current_time] = self.Account

    def update_account_balance(self):
        self.ACCOUNT.buying_power = max(np.round(
            self.ACCOUNT.cash * self.LEVERAGE, 2), 0)

    def format_on_bar(self, bar, symbol: str):
        if self.DataFeed == 'yf':
            assert symbol, 'Symbol must be provided when using yf data feed - format_on_bar()'
            index = pd.MultiIndex.from_product(
                [[symbol], pd.to_datetime(bar.index, utc=True)], names=['symbol', 'date'])

            bar = pd.DataFrame(data={
                'open': np.array(bar['Open'].values).reshape(-1),
                'high': np.array(bar['High'].values).reshape(-1),
                'low': np.array(bar['Low'].values).reshape(-1),
                'close': np.array(bar['Close'].values).reshape(-1),
                'volume': np.array(bar['Volume'].values).reshape(-1),
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

    def _applyTA(self, asset: IMarketDataStream):
        symbol = asset['symbol'] if asset.get(
            'feature') == None else asset['feature']
        if not asset.get('applyTA') or not asset.get('TA'):
            return
        print("Applying TA for: ", symbol)
        self.HISTORICAL_DATA[symbol]['bar'].ta.strategy(asset['TA'])

    def _load_historical_bar_data(self, asset: IMarketDataStream):
        try:
            bar_data_path = None
            symbol = asset['symbol'] if asset.get(
                'feature') == None else asset['feature']
            if asset.get('stored') and asset.get('stored_path'):
                bar_data_path = asset['stored_path'] + \
                    f'/bar/{asset['symbol']}_{asset["time_frame"]
                                              }_{self.START_DATE}-{self.END_DATE}.h5'

            if asset.get('stored'):
                if asset['stored_path']:
                    if os.path.exists(bar_data_path):
                        print("Loading data from ", bar_data_path)
                        self.HISTORICAL_DATA[symbol]['bar'] = pd.read_hdf(
                            bar_data_path)
                        # check if the data is empty
                        if self.HISTORICAL_DATA[symbol]['bar'].empty:
                            raise Exception({
                                "code": "no_data",
                                "data": {"symbol": symbol}
                            })
                        # apply the TA strategy
                        self._applyTA(asset)
                        print(
                            self.HISTORICAL_DATA[symbol]['bar'].describe())
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
            self.HISTORICAL_DATA[symbol]['bar'] = self.get_history(
                asset, self.START_DATE, self.END_DATE, asset['time_frame'], False)

            # check if the data is empty
            if self.HISTORICAL_DATA[symbol]['bar'].empty:
                raise Exception({
                    "code": "no_data",
                    "data": {"symbol": symbol}
                })
            # apply the TA strategy
            self._applyTA(asset)

            print("Loaded data for ", symbol)
            print(self.HISTORICAL_DATA[symbol]['bar'].describe())
            # if a stored path is provided save the data to the path
            if asset.get('stored_path'):
                # Create the directory if it does not exist
                Path(asset['stored_path']+'/bar').mkdir(
                    parents=True, exist_ok=True)
                # Save the data to the path
                print(self.HISTORICAL_DATA[symbol]['bar'].head(10))

                # Save the data to the path in hdf5 format
                print("Saving data to ", bar_data_path)
                self.HISTORICAL_DATA[symbol]['bar'].to_hdf(
                    bar_data_path, mode='a', key=asset["exchange"], index=True, format='table')

            return True

        else:
            print('DataFeed not supported')

    def streamMarketData(self, callback, assetStreams):
        """Listen to market data and call the callback function with the data"""
        super().streamMarketData(callback, assetStreams)
        loop = asyncio.new_event_loop()
        self.RUNNING_MARKET_STREAM = True
        TF = None  # strategy time frame
        hasFeature = False

        if self.MODE == IStrategyMode.BACKTEST:
            # Load Market data from yfinance for all assets
            self.HISTORICAL_DATA = {}

            for asset in tqdm(assetStreams, desc="Loading Historical Data"):
                symbol = asset['symbol'] if asset.get(
                    'feature') == None else asset['feature']
                if asset['type'] == 'bar':
                    self.HISTORICAL_DATA[symbol] = {}
                    # populate HISTORICAL_DATA
                    try:
                        if self._load_historical_bar_data(asset):
                            if self.MODE == IStrategyMode.BACKTEST:

                                if asset.get('feature') == None:
                                    # Create signals dataframe
                                    size = self.HISTORICAL_DATA[symbol
                                                                ]['bar'].shape[0]
                                    self.HISTORICAL_DATA[symbol]['signals'] = pd.DataFrame(data={"entries": np.zeros(size), "short_entries": np.zeros(size), "exits": np.zeros(
                                        size), "short_exits": np.zeros(size), "price": np.zeros(size), "qty": np.zeros(size)}, columns=["entries", "short_entries", "exits", "short_exits", "price", "qty"], index=self.HISTORICAL_DATA[asset['symbol']]['bar'].index)
                                    # .reindex_like(self.HISTORICAL_DATA[asset['symbol']]['bar'])
                                    self.HISTORICAL_DATA[symbol]['signals'][[
                                        'entries', 'exits', 'short_entries', 'short_exits']] = False
                                    self.HISTORICAL_DATA[symbol]['signals'][[
                                        'qty']] = 0
                                    self.HISTORICAL_DATA[symbol]['signals'][[
                                        'price']] = np.nan
                                    if not TF:
                                        # set the Main time frame to the first asset time frame
                                        TF = asset['time_frame']
                                else:
                                    # change the symbol to the feature symbol in the multi index
                                    self.HISTORICAL_DATA[symbol]['bar'].rename(
                                        index={asset['symbol']: symbol}, inplace=True)
                                    if hasFeature == False:
                                        # signal for the backtest to use dynamic time resoltion
                                        hasFeature = True

                    except Exception as e:
                        print("Removing Bar Stream",
                              asset['symbol'],  "\nError: ", e)
                        assetStreams.remove(asset)
                        continue

                else:
                    raise NotImplementedError(
                        f'Stream type not {self.DataFeed}supported')

            # Stream data to callback one by one for each IAsset

            while self.get_current_time <= self.END_DATE and self.RUNNING_MARKET_STREAM and len(assetStreams) > 0:
                try:
                    if self.VERBOSE > 0:
                        print("\nstreaming data for:",
                              self.get_current_time, "\n")
                    for asset in assetStreams:
                        isFeature = False
                        if asset['type'] == 'bar':
                            if asset.get('feature') == None:
                                symbol = asset['symbol']
                            else:
                                symbol = asset['feature']
                                isFeature = True

                            try:
                                if isFeature:
                                    if self.PreviousTime == None:
                                        barDatas = self.HISTORICAL_DATA[symbol]['bar'].loc[(self.HISTORICAL_DATA[symbol]['bar'].index.get_level_values('date') >= self.get_current_time.replace(
                                            tzinfo=datetime.timezone.utc)) & (self.HISTORICAL_DATA[symbol]['bar'].index.get_level_values('date') <= self.get_current_time.replace(tzinfo=datetime.timezone.utc))]
                                    else:
                                        barDatas = self.HISTORICAL_DATA[symbol]['bar'].loc[(self.HISTORICAL_DATA[symbol]['bar'].index.get_level_values('date') > self.PreviousTime.replace(
                                            tzinfo=datetime.timezone.utc)) & (self.HISTORICAL_DATA[symbol]['bar'].index.get_level_values('date') <= self.get_current_time.replace(tzinfo=datetime.timezone.utc))]
                                    if type(barDatas) == NoneType:
                                        continue
                                    elif barDatas.empty:
                                        continue
                                    else:
                                        for index in barDatas.index:
                                            loop.run_until_complete(
                                                callback(barDatas.loc[[index]], timeframe=asset['time_frame']))
                                else:
                                    # Get the current bar data with the index
                                    barData = self._get_current_bar(symbol)
                                    if type(barData) == NoneType:
                                        continue
                                    elif barData.empty:
                                        continue
                                    else:
                                        loop.run_until_complete(
                                            callback(barData, timeframe=asset['time_frame']))

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
            barStreamCount = 0
            for asset in assetStreams:
                self.HISTORICAL_DATA[asset['symbol']] = {}
                if asset['type'] == 'bar':
                    self.HISTORICAL_DATA[asset['symbol']
                                         ]['bar'] = pd.DataFrame()
                    barStreamCount += 1
                    # if asset.get('feature') == None:
                    #     TF = asset['time_frame']

            pool = ThreadPoolExecutor(max_workers=(
            barStreamCount), thread_name_prefix="MarketDataStream")
            for asset in assetStreams:
                if asset['type'] == 'bar':
                    # Stream data to callback one by one for each IAsset
                    async def PaperBarStreamer(asset: IMarketDataStream):
                        """
                        Stream data to the callback function
                        """
                        lastChecked = pd.Timestamp.now() - datetime.timedelta(minutes=self.FeedDelay) # last checked time for the asset stream data - FeedDelay
                        while self.RUNNING_MARKET_STREAM:
                            nextTimetoCheck = asset['time_frame'].get_next_time_increment(lastChecked)
                            await asyncio.sleep((nextTimetoCheck - lastChecked).total_seconds())

                            try:
                                # Get the current bar data with the index
                                barDatas = self._get_current_bar(
                                    asset["symbol"], asset['time_frame'], lastChecked)
                                if type(barDatas) == NoneType:
                                    continue
                                elif barDatas.empty:
                                    continue
                                else:
                                    # TODO: May need to check if this is a feature or not and get the data accordingly
                                    for idx in  range(0, len(barDatas)):
                                        bar = barDatas.iloc[[idx]]
                                        # if asset['time_frame'].is_time_increment(bar.index[0][1]) and (not (bar.index[0][1]) < lastChecked):
                                        if asset['time_frame'].is_time_increment(bar.index[0][1]) and (not (bar.index[0][1]) < lastChecked.replace(tzinfo=datetime.timezone.utc)):
                                            loop.run_until_complete(
                                                callback(bar, timeframe=asset['time_frame']))
    
                                        # loop.run_until_complete(
                                        #     callback(barData.loc[[index]], timeframe=asset['time_frame']))
                                    
                            except BaseException as e:
                                print("Error: ", e)
                                continue
                            
                            lastChecked = nextTimetoCheck
                    streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                    self._MARKET_STREAMS[streamKey] = loop.create_task(
                        PaperBarStreamer(asset), name=f"Market:{streamKey}")
            
                    # pool.submit(, asset)
            loop.run_forever()
                    


    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        if self.RUNNING_MARKET_STREAM:
            # _MARKET_STREAMS may nee to be part of the parant class
            for asset in assetStreams:
                streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                marketStream = self._MARKET_STREAMS.get(streamKey, None)
                if marketStream:
                    print("Closing Market Stream for: ", streamKey)
                    if type(marketStream) == asyncio.Task:
                        marketStream.cancel("Relenquishing Market Stream for: " +streamKey)
                    del self._MARKET_STREAMS[streamKey]
                    return True
                if len(self._MARKET_STREAMS) == 0:
                    self.RUNNING_MARKET_STREAM = False
                return True
        return False

    def close_position(self, symbol: str, qty=None, percent=None):
        position = self.get_position(symbol)
        if position:
            quantityToClose = 0
            counterPosistionSide = IOrderSide.BUY if position[
                'side'] == IOrderSide.SELL else IOrderSide.SELL
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
            """FIXME: This should also remove the active orders that need to be closed or reduced in size
                right now it only closes the position and does not remove the active order from the active orders list.
                This would mean that the order would still be active and could be filled later on, thus adjusting the position size.
                which would make the results inconsistent with the actual orders placed.

                self.CLOSE_ORDERS.append(marketCloseOrder)
                then we can process the rest in the self._update_order() method
            """
            self._update_order(marketCloseOrder)
            return marketCloseOrder
        else:
            raise BaseException({
                "code": "no_position",
                "data": {"symbol": symbol}
            })

    def close_all_positions(self):
        activePositions = self.get_positions()
        for symbol in activePositions:
            if activePositions.get(symbol) != None:
                self.close_position(symbol, qty=activePositions[symbol]['qty'])
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

    def _get_current_bar(self, symbol: str, timeFrame: ITimeFrame = ITimeFrame(unit=ITimeFrameUnit.Minute, amount=1), lastChecked: datetime.datetime = None) -> pd.DataFrame:
        currentBar = None

        def find_next_bar(start: datetime.datetime, end: datetime.datetime):
            idx = pd.IndexSlice
            nonlocal currentBar
            nonlocal symbol
            try:
                if self.HISTORICAL_DATA[symbol]['bar'].empty:
                    return None
                # Try to get the exact current time bar
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
            # time.astimezone(datetime.timezone.utc) # Some brokers may need this line as right now your just falsely assuming the time is in UTC when it may not be
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
            useTime = self.get_current_time
            
            
            tf_current_time = timeFrame.get_time_increment(useTime)

            current_time = convert_to_utc(tf_current_time)
            # if self.PreviousTime == None:
            #     # Default to the current time for backtesting 
            #     previous_time = current_time
            # else:
            #     previous_time = convert_to_utc(self.PreviousTime)
            # TODO: Else statement needs to be tested as we should just get the latest bar from the previous time
            previous_time = convert_to_utc(lastChecked) if lastChecked else current_time

            find_next_bar(previous_time, current_time)
            if type(currentBar) == NoneType or currentBar.empty:
                try:
                    if not self.TICKER_INFO[symbol]:
                        self.get_ticker_info(symbol)
                    getBarsFrom = timeFrame.add_time_increment(tf_current_time, -2)
                    # TODO: Could be using previous_time as we now track the last checked time for each asset stream
                    recentBars = self.get_history(
                        self.TICKER_INFO[symbol], getBarsFrom, timeFrame.get_next_time_increment(useTime), timeFrame)
                    self.HISTORICAL_DATA[symbol]['bar'] = pd.concat(
                        [self.HISTORICAL_DATA[symbol]['bar'], recentBars])
                    # Remove duplicates keys in the history as sometimes if we get duplicates
                    self.HISTORICAL_DATA[symbol]['bar'] = self.HISTORICAL_DATA[symbol]['bar'].loc[~self.HISTORICAL_DATA[symbol]['bar'].index.duplicated(
                        keep='first')]

                    found = find_next_bar(previous_time, current_time)
                    if found == None:
                        # Default to the last bar
                        currentBar = self.HISTORICAL_DATA[symbol]['bar'].iloc[-1, :]
                        return None
                except KeyError:
                    return None
            # elif currentBar.empty:
            #     return None

        return currentBar

        # raise NotImplementedError(f'Mode {self.MODE} not supported')

    def get_VBT_results(self, timeFrame: ITimeFrame) -> dict[str, vbt.Portfolio]:
        """returns the backtest results from Vector BT - profit and loss,  profit and loss percentage, number of orders executed and filled, cag sharp rattio, percent win. etc."""
        results: dict[str, vbt.Portfolio] = {}

        def calc_expectancy_ratio(trades: vbt.EntryTrades):
            if len(trades) == 0:
                return np.nan

            returns = trades.returns.values
            winners = returns[returns > 0]
            losers = returns[returns <= 0]

            pct_winners = len(winners) / len(returns)
            pct_losers = len(losers) / len(returns)

            avg_win = np.mean(winners) if len(winners) > 0 else 0
            avg_loss = abs(np.mean(losers)) if len(losers) > 0 else 1
            R = avg_win / avg_loss

            E = pct_winners * R - pct_losers
            return E

        expectancy_ratio = (
            "Expectancy Ratio",
            dict(
                title="Expectancy Ratio",
                calc_func=calc_expectancy_ratio,
                resolve_trades=True
            )
        )

        if self.MODE == IStrategyMode.BACKTEST:
            for asset in tqdm(self.HISTORICAL_DATA.keys(), desc="Running VBT Backtest"):
                if isinstance(self.HISTORICAL_DATA[asset].get('signals'), pd.DataFrame):
                    try:
                        vbtParams = {
                            "init_cash": self.STARTING_CASH,
                            "open": self.HISTORICAL_DATA[asset]['bar']['open'].reset_index(level='symbol', drop=True),
                            "high": self.HISTORICAL_DATA[asset]['bar']['high'].reset_index(level='symbol', drop=True),
                            "low": self.HISTORICAL_DATA[asset]['bar']['low'].reset_index(level='symbol', drop=True),
                            "close": self.HISTORICAL_DATA[asset]['bar']['close'].reset_index(level='symbol', drop=True),
                            "entries": self.HISTORICAL_DATA[asset]['signals']['entries'].reset_index(level='symbol', drop=True),
                            "short_entries": self.HISTORICAL_DATA[asset]['signals']['short_entries'].reset_index(level='symbol', drop=True),
                            "exits": self.HISTORICAL_DATA[asset]['signals']['exits'].reset_index(level='symbol', drop=True),
                            "short_exits": self.HISTORICAL_DATA[asset]['signals']['short_exits'].reset_index(level='symbol', drop=True),
                            "price": self.HISTORICAL_DATA[asset]['signals']['price'].reset_index(level='symbol', drop=True),
                            "size":  self.HISTORICAL_DATA[asset]['signals']['qty'].abs().reset_index(level='symbol', drop=True),
                            "freq": timeFrame.unit.value[0].lower(),
                            "accumulate": True
                        }

                        # run the backtest
                        print("Running backtest with Vector BT for:", asset)
                        results[asset] = vbt.Portfolio.from_signals(
                            **vbtParams)
                        # results[asset] = vbt.Portfolio.from_orders(
                        #     **vbtParams)
                        print(results[asset].stats(
                            metrics=[*vbt.Portfolio.metrics, expectancy_ratio]))
                    except Exception as e:
                        print("Failed to run backtest for ", asset, e)
                        continue
                else:
                    print("No signals for feature ", asset)
                    continue
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')
        return results

    @property
    def Account(self) -> IAccount:
        """ Returns the state of the strategy."""
        self.update_account_balance()
        return self.ACCOUNT

    @Account.setter
    def Account(self, account: IAccount):
        """ Sets the state of the strategy."""
        cash = account.cash
        if cash and cash != self.ACCOUNT.cash:
            self.ACCOUNT.cash = max(cash, 0)
        equity = account.get('equity')
        if equity and equity != self.ACCOUNT.equity:
            self.ACCOUNT.equity = max(equity, 0)

        if account.get('leverage') and account.leverage != self.ACCOUNT.leverage:
            self.ACCOUNT.leverage = account.leverage

        self.update_account_balance()


if __name__ == '__main__':
    # os.path.join(os.path.dirname(__file__), 'data')
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 5, 27), end_date=datetime(2024, 5, 31))
