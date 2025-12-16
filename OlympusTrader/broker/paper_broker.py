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

import logging
# Configure logging
# logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s - %(message)s')

import vectorbt as vbt

import pandas as pd
from tqdm import tqdm
from tqdm.notebook import tqdm_notebook

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

    UPDATE_ORDERS: deque[IOrder] = deque()
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
        super().__init__(name=ISupportedBrokers.PAPER, paper=True, feed=feed, verbose=verbose)
        self.MODE = mode
        self.VERBOSE = verbose
        self.LEVERAGE = leverage
        self.STARTING_CASH = cash
        self.ACCOUNT = IAccount(account_id="PAPER_ACCOUNT", equity=self.STARTING_CASH, cash=self.STARTING_CASH, currency=currency,
                                buying_power=cash*self.LEVERAGE, leverage=self.LEVERAGE, shorting_enabled=allow_short)
        self.HISTORICAL_DATA = {}
        self.Positions = {}
        self.Orders = {}
        self.UPDATE_ORDERS = deque()
        self.PENDING_ORDERS = deque()
        self.ACTIVE_ORDERS = deque()
        self.CLOSE_ORDERS = deque()
        self.CANCELED_ORDERS = deque()
        self.ACCOUNT_HISTORY = {}
        self.FILLED_ORDERS_HISTORY = []
        self._MARKET_STREAMS = {}
        self.FeedDelay = feedDelay
        self.CurrentTime = None
        self.PreviousTime = None
        self.START_DATE = start_date
        self.END_DATE = end_date
        if self.MODE == IStrategyMode.BACKTEST:
            assert start_date and end_date, 'Start and End date must be provided for backtesting'
            assert start_date < end_date, 'Start date must be before end date'
            self.START_DATE = start_date
            self.END_DATE = end_date
            self.CurrentTime = self.START_DATE
            self.update_account_history()
            # self.BACKTEST_FLOW_CONTROL_BARRIER = Barrier(4)
        else:
            self.LOGGER.info("Live Paper Trading Mode - There is a:",
                  feedDelay, "minute delay in the feed")
            self.FeedDelay = feedDelay
            self.CurrentTime = datetime.datetime.now(
            ) - datetime.timedelta(minutes=self.FeedDelay)
        self.supportedFeatures = ISupportedBrokerFeatures(
            barDataStreaming=True, featuredBarDataStreaming=True, trailingStop=False)

    def get_ticker_info(self, symbol: str):
        cached = super().get_ticker_info(symbol)
        if cached:
            return cached

        if self.DataFeed == 'yf':
            symbol = symbol.replace('/', '-')
            try:
                yfRes = yf.Ticker(symbol)
                if not yfRes:
                    return None
                tickerInfo = yfRes.info
                tickerAsset: IAsset = IAsset(
                    id=str(uuid.uuid4()),
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
                self.LOGGER.error("Error: ", e)
                return None
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def get_history(self, asset: IAsset, start: datetime.datetime, end: datetime.datetime, resolution: ITimeFrame, shouldDelta: bool = True) -> pd.DataFrame:
        super().get_history(asset, start, end, resolution)

        if self.DataFeed == 'yf':
            symbol = asset['symbol'].replace('/', '-')
            formatTF = f'{resolution.amount_value}{resolution.unit_value[0].lower()}'
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
        # First, try to find the order directly
        order = self.get_order(order_id)
        if order:
            # Check if the order is already filled or closed
            if order['status'] == ITradeUpdateEvent.FILLED or order['status'] == ITradeUpdateEvent.CLOSED:
                self.LOGGER.warning(
                    f"Cannot cancel order {order_id} because it is already {order['status']}")
                raise BaseException({
                    "code": "already_filled",
                    "data": {"order_id": order_id, "status": order['status']}
                })

            order['status'] = ITradeUpdateEvent.CANCELED
            order['updated_at'] = self.get_current_time

            # Check if order is already in CANCELED_ORDERS to avoid duplicates
            if not any(canceled_order['order_id'] == order_id for canceled_order in self.CANCELED_ORDERS):
                self.CANCELED_ORDERS.append(order)
                self.LOGGER.debug(f"Added order {order_id} to CANCELED_ORDERS")

            # Remove from PENDING_ORDERS if present
            for pending_order in list(self.PENDING_ORDERS):
                if pending_order['order_id'] == order_id:
                    self.PENDING_ORDERS.remove(pending_order)
                    self.LOGGER.debug(
                        f"Removed order {order_id} from PENDING_ORDERS during cancellation")

            # If this order has TP/SL legs, cancel those too
            if order.get('legs'):
                if order['legs'].get('take_profit'):
                    tp_order_id = order['legs']['take_profit']['order_id']
                    self.LOGGER.debug(
                        f"Canceling take profit leg {tp_order_id} of order {order_id}")
                    try:
                        # Recursively cancel the TP leg but don't raise exceptions if already canceled
                        self.cancel_order(tp_order_id)
                    except Exception as e:
                        self.LOGGER.error(f"Could not cancel TP leg: {e}")

                if order['legs'].get('stop_loss'):
                    sl_order_id = order['legs']['stop_loss']['order_id']
                    self.LOGGER.debug(
                        f"Canceling stop loss leg {sl_order_id} of order {order_id}")
                    try:
                        # Recursively cancel the SL leg but don't raise exceptions if already canceled
                        self.cancel_order(sl_order_id)
                    except Exception as e:
                        self.LOGGER.error(f"Could not cancel SL leg: {e}")

            return order

        # If not found directly, check if this is a TP or SL leg of another order
        for parent_id, parent_order in self.Orders.items():
            if parent_order.get('legs'):
                # Check if this is a take profit leg
                if parent_order['legs'].get('take_profit') and parent_order['legs']['take_profit'].get('order_id') == order_id:
                    # Check if the order is already filled or closed
                    # if parent_order['status'] == ITradeUpdateEvent.FILLED or parent_order['status'] == ITradeUpdateEvent.CLOSED:
                    if parent_order['legs']['take_profit']['status'] == ITradeUpdateEvent.FILLED or parent_order['legs']['take_profit']['status'] == ITradeUpdateEvent.CLOSED:
                        # print(f"Cannot cancel order {parent_id} because it is already {parent_order['status']}")
                        raise BaseException({
                            "code": "already_filled",
                            "data": {"order_id": parent_id, "status": parent_order['status']}
                        })
                    else:
                        self.LOGGER.debug(
                            f"Order {order_id} is a take profit leg of {parent_id}, removing reference")
                        # Remove the take profit leg reference
                        del parent_order['legs']['take_profit']
                        return self.get_order(order_id) or {'order_id': order_id, 'status': ITradeUpdateEvent.CANCELED}

                # Check if this is a stop loss leg
                if parent_order['legs'].get('stop_loss') and parent_order['legs']['stop_loss'].get('order_id') == order_id:
                    # Check if the order is already filled or closed
                    # if parent_order['status'] == ITradeUpdateEvent.FILLED or parent_order['status'] == ITradeUpdateEvent.CLOSED:
                    if parent_order['legs']['stop_loss']['status'] == ITradeUpdateEvent.FILLED or parent_order['legs']['stop_loss']['status'] == ITradeUpdateEvent.CLOSED:
                        # self.LOGGER.debug(f"Cannot cancel order {parent_id} because it is already {parent_order['status']}")
                        raise BaseException({
                            "code": "already_filled",
                            "data": {"order_id": parent_id, "status": parent_order['status']}
                        })
                    else:
                        self.LOGGER.debug(
                            f"Order {order_id} is a stop loss leg of {parent_id}, removing reference")
                        # Remove the stop loss leg reference
                        del parent_order['legs']['stop_loss']
                        return self.get_order(order_id) or {'order_id': order_id, 'status': ITradeUpdateEvent.CANCELED}

        # Order Id not found
        raise BaseException({
            "code": "order_not_found",
            "data": {"order_id": order_id}
        })

    def update_order(self, order_id: str, price: float,  qty: float):
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
                order['qty'] = qty
                order['limit_price'] = price
                self.UPDATE_ORDERS.append(order)
                return order
        else:
            # check legs
            for i, leg_order in self.Orders.items():
                if leg_order['legs'] != None and leg_order not in self.CANCELED_ORDERS and (leg_order['status'] != ITradeUpdateEvent.CANCELED and leg_order['status'] != ITradeUpdateEvent.CLOSED):
                    if leg_order['legs'].get('take_profit'):
                        if leg_order['legs']['take_profit']['order_id'] == order_id:
                            # remove the take profit leg
                            self.Orders[i]['legs']['take_profit']['limit_price'] = price
                            self.Orders[i]['legs']['take_profit']['qty'] = qty
                            self.Orders[i]['legs']['take_profit']["updated_at"] = self.get_current_time
                            self.UPDATE_ORDERS.append(self.Orders[i])
                            return self.Orders[i]

                    if leg_order['legs'].get('stop_loss'):
                        if leg_order['legs']['stop_loss']['order_id'] == order_id:
                            self.Orders[i]['legs']['stop_loss']['limit_price'] = price
                            self.Orders[i]['legs']['stop_loss']['qty'] = qty
                            self.Orders[i]['legs']['stop_loss']["updated_at"] = self.get_current_time
                            self.UPDATE_ORDERS.append(self.Orders[i])
                            return self.Orders[i]

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

    async def startTradeStream(self, callback):
        await super().startTradeStream(callback)
        if self.MODE == IStrategyMode.BACKTEST:
            # trade stream for all of the pending, filled, canceled oerders.
            while self.get_current_time <= self.END_DATE and self.RUNNING_TRADE_STREAM:
                self.LOGGER.debug("trade: waiting for insight for step %s", self.BACKTEST_FlOW_CONTROL._step_id)
                self.LOGGER.debug("DEBUG: Entering wait_for_insight")
                await self.BACKTEST_FlOW_CONTROL.wait_for_insight()
                self.LOGGER.debug("DEBUG: Exited wait_for_insight")
                self.LOGGER.debug("trade: processing orders for step %s", self.BACKTEST_FlOW_CONTROL._step_id)

                try:
                    await self.processUpdateOrders(callback)
                    await self.processClosedOrders(callback)
                    await self.processCanceledOrders(callback)
                    await self.processPendingOrders(callback)
                    await self.processActiveOrders(callback)
                    # perform any order updates again
                    await self.processUpdateOrders(callback)
                    await self.processCanceledOrders(callback)
                    # Run barrier in a thread so it doesn't block the async loop
                except BaseException as e:
                    self.LOGGER.debug(f"DEBUG: startTradeStream caught exception type: {type(e)}")
                    if isinstance(e, asyncio.CancelledError):
                         self.LOGGER.info("startTradeStream cancelled")
                    else:
                         self.LOGGER.exception("Error processing orders in trade stream", e)
                    raise
                finally:
                    self.LOGGER.debug("DEBUG: startTradeStream inner finally block")
                # signal trade done for this timestep
                await self.BACKTEST_FlOW_CONTROL.report_trade()
                self.LOGGER.debug("trade: reported trade for step %s", self.BACKTEST_FlOW_CONTROL._step_id)

                # optionally wait a tiny bit to yield
                await asyncio.sleep(0)
            try:
                self.BACKTEST_FlOW_CONTROL.close()
            except Exception:
                self.LOGGER.exception("Failed to close BACKTEST_FlOW_CONTROL cleanly")
            self.LOGGER.debug("DEBUG: startTradeStream OUTER finally block - EXITING")

        else:
            # live paper trade stream
            while self.RUNNING_TRADE_STREAM:
                try:
                    await self.processUpdateOrders(callback)
                    await self.processClosedOrders(callback)
                    await self.processCanceledOrders(callback)
                    await self.processPendingOrders(callback)
                    await self.processActiveOrders(callback)
                    # perform any order updates again
                    await self.processUpdateOrders(callback)
                    await self.processCanceledOrders(callback)
                except Exception as e:
                    self.LOGGER.error("Error: ", e)
                    continue
                asyncio.sleep(1)
        self.LOGGER.info("End of Trade Stream")
        return

    async def processUpdateOrders(self, callback: Awaitable):
        for i, order in enumerate(self.UPDATE_ORDERS):
            updateOrder = order.copy()
            self.LOGGER.debug("Processing update order: ", updateOrder['order_id'])
            updateOrder['status'] = ITradeUpdateEvent.REPLACED
            await callback(ITradeUpdate(updateOrder, updateOrder['status']))
            self.UPDATE_ORDERS.remove(order)

    async def processPendingOrders(self, callback: Awaitable):
        """ Process pending orders that are either new or accepted.
        This method checks the current market conditions and fills market orders immediately.
        It also processes limit orders based on the current bar's high and low prices.
        """
        # Allowed order states
        allowed_states = [ITradeUpdateEvent.NEW,
                          ITradeUpdateEvent.ACCEPTED, ITradeUpdateEvent.PENDING_NEW]
        idx = 0
        # Iterate through pending orders
        # for i, order in enumerate(self.PENDING_ORDERS):
        while idx < len(self.PENDING_ORDERS):
            order = self.PENDING_ORDERS[idx]

            # Check if order has been canceled and is not already filled or closed
            if any(canceled_order['order_id'] == order['order_id'] for canceled_order in self.CANCELED_ORDERS):
                # Only skip if the order is not already filled or closed
                if order['status'] != ITradeUpdateEvent.FILLED and order['status'] != ITradeUpdateEvent.CLOSED:
                    self.PENDING_ORDERS.remove(order)
                    self.LOGGER.debug(
                        f"Skipping processing of canceled order {order['order_id']} in PENDING_ORDERS")
                    continue

            if order['status'] not in allowed_states or (order not in self.PENDING_ORDERS):
                self.PENDING_ORDERS.remove(order)
                continue

            currentBar = self._get_current_bar(
                order['asset']['symbol'])
            if currentBar is None:
                idx += 1
                continue
            currentBar = currentBar.iloc[0]

            if ((order['status'] == ITradeUpdateEvent.NEW) or (order['created_at'] == self.get_current_time)):
                order['status'] = ITradeUpdateEvent.NEW
                self._update_order(order)

                await callback(ITradeUpdate(order, order['status']))
                
                order['status'] = ITradeUpdateEvent.PENDING_NEW

            if order['type'] == IOrderType.MARKET:
                # Market order - FILLED at the current close price
                order['filled_price'] = currentBar.open
                order['filled_qty'] = order['qty']
                order['status'] = ITradeUpdateEvent.FILLED
                order['filled_at'] = self.get_current_time
                order['updated_at'] = self.get_current_time

                try:
                    self._update_order(order)
                    await callback(ITradeUpdate(order, order['status']))
                except BaseException as e:
                    if e.code == "insufficient_funds":
                        self.LOGGER.warning("Error: ", e)
                    order['status'] = ITradeUpdateEvent.REJECTED
                    order['filled_at'] = None
                    order['filled_price'] = None
                    order['filled_qty'] = None
                    order['updated_at'] = self.get_current_time
                    self.PENDING_ORDERS.remove(order)
                    await callback(ITradeUpdate(order, order['status']))
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
                        await callback(ITradeUpdate(order, order['status']))
                    except BaseException as e:
                        if e.code == "insufficient_funds":
                            self.LOGGER.error("Error: ", e)
                        order['status'] = ITradeUpdateEvent.REJECTED
                        order['filled_at'] = None
                        order['filled_price'] = None
                        order['filled_qty'] = None
                        order['updated_at'] = self.get_current_time
                        self.PENDING_ORDERS.remove(order)
                        await callback(ITradeUpdate(order, order['status']))
                    continue
            idx += 1

    async def processActiveOrders(self, callback: Awaitable):
        """ Process active orders that are either filled or partially filled.
        This method checks for take profit and stop loss conditions and updates the order status accordingly.
        It also updates the position information and calculates the P&L for filled positions.
        """
        # Allowed order states
        allowed_states = [ITradeUpdateEvent.FILLED,
                          ITradeUpdateEvent.PARTIAL_FILLED]
        for i, order in enumerate(list(self.ACTIVE_ORDERS)):
            if order['status'] not in allowed_states or (order not in self.ACTIVE_ORDERS):
                self.ACTIVE_ORDERS.remove(order)
                continue
            # update the position information as the position is filled and keep track of all  positions PNL
            self._update_position(order)

            # check if the order has take profit or stop loss
            if order['legs']:
                currentBar = self._get_current_bar(
                    order['asset']['symbol'])
                if currentBar is None:
                    continue
                currentBar = currentBar.iloc[0]

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
                        await callback(ITradeUpdate(order, order['status']))
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
                        await callback(ITradeUpdate(order,  order['status']))
                        continue
            else:
                # USually a market order or limit order without take profit or stop loss
                continue

    async def processClosedOrders(self, callback: Awaitable):
        """ Process closed orders that are either filled or closed.
        This method updates the order status to CLOSED and sets the stop price to the current bar's open price.
        It also updates the filled quantity and filled at time.
        """
        # Allowed order states
        allowed_states = [ITradeUpdateEvent.CLOSED, ITradeUpdateEvent.FILLED]
        for i, order in enumerate(list(self.CLOSE_ORDERS)):
            if (order['status'] not in allowed_states) or (order not in self.CLOSE_ORDERS):
                self.CLOSE_ORDERS.remove(order)
                continue

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

            await callback(ITradeUpdate(order, order['status']))

    async def processCanceledOrders(self, callback: Awaitable):
        """ Process canceled orders that are either canceled or pending new.
        This method cancels pending orders and removes it from the PENDING_ORDERS and UPDATE_ORDERS.
        """
        # Allowed order states
        allowed_states = [ITradeUpdateEvent.CANCELED,
                          ITradeUpdateEvent.ACCEPTED, ITradeUpdateEvent.PENDING_NEW]
        try: 
            for i, order in enumerate(self.CANCELED_ORDERS):
                if order['status'] not in allowed_states or (order not in self.CANCELED_ORDERS):
                    self.CANCELED_ORDERS.remove(order)
                    continue

                if order in self.PENDING_ORDERS:
                    self.PENDING_ORDERS.remove(order)
                    self.LOGGER.debug(
                        f"Removed canceled order {order['order_id']} from PENDING_ORDERS")
                if order in self.UPDATE_ORDERS:
                    self.UPDATE_ORDERS.remove(order)
                    self.LOGGER.debug(
                        f"Removed canceled order {order['order_id']} from UPDATE_ORDERS")

                if (order['status'] != ITradeUpdateEvent.FILLED and order['status'] != ITradeUpdateEvent.CLOSED):
                    order['status'] = ITradeUpdateEvent.CANCELED
                    order['updated_at'] = self.get_current_time
                    self._update_order(order)

                    await callback(ITradeUpdate(order, order['status']))
                else:
                    # If the order is already FILLED or CLOSED, remove it from CANCELED_ORDERS
                    # but don't change its status or remove from ACTIVE_ORDERS
                    self.LOGGER.debug(
                        f"Order {order['order_id']} is already {order['status']}, removing from CANCELED_ORDERS only")
                    self.CANCELED_ORDERS.remove(order)
        except Exception as e:
            self.LOGGER.info(f"error in processCanceledOrders: {e}")

    async def closeTradeStream(self):
        await super().closeTradeStream()
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
                            assert order['side'] == IOrderSide.SELL, "Order side must be SELL for closing a BUY position"
                            self.Positions[symbol][orderId]['qty'] = np.round(self.Positions[symbol][orderId]['qty'] - order['qty'], 8)
                        elif self.Positions[symbol][orderId]['side'] == IOrderSide.SELL:
                            assert order['side'] == IOrderSide.BUY, "Order side must be BUY for closing a SELL position"
                            self.Positions[symbol][orderId]['qty'] = np.round(self.Positions[symbol][orderId]['qty'] + order['qty'], 8)

                        # Calculate realized P&L and update account
                        entryPrice = order['filled_price'] if order[
                            'filled_price'] != None else self.Positions[symbol][orderId]['avg_entry_price']
                        closePrice = order['stop_price']

                        # Calculate realized P&L based on position side
                        if self.Positions[symbol][orderId]['side'] == IOrderSide.BUY:
                            # For long positions: (close_price - entry_price) * qty
                            realized_pl = (
                                closePrice - entryPrice) * order['qty']
                        else:
                            # For short positions: (entry_price - close_price) * qty
                            realized_pl = (
                                entryPrice - closePrice) * order['qty']

                        # Update cash with realized P&L and return of margin
                        margin_used = np.round(
                            (order['qty'] * entryPrice) / self.LEVERAGE, 2)
                        # self.ACCOUNT.cash += margin_used + realized_pl

                        # Update equity with realized P&L (margin was already counted in equity)
                        # self.ACCOUNT.equity += realized_pl
                        # TODO: factor in commission?
                        self.ACCOUNT.cash += realized_pl

                        self.LOGGER.debug(
                            f"[AUDIT] Realized P&L: {realized_pl}, Margin Released: {margin_used}")

                        if self.Account.cash <= 0:
                            # No buying power left close the position
                            order['status'] = ITradeUpdateEvent.CANCELED
                            self.CANCELED_ORDERS.append(order)
                            raise BaseException({
                                "code": "insufficient_funds",
                                "data": {"order_id": order['order_id']}
                            })

                    else:
                        self.LOGGER.debug("Order Close Without stop_price:", order)

        else:
            match order['status']:
                case ITradeUpdateEvent.FILLED:
                    # add positions dictionary
                    marginRequired = order['qty'] * order['filled_price']
                    if self.Account.cash < marginRequired/self.LEVERAGE:
                        # Not enough buying power
                        try:
                            self.cancel_order(order['order_id'])
                        except BaseException as e:
                            logging.error(
                                "Not enough BP - Position Update Init:", e)

                        return

                    entryPrice = order['filled_price'] if order['filled_price'] != None else currentBar.close
                    market_value = entryPrice * order['qty']
                    self.Positions[symbol][orderId] = IPosition(
                        asset=order['asset'],
                        avg_entry_price=entryPrice,
                        qty=order['qty'] if order['side'] == IOrderSide.BUY else -order['qty'],
                        side=order['side'],
                        market_value=market_value,
                        cost_basis=market_value,
                        current_price=entryPrice,
                        unrealized_pl=0
                    )

                    # Deduct margin requirement from cash (affects buying power)
                    margin_required = np.round(marginRequired/self.LEVERAGE, 2)
                    self.LOGGER.debug(f"[AUDIT] New position margin requirement: {margin_required}")
                    # self.ACCOUNT.equity -= margin_required
                    # TODO: factor in commission on cash?
                    # Equity doesn't change when opening a position (just moving assets)
                    # Track this margin requirement for future reference
                    self.Positions[symbol][orderId]['margin_required'] = margin_required
                    self.update_account_balance()

                case ITradeUpdateEvent.CANCELED:
                    # Order will just be canceled
                    pass

        if oldPosition is not None:
            # Always update to latest price
            self.Positions[symbol][orderId]['current_price'] = currentBar.close if not order.get(
                'stop_price') else order['stop_price']

            # --- BEGIN AUDIT LOGGING ---
            # before_cash = self.Account.cash
            # before_equity = self.Account.equity
            # self.LOGGER.debug(f"[AUDIT] OrderID: {orderId}, Symbol: {symbol}, Side: {order.get('side')}, Qty: {order.get('qty')}, Price: {order.get('filled_price', None) or order.get('stop_price', None)}, Status: {order.get('status')}, BEFORE cash: {before_cash}, BEFORE equity: {before_equity}")
            # --- END AUDIT LOGGING ---

            if order['status'] == ITradeUpdateEvent.CLOSED:
                # Check if quantity is effectively zero
                if np.isclose(self.Positions[symbol][orderId]['qty'], 0, atol=1e-8):
                    # remove the position from the Positions dictionary
                    del self.Positions[symbol][orderId]
                    self.LOGGER.debug(f"[AUDIT] Position {orderId} for {symbol} removed due to zero qty (CLOSED)")
                # --- LOG POST-CLOSE ---
                self.LOGGER.debug(
                    f"[AUDIT] CLOSED OrderID: {orderId}, AFTER cash: {self.Account.cash}, AFTER equity: {self.Account.equity}")
                return

            # Only update if price has changed
            if self.Positions[symbol][orderId]['current_price'] == oldPosition.get('current_price') and order['status'] != ITradeUpdateEvent.CLOSED:
                return

            # Update the position market value and unrealized PnL based on current data
            side = self.Positions[symbol][orderId]['side']
            curr_qty = self.Positions[symbol][orderId]['qty']
            curr_price = self.Positions[symbol][orderId]['current_price']
            cost_basis = self.Positions[symbol][orderId].get('cost_basis', 0)
            avg_entry = self.Positions[symbol][orderId]['avg_entry_price']

            # Calculate market value
            self.Positions[symbol][orderId]['market_value'] = curr_price * \
                np.abs(curr_qty)

            # Calculate unrealized P&L properly based on position side
            if side == IOrderSide.BUY:
                # Long position: (current_price - avg_entry) * qty
                self.Positions[symbol][orderId]['unrealized_pl'] = (
                    curr_price - avg_entry) * np.abs(curr_qty)
            else:
                # Short position: (avg_entry - current_price) * qty
                self.Positions[symbol][orderId]['unrealized_pl'] = (
                    avg_entry - curr_price) * np.abs(curr_qty)

            # Calculate change in unrealized P&L
            changeInPL = round(
                self.Positions[symbol][orderId]['unrealized_pl'] - oldPosition.get('unrealized_pl', 0), 2)

            # Update equity with unrealized P&L changes
            self.update_account_balance()

            # --- LOG POST-UPDATE ---
            self.LOGGER.debug(f"[AUDIT] OrderID: {orderId}, AFTER cash: {self.Account.cash}, AFTER equity: {self.Account.equity}, ChangeInPL: {changeInPL}, Unrealized PL: {self.Positions[symbol][orderId]['unrealized_pl']}")

            # Cleanup zero quantity positions
            if np.isclose(self.Positions[symbol][orderId]['qty'], 0, atol=1e-8):
                del self.Positions[symbol][orderId]
                self.LOGGER.debug(f"[AUDIT] Position {orderId} for {symbol} removed due to zero qty (UPDATE)")

        else:
            return

    def _log_signal(self, order: IOrder, signalType: Literal['entry', 'exit']):
        """
        Logs entry/exit signals for both BUY and SELL sides with proper DCA support.
        Ensures price and qty columns are set correctly, prioritizes DCA accumulation over position closure conflicts.
        """
        symbol = order['asset']['symbol']
        bar = self._get_current_bar(symbol)
        if bar is None:
            # No bar found for this symbol/time
            return
        currentBarIndex = bar.index
        signals = self.HISTORICAL_DATA[symbol]['signals']

        # Check if this is DCA accumulation (same direction as existing position)
        current_position = self.get_position(symbol)
        is_dca_accumulation = False
        if current_position and signalType == 'entry':
            current_qty = current_position.get('qty', 0)
            is_dca_accumulation = ((order['side'] == IOrderSide.BUY and current_qty > 0) or
                                   (order['side'] == IOrderSide.SELL and current_qty < 0))

        # Handle signal logging with DCA priority
        qty = order.get('filled_qty', order.get('qty', 0))

        if signalType == 'entry':
            targetBarIndex = currentBarIndex
            
            # Check for conflicts (Reversal: Exit + Entry on same bar)
            # If we are entering, but there is already an exit on this bar, it's a reversal.
            # VBT can't handle both on same bar, so shift entry to next bar.
            conflict = False
            
            # DEBUG PRINTS (commented - enable if needed)
            # print(f"DEBUG: _log_signal ENTRY {symbol} {order['side']} at {currentBarIndex}")
            # print(f"DEBUG: Exits: {signals.loc[currentBarIndex, 'exits']}, Short Exits: {signals.loc[currentBarIndex, 'short_exits']}")

            if order['side'] == IOrderSide.BUY:
                if signals.loc[currentBarIndex, 'exits'].bool():
                    conflict = True
            elif order['side'] == IOrderSide.SELL:
                if signals.loc[currentBarIndex, 'short_exits'].bool():
                    conflict = True
            
            # if conflict:
            #     print(f"DEBUG: Conflict detected for {symbol} at {currentBarIndex}. DCA: {is_dca_accumulation}")
            
            if conflict and not is_dca_accumulation:
                # Find next bar index
                try:
                    # Get integer location
                    iloc = signals.index.get_loc(currentBarIndex)
                    # Get next location
                    next_iloc = iloc + 1
                    if next_iloc < len(signals.index):
                        targetBarIndex = signals.index[next_iloc]
                        self.LOGGER.debug(f"[VBT] Shifting {order['side']} Entry signal for {symbol} to next bar {targetBarIndex} to avoid conflict with Exit")
                        # print(f"DEBUG: Shifted to {targetBarIndex}")
                    else:
                        self.LOGGER.warning(f"[VBT] Cannot shift Entry signal for {symbol} - end of data")
                        # Fallback: overwrite (VBT will miss the exit, but better than crashing)
                except Exception as e:
                    self.LOGGER.error(f"Error shifting signal: {e}")

            if order['side'] == IOrderSide.BUY:
                # For DCA: if conflicting exit exists (and not shifted), prioritize entry (accumulation)
                if targetBarIndex == currentBarIndex and signals.loc[targetBarIndex, 'exits'].bool():
                    if is_dca_accumulation:
                        self.LOGGER.debug(
                            f"[DCA] Prioritizing BUY entry over exit for {symbol} - DCA accumulation")
                        signals.loc[targetBarIndex, 'exits'] = False
                    else:
                        # This should be handled by shift above, but if shift failed or logic gap:
                        self.LOGGER.debug(
                            f"[DCA] Skipping BUY entry for {symbol} - conflicting exit signal")
                        return
                signals.loc[targetBarIndex, 'entries'] = True
                signals.loc[targetBarIndex, 'qty'] += abs(qty)

            elif order['side'] == IOrderSide.SELL:
                # For DCA: if conflicting short exit exists (and not shifted), prioritize entry (accumulation)
                if targetBarIndex == currentBarIndex and signals.loc[targetBarIndex, 'short_exits'].bool():
                    if is_dca_accumulation:
                        self.LOGGER.debug(
                            f"[DCA] Prioritizing SELL entry over short exit for {symbol} - DCA accumulation")
                        signals.loc[targetBarIndex, 'short_exits'] = False
                    else:
                         # This should be handled by shift above
                        self.LOGGER.debug(
                            f"[DCA] Skipping SELL entry for {symbol} - conflicting short exit signal")
                        return
                signals.loc[targetBarIndex, 'short_entries'] = True
                signals.loc[targetBarIndex, 'qty'] -= abs(qty)

            # Set the entry price
            if order.get('filled_price') is not None and not np.isnan(order['filled_price']):
                signals.loc[targetBarIndex, 'price'] = order['filled_price']

        elif signalType == 'exit':
            if order['side'] == IOrderSide.SELL:
                # Clear conflicting entry if this is a true position closure
                if signals.loc[currentBarIndex, 'entries'].bool():
                    self.LOGGER.debug(
                        f"[DCA] Exit SELL clearing conflicting entry for {symbol}")
                    signals.loc[currentBarIndex, 'entries'] = False
                signals.loc[currentBarIndex, 'exits'] = True
                signals.loc[currentBarIndex, 'qty'] -= abs(qty)

            elif order['side'] == IOrderSide.BUY:
                # Clear conflicting short entry if this is a true position closure
                if signals.loc[currentBarIndex, 'short_entries'].bool():
                    self.LOGGER.debug(
                        f"[DCA] Exit BUY clearing conflicting short entry for {symbol}")
                    signals.loc[currentBarIndex, 'short_entries'] = False
                signals.loc[currentBarIndex, 'short_exits'] = True
                signals.loc[currentBarIndex, 'qty'] += abs(qty)

            # Set the exit price (prefer stop_price, fallback to filled_price)
            exit_price = order.get('stop_price')
            if exit_price is None or np.isnan(exit_price):
                exit_price = order.get('filled_price')
            if exit_price is not None and not np.isnan(exit_price):
                signals.loc[currentBarIndex, 'price'] = exit_price

        # Final validation: VectorBT cannot handle overlapping signals on same bar
        # This should rarely trigger now with improved logic above
        if (signals.loc[currentBarIndex, 'entries'].bool() and
                signals.loc[currentBarIndex, 'exits'].bool()):
            self.LOGGER.debug(
                f"[VBT] Warning: Still have conflicting long signals for {symbol} on same bar - clearing exit")
            signals.loc[currentBarIndex, 'exits'] = False

        if (signals.loc[currentBarIndex, 'short_entries'].bool() and
                signals.loc[currentBarIndex, 'short_exits'].bool()):
            self.LOGGER.debug(
                f"[VBT] Warning: Still have conflicting short signals for {symbol} on same bar - clearing short exit")
            signals.loc[currentBarIndex, 'short_exits'] = False

    def _update_order(self, order: IOrder):
        if self.Orders.get(order['order_id']):
            oldOrder = self.Orders[order['order_id']].copy()
        else:
            oldOrder = None

        def onNewOrder():
            # Add the new order to the pending orders queue
            if not oldOrder:
                """ Check if the order is affecting any active orders as it might be an order to close a position and update the active orders accordingly"""
                current_position = self.get_position(order['asset']['symbol'])

                if current_position:
                    # Check if this is DCA accumulation (same direction) or position closure/reversal
                    current_qty = current_position.get('qty', 0)
                    is_dca_accumulation = ((order['side'] == IOrderSide.BUY and current_qty > 0) or
                                           (order['side'] == IOrderSide.SELL and current_qty < 0))

                    if is_dca_accumulation:
                        # This is DCA accumulation - don't treat as position closure
                        # Simply add to pending orders and let it accumulate
                        self.LOGGER.debug(
                            f"[DCA] Order for {order['asset']['symbol']} is DCA accumulation - allowing to proceed")
                        self.PENDING_ORDERS.append(order)
                        return

                    # Handle position closure/reversal logic (existing logic for opposite direction orders)
                    self.LOGGER.debug(
                        f"[DCA] Order for {order['asset']['symbol']} is opposite direction - handling as closure/reversal")
                    tempCloseOrder = order.copy()
                    conflicting = False
                    # self.LOGGER.debug(f"[AUDIT] Processing new order {order['order_id']} {order['asset']['symbol']} {order['side']} {order['qty']}. Active orders: {len(self.ACTIVE_ORDERS)}")
                    for i, activeOrder in enumerate(list(self.ACTIVE_ORDERS)):
                        # self.LOGGER.debug(f"[AUDIT] Checking vs {activeOrder['order_id']} {activeOrder['asset']['symbol']} {activeOrder['side']} {activeOrder['qty']} {activeOrder['status']}")
                        if activeOrder['asset']['symbol'] == order['asset']['symbol'] and \
                                activeOrder['side'] != order['side'] and \
                                (activeOrder['status'] == ITradeUpdateEvent.FILLED or activeOrder['status'] == ITradeUpdateEvent.PARTIAL_FILLED):

                            if order in self.PENDING_ORDERS:
                                # remove the order from the pending orders
                                self.PENDING_ORDERS.remove(order)

                            if np.isclose(activeOrder['qty'], tempCloseOrder['qty'], atol=1e-8):
                                # close the position
                                self.ACTIVE_ORDERS.remove(activeOrder)

                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = activeOrder['filled_qty']
                                tempCloseOrder['status'] = ITradeUpdateEvent.FILLED
                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())
                                tempCloseOrder['qty'] = 0
                                conflicting = True

                            elif (activeOrder['qty'] - tempCloseOrder['qty']) > 1e-8:
                                # partially close the position
                                self.ACTIVE_ORDERS.remove(activeOrder)
                                # reduce the quantity of the active order
                                activeOrder['qty'] = np.round(activeOrder['qty'] - tempCloseOrder['qty'], 8)
                                self.ACTIVE_ORDERS.append(activeOrder)

                                # send the close order to the close orders
                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = tempCloseOrder['qty']
                                tempCloseOrder['status'] = ITradeUpdateEvent.FILLED
                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())
                                tempCloseOrder['qty'] = 0
                                conflicting = True
                            else:
                                # close multiple positions. quantityLeft > 0
                                quantityLeft = np.round(tempCloseOrder['qty'] - activeOrder['qty'], 8)
                                self.ACTIVE_ORDERS.remove(activeOrder)
                                # send the close order for the active order
                                tempCloseOrder['order_id'] = activeOrder['order_id']
                                tempCloseOrder['qty'] = activeOrder['qty']
                                tempCloseOrder['filled_price'] = activeOrder['filled_price']
                                tempCloseOrder['filled_qty'] = tempCloseOrder['qty']
                                tempCloseOrder['status'] = ITradeUpdateEvent.FILLED
                                self.CLOSE_ORDERS.append(tempCloseOrder.copy())
                                tempCloseOrder['qty'] = quantityLeft
                                conflicting = True
                                continue

                            if tempCloseOrder['qty'] == 0:
                                break

                        tempCloseOrder['status'] = ITradeUpdateEvent.PENDING_NEW
                    if tempCloseOrder['qty'] > 0 and conflicting:
                        # Add the order to the pending orders
                        order['qty'] = tempCloseOrder['qty']
                        self.PENDING_ORDERS.append(order)
                        return

                self.PENDING_ORDERS.append(order)

        def onFilledOrder():
            if oldOrder in self.PENDING_ORDERS:
                self.PENDING_ORDERS.remove(oldOrder)

                # update position of the order

                self._update_position(order)
                # Add the order to the active orders
                if self.Positions[order['asset']['symbol']].get(order['order_id']) and self.Positions[order['asset']['symbol']][order['order_id']]['qty'] != 0:
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
                        # Record for VBT from_orders
                        trade_record = {
                            'date': self.get_current_time,
                            'symbol': order['asset']['symbol'],
                            'side': order['side'],
                            'qty': order['filled_qty'],
                            'price': order['filled_price'],
                            'fees': 0.0
                        }
                        self.FILLED_ORDERS_HISTORY.append(trade_record)
                        self.LOGGER.debug(f"[PAPER DEBUG] Entry Order: {trade_record['date']} | {trade_record['side']} {trade_record['qty']} @ ${trade_record['price']:.2f}")

            elif oldOrder in self.ACTIVE_ORDERS:
                # update position of the order
                self._update_position(order)

        def onClosedOrder():
            # This update is already done in the on trade update
            self._update_position(order)

            if self.MODE == IStrategyMode.BACKTEST:
                # log the exit signal
                self._log_signal(order, 'exit')
                # Record for VBT from_orders
                trade_record = {
                    'date': self.get_current_time,
                    'symbol': order['asset']['symbol'],
                    'side': order['side'],
                    'qty': order['filled_qty'],
                    'price': order['filled_price'],
                    'fees': 0.0
                }
                self.FILLED_ORDERS_HISTORY.append(trade_record)
                self.LOGGER.debug(f"[PAPER DEBUG] Exit Order: {trade_record['date']} | {trade_record['side']} {trade_record['qty']} @ ${trade_record['price']:.2f}")

            # Check if the position is completely closed and remove it from the positions dictionary - if the qty is 0 or None
            if self.Positions[order['asset']['symbol']].get(order['order_id']) == None:
                if oldOrder in self.ACTIVE_ORDERS:
                    self.ACTIVE_ORDERS.remove(oldOrder)

                if oldOrder in self.CLOSE_ORDERS:
                    self.CLOSE_ORDERS.remove(oldOrder)
            if order in self.CLOSE_ORDERS:
                # This is when the order was sent and we are closing a position with another order id than the original order id - order is the updated order with the new order id and oldOrder is the original order (in the filled state)
                self.CLOSE_ORDERS.remove(order)

        def onCanceledOrder():
            if oldOrder in self.ACTIVE_ORDERS or order in self.ACTIVE_ORDERS:
                """ Should not really happen as the order state check should be before have already happened when cancelling the order """
                # if order is already filled oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                if oldOrder in self.CANCELED_ORDERS:
                    self.CANCELED_ORDERS.remove(oldOrder)
                if order in self.CANCELED_ORDERS:
                    self.CANCELED_ORDERS.remove(order)

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
        try:
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
        except Exception as e:
            self.LOGGER.warn("Error updating order: ", e)

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
            self.LOGGER.warning(f"Order Type not supported {insight.type}")
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
                if (type(currentBar) == NoneType) or currentBar.empty:
                    return
                currentBar = currentBar.iloc[0]
                orderRequest['limit_price'] = currentBar.close

            marginRequired = orderRequest['qty'] * orderRequest['limit_price']
            buying_power = self.ACCOUNT.buying_power

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
                             "available": self.ACCOUNT.buying_power,
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

            if self.ACCOUNT.cash < (marginRequired/self.LEVERAGE):
                # Not enough buying power
                raise BaseException({
                    "code": "insufficient_funds",
                    "data": {"order_id": order['order_id']}
                })
            self._update_order(order)
            return order

        except BaseException as e:
            raise e

    def format_on_bar(self, bar, symbol: str):
        if self.DataFeed == 'yf':
            assert symbol, 'Symbol must be provided when using yf data feed - format_on_bar()'
            index = pd.MultiIndex.from_product(
                [[symbol], pd.to_datetime(bar.index, utc=True)], names=['symbol', 'timestamp'])

            bar = pd.DataFrame(data={
                'open': np.array(bar['Open'].values).reshape(-1),
                'high': np.array(bar['High'].values).reshape(-1),
                'low': np.array(bar['Low'].values).reshape(-1),
                'close': np.array(bar['Close'].values).reshape(-1),
                'volume': np.array(bar['Volume'].values).reshape(-1),
            }, index=index, columns=['open', 'high', 'low', 'close', 'volume'])
            return bar
        else:
            self.LOGGER.error('DataFeed not supported')
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
        self.LOGGER.info("Applying TA for: ", symbol)
        self.HISTORICAL_DATA[symbol]['bar'].ta.study(asset['TA'])

    def _load_historical_bar_data(self, asset: IMarketDataStream):
        try:
            bar_data_path = None
            symbol = asset['symbol'] if asset.get(
                'feature') == None else asset['feature']
            if asset.get('stored') and asset.get('stored_path'):
                bar_data_path = asset['stored_path'] + \
                    f'/bar/{asset["symbol"]}_{asset["time_frame"]
                                              }_{self.START_DATE}-{self.END_DATE}.h5'

            if asset.get('stored'):
                if asset['stored_path']:
                    if os.path.exists(bar_data_path):
                        self.LOGGER.info("Loading data from ", bar_data_path)
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
                        self.LOGGER.info(
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
            self.LOGGER.error("Error: ", e.args[0]['code'], e.args[0]['data']['path'])

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

            self.LOGGER.info("Loaded data for ", symbol)
            self.LOGGER.info(self.HISTORICAL_DATA[symbol]['bar'].describe())
            # if a stored path is provided save the data to the path
            if asset.get('stored_path'):
                # Create the directory if it does not exist
                Path(asset['stored_path']+'/bar').mkdir(
                    parents=True, exist_ok=True)
                # Save the data to the path
                self.LOGGER.info(self.HISTORICAL_DATA[symbol]['bar'].head(10))

                # Save the data to the path in hdf5 format
                self.LOGGER.info("Saving data to ", bar_data_path)
                self.HISTORICAL_DATA[symbol]['bar'].to_hdf(
                    bar_data_path, mode='a', key=asset["exchange"], index=True, format='table')

            return True

        else:
            self.LOGGER.error('DataFeed not supported')
    async def streamMarketData(self, callback, assetStreams):
        """Listen to market data and call the async callback with the data.

        Important: `callback` must be an async callable: `async def callback(bar, timeframe=...)`.
        """
        await super().streamMarketData(callback, assetStreams)  # keep any parent logic
        TF = None

        # -------------------
        # BACKTEST mode
        # -------------------
        if self.MODE == IStrategyMode.BACKTEST:
            # load historical data
            for asset in assetStreams:
                try:
                    symbol = asset.get("feature") or asset["symbol"]
                    if asset["type"] != "bar":
                        continue
                    else:
                        self.HISTORICAL_DATA[symbol] = {}

                    # run load in a thread to avoid blocking event loop
                    loaded = await asyncio.to_thread(self._load_historical_bar_data, asset)
                    if not loaded:
                        assetStreams.remove(asset)
                        continue

                    # set up signals dataframe synchronously (cheap)
                    if asset.get("feature") is None:
                        bar_df = self.HISTORICAL_DATA[symbol]["bar"]
                        size = bar_df.shape[0]
                        signals_df = pd.DataFrame(
                            {
                                "entries": np.zeros(size),
                                "short_entries": np.zeros(size),
                                "exits": np.zeros(size),
                                "short_exits": np.zeros(size),
                                "price": np.zeros(size),
                                "qty": np.zeros(size),
                            },
                            index=bar_df.index,
                        )
                        signals_df[["entries", "exits", "short_entries", "short_exits"]] = False
                        signals_df[["qty"]] = 0
                        signals_df[["price"]] = np.nan
                        self.HISTORICAL_DATA[symbol]["signals"] = signals_df
                        if TF is None:
                            TF = asset["time_frame"]
                    else:
                        # feature renaming / multiindex handling (do in thread if heavy)
                        await asyncio.to_thread(
                            self.HISTORICAL_DATA[symbol]["bar"].rename,
                            index={asset["symbol"]: symbol},
                            inplace=True,
                        )
                        hasFeature = True
                except Exception as e:
                    self.LOGGER.exception("Error loading historical data for %s: %s", asset.get("symbol"), e)
                    try:
                        assetStreams.remove(asset)
                    except ValueError:
                        pass
                    continue

             # Determine list of bar assets
            
            bar_assets = [a for a in assetStreams if a.get("type") == "bar"]
            market_parties = len(bar_assets)
            await self.BACKTEST_FlOW_CONTROL.update_market_parties(market_parties)
            if not self.HISTORICAL_DATA:
                self.LOGGER.error("No historical data loaded, aborting market stream.")
                self.RUNNING_MARKET_STREAM = False
                return

            # Main backtest streaming loop
            if self.VERBOSE > 0:
                import datetime, timeit
                self.LOGGER.debug(f"Running Backtest - {datetime.datetime.now()}")
                start_time = timeit.default_timer()

            try:
                while self.RUNNING_MARKET_STREAM and self.get_current_time <= self.END_DATE:
                    if self.VERBOSE > 0:
                        self.LOGGER.debug(f"\nstreaming data for: {self.get_current_time} \n")

                    # For each asset, find bars between PreviousTime and current time
                    for asset in bar_assets:
                        try:
                            symbol = asset.get("feature") or asset["symbol"]
                            is_feature = asset.get("feature") is not None

                            if is_feature:
                                if self.PreviousTime is None:
                                    mask = (
                                        (self.HISTORICAL_DATA[symbol]["bar"].index.get_level_values("timestamp")
                                        >= self.get_current_time.replace(tzinfo=datetime.timezone.utc))
                                        & (self.HISTORICAL_DATA[symbol]["bar"].index.get_level_values("timestamp")
                                        <= self.get_current_time.replace(tzinfo=datetime.timezone.utc))
                                    )
                                else:
                                    mask = (
                                        (self.HISTORICAL_DATA[symbol]["bar"].index.get_level_values("timestamp")
                                        > self.PreviousTime.replace(tzinfo=datetime.timezone.utc))
                                        & (self.HISTORICAL_DATA[symbol]["bar"].index.get_level_values("timestamp")
                                        <= self.get_current_time.replace(tzinfo=datetime.timezone.utc))
                                    )
                                barDatas = self.HISTORICAL_DATA[symbol]["bar"].loc[mask]
                                if barDatas is None or getattr(barDatas, "empty", False):
                                    continue

                                # iterate rows and await callback
                                for index in barDatas.index:
                                    try:
                                        await callback(barDatas.loc[[index]], timeframe=asset["time_frame"])
                                    except Exception:
                                        self.LOGGER.exception("Error streaming bar back to strategy")
                                        continue
                            else:
                                # non-feature: get the current bar (assume _get_current_bar is lightweight)
                                barData = await asyncio.to_thread(self._get_current_bar, symbol)
                                if barData is None or barData.empty:
                                    continue
                                await callback(barData, timeframe=asset["time_frame"])
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            self.LOGGER.exception("Error producing bars for asset %s", asset.get("symbol"))
                            continue
                    

                    # signal market done for this timestep
                    self.LOGGER.debug("market step %s: reporting market", self.BACKTEST_FlOW_CONTROL._step_id)
                    await self.BACKTEST_FlOW_CONTROL.report_market()

                    self.LOGGER.debug("market step %s: waiting for trade", self.BACKTEST_FlOW_CONTROL._step_id)
                    # wait for trade processing to complete for this timestep
                    # await self.BACKTEST_FlOW_CONTROL.wait_for_trade()
                    try:
                        await asyncio.wait_for(self.BACKTEST_FlOW_CONTROL.wait_for_trade(), timeout=30.0)
                    except asyncio.TimeoutError:
                        # Trade hasn't completed in time — log and decide whether to continue or abort.
                        self.LOGGER.error("Timeout waiting for trade for timestep %s — aborting backtest step", getattr(self.BACKTEST_FlOW_CONTROL, "_step_id", "n/a"))
                        # Either break or call close() to unblock everything
                        break

                    self.LOGGER.debug("Market: trade step completed, updating account and advancing time")
                    # log accounts etc
                    self.update_account_history()
                    # advance time to next increment
                    self.setCurrentTime(TF.get_next_time_increment(self.get_current_time))

                    # prepare coordinator for next step
                    await self.BACKTEST_FlOW_CONTROL.step_complete()
            
                
            finally:
                # final cleanup
                self.LOGGER.debug("DEBUG: streamMarketData finally block")
                self.RUNNING_MARKET_STREAM = False
                try:
                    self.BACKTEST_FlOW_CONTROL.close()
                except Exception:
                    self.LOGGER.exception("Failed to close BACKTEST_FlOW_CONTROL cleanly")

                if self.VERBOSE > 0:
                    self.LOGGER.debug(f"Backtest Completed: {timeit.default_timer() - start_time}")
        elif  self.MODE == IStrategyMode.LIVE:
            # -------------------
            # LIVE mode
            # -------------------
            # Prepare storage for live streaming
            self.HISTORICAL_DATA = {a["symbol"]: {"bar": pd.DataFrame()} for a in assetStreams if a["type"] == "bar"}

            # create per-asset streamer coroutines and run them concurrently
            async def _paper_bar_streamer(asset):
                lastChecked = pd.Timestamp.now() - datetime.timedelta(minutes=self.FeedDelay)
                while self.RUNNING_MARKET_STREAM:
                    nextTimeToCheck = asset["time_frame"].get_next_time_increment(lastChecked)
                    wait_seconds = (nextTimeToCheck - lastChecked).total_seconds()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                    try:
                        # If _get_current_bar is blocking, run in thread
                        barDatas = await asyncio.to_thread(self._get_current_bar, asset["symbol"], asset["time_frame"], lastChecked)
                        if barDatas is None or getattr(barDatas, "empty", False):
                            lastChecked = nextTimeToCheck
                            continue
                        for idx in range(len(barDatas)):
                            bar = barDatas.iloc[[idx]]
                            if asset["time_frame"].is_time_increment(bar.index[0][1]) and not (bar.index[0][1] < lastChecked.replace(tzinfo=timezone.utc)):
                                # await the async callback directly
                                await callback(bar, timeframe=asset["time_frame"])
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.LOGGER.exception("Error in live market producer for %s", asset["symbol"])
                    lastChecked = nextTimeToCheck

            # spawn tasks and keep them alive
            tasks = []
            for asset in assetStreams:
                if asset["type"] == "bar":
                    task = asyncio.create_task(_paper_bar_streamer(asset), name=f"Market:{asset['symbol']}:{asset['time_frame']}")
                    streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                    self._MARKET_STREAMS[streamKey] = task
                    tasks.append(task)

            if tasks:
                # await them (this will run until tasks are cancelled by the parent TaskGroup)
                try:
                    await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    # graceful cancellation path
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # nothing to stream; return
                return
        else:
            raise NotImplementedError
        return


    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        if self.RUNNING_MARKET_STREAM:
            # _MARKET_STREAMS may nee to be part of the parant class
            for asset in assetStreams:
                streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                marketStream = self._MARKET_STREAMS.get(streamKey, None)
                if marketStream:
                    self.LOGGER.info("Closing Market Stream for: ", streamKey)
                    if type(marketStream) == asyncio.Task:
                        marketStream.cancel(
                            "Relenquishing Market Stream for: " + streamKey)
                    del self._MARKET_STREAMS[streamKey]
                    return True
                if len(self._MARKET_STREAMS) == 0:
                    self.RUNNING_MARKET_STREAM = False
                return True
        return False

    def close_position(self, symbol: str, qty=None, percent=None):
        super().close_position(symbol, qty, percent)

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
                # self.LOGGER.debug("Current Bar: ", currentBar)
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
            previous_time = convert_to_utc(
                lastChecked) if lastChecked else current_time

            find_next_bar(previous_time, current_time)
            if type(currentBar) == NoneType or currentBar.empty:
                try:
                    if not self.TICKER_INFO[symbol]:
                        self.get_ticker_info(symbol)
                    getBarsFrom = timeFrame.add_time_increment(
                        tf_current_time, -2)
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
                # Use FILLED_ORDERS_HISTORY if available
                trade_history = [t for t in self.FILLED_ORDERS_HISTORY if t['symbol'] == asset]
                
                if trade_history:
                    try:
                        self.LOGGER.info(f"Running VBT from orders for {asset} with {len(trade_history)} trades")
                        bar_data = self.HISTORICAL_DATA[asset]['bar']
                        # Drop symbol level to get DatetimeIndex
                        if isinstance(bar_data.index, pd.MultiIndex):
                            bar_index = bar_data.index.droplevel('symbol')
                        else:
                            bar_index = bar_data.index
                        
                        # Initialize arrays
                        size = pd.Series(0.0, index=bar_index)
                        price = pd.Series(np.nan, index=bar_index)
                        
                        # Sort trades by time
                        trade_history.sort(key=lambda x: x['date'])
                        
                        # CRITICAL FIX: Consolidate orders at the SAME timestamp
                        # Problem: Multiple SELLs at 15:08 were being shifted to 15:08, 15:09, 15:10
                        # creating phantom trades in VBT. Solution: sum all orders per timestamp.
                        from collections import defaultdict
                        orders_by_time = defaultdict(lambda: {'qty': 0.0, 'prices': [], 'weights': []})
                        
                        for trade in trade_history:
                            trade_time = pd.Timestamp(trade['date'])
                            qty = trade['qty']
                            if trade['side'] == IOrderSide.SELL:
                                qty = -qty
                            
                            orders_by_time[trade_time]['qty'] += qty
                            orders_by_time[trade_time]['prices'].append(trade['price'])
                            orders_by_time[trade_time]['weights'].append(abs(qty))
                        
                        # Create consolidated order list with weighted average prices
                        consolidated_orders = []
                        for time, data in sorted(orders_by_time.items()):
                            if abs(data['qty']) > 0.01:  # Only include non-zero orders
                                # Weighted average price
                                total_weight = sum(data['weights'])
                                avg_price = sum(p * w for p, w in zip(data['prices'], data['weights'])) / total_weight if total_weight > 0 else data['prices'][0]
                                
                                consolidated_orders.append({
                                    'time': time,
                                    'qty': data['qty'],
                                    'price': avg_price
                                })
                        
                        self.LOGGER.debug(f"\n[VBT DEBUG] Consolidated {len(trade_history)} orders from {len(orders_by_time)} unique timestamps into {len(consolidated_orders)} non-zero orders")
                        
                        # Now track position changes for VBT
                        position_changes = []
                        current_position = 0.0
                        
                        for order in consolidated_orders:
                            new_position = current_position + order['qty']
                            position_change = order['qty']
                            
                            position_changes.append({
                                'time': order['time'],
                                'position_change': position_change,
                                'new_position': new_position,
                                'price': order['price']
                            })
                            current_position = new_position
                        
                        self.LOGGER.debug(f"\n[VBT DEBUG] Consolidated {len(trade_history)} orders into {len(position_changes)} position changes")
                        
                        # Now populate size/price arrays from position changes
                        shifted_count = 0
                        for change in position_changes:
                            trade_time = change['time']
                            
                            # Normalize timezone
                            if bar_index.tz is not None:
                                if trade_time.tz is None:
                                    trade_time = trade_time.tz_localize(bar_index.tz)
                                else:
                                    trade_time = trade_time.tz_convert(bar_index.tz)
                            else:
                                if trade_time.tz is not None:
                                    trade_time = trade_time.tz_localize(None)
                            
                            # Find index
                            if trade_time in bar_index:
                                idx = trade_time
                            else:
                                # Find nearest
                                loc = bar_index.get_indexer([trade_time], method='nearest')[0]
                                idx = bar_index[loc]
                            
                            # If there's already a trade at this timestamp, shift to next bar
                            while idx in size.index and size[idx] != 0:
                                loc = bar_index.get_loc(idx)
                                if loc + 1 < len(bar_index):
                                    idx = bar_index[loc +1]
                                    shifted_count += 1
                                else:
                                    self.LOGGER.warning(f"Warning: Dropping position change at end of data")
                                    break
                            
                            if idx in size.index:
                                size[idx] = change['position_change']
                                price[idx] = change['price']

                        if shifted_count > 0:
                            self.LOGGER.warning(f"Shifted {shifted_count} trades to avoid same-bar conflicts")

                        # Log trade history for comparison  
                        self.LOGGER.debug(f"\n=== VBT DEBUG: Trade History for {asset} ===")
                        self.LOGGER.debug(f"Total orders recorded: {len(trade_history)}")
                        self.LOGGER.debug(f"\nFirst 5 PaperBroker orders:")
                        for i, trade in enumerate(trade_history[:5]):
                            qty_sign = "+" if trade['side'] == IOrderSide.BUY else "-"
                            self.LOGGER.debug(f"  {i}: {trade['date']} | {trade['side'].name} {qty_sign}{trade['qty']} @ ${trade['price']:.2f}")
                        if len(trade_history) > 5:
                            self.LOGGER.debug(f"... and {len(trade_history) - 5} more orders")
                        
                        self.LOGGER.debug(f"\nFirst 5 VBT position changes:")
                        for i, change in enumerate(position_changes[:5]):
                            direction = "LONG" if change['position_change'] > 0 else "SHORT"
                            self.LOGGER.debug(f"  {i}: {change['time']} | {direction} {change['position_change']:+.0f} → Position: {change['new_position']:+.0f} @ ${change['price']:.2f}")
                        if len(position_changes) > 5:
                            self.LOGGER.debug(f"... and {len(position_changes) - 5} more changes")
                        
                        # Log VBT input arrays (first 10 non-zero entries)
                        self.LOGGER.debug(f"\n=== VBT DEBUG: Input Arrays ===")
                        non_zero_size = size[size != 0]
                        self.LOGGER.debug(f"Non-zero size entries: {len(non_zero_size)}")
                        if len(non_zero_size) > 0:
                            self.LOGGER.debug(f"\nFirst 5 VBT orders (size array):")
                            for idx, val in non_zero_size.head().items():
                                direction = "BUY" if val > 0 else "SELL"
                                self.LOGGER.debug(f"  {idx}: {direction} {val:+.0f} @ ${price[idx]:.2f}")

                        vbtParams = {
                            "init_cash": self.STARTING_CASH,
                            "close": bar_data['close'].reset_index(level='symbol', drop=True),
                            "size": size,
                            "price": price,
                            "freq": timeFrame.unit.value[0].lower(),
                        }

                        # run the backtest
                        self.LOGGER.debug("\n=== Running VBT from_orders ===")
                        self.LOGGER.debug(f"Initial cash: ${self.STARTING_CASH:,.2f}")
                        results[asset] = vbt.Portfolio.from_orders(**vbtParams)
                        
                        # Log VBT results
                        self.LOGGER.debug(f"\n=== VBT DEBUG: Portfolio Results ===")
                        self.LOGGER.debug(f"Final value: ${results[asset].final_value():,.2f}")
                        self.LOGGER.debug(f"Total return: {results[asset].total_return():.2%}")
                        self.LOGGER.debug(f"Total trades: {results[asset].trades.count()}")
                        
                        # Show first few trades executed by VBT
                        if results[asset].trades.count() > 0:
                            self.LOGGER.debug(f"\nFirst 3 VBT executed trades:")
                            trades_df = results[asset].trades.records_readable
                            for idx in range(min(3, len(trades_df))):
                                trade = trades_df.iloc[idx]
                                self.LOGGER.debug(f"  {idx}: {trade['Entry Timestamp']} → {trade['Exit Timestamp']} | "
                                      f"Size: {trade['Size']:.0f} | PnL: ${trade['PnL']:.2f} | Return: {trade['Return']:.2%}")
                        
                        print(results[asset].stats(
                            metrics=[*vbt.Portfolio.metrics, expectancy_ratio]))
                            
                    except Exception as e:
                        self.LOGGER.error("Failed to run backtest for ", asset, e)
                        import traceback
                        traceback.print_exc()
                        continue
                
                # Always use from_signals for better control
                if isinstance(self.HISTORICAL_DATA[asset].get('signals'), pd.DataFrame):
                    try:
                        self.LOGGER.info(f"\n=== Running VBT from_signals for {asset} ===")
                        
                        # Log signal statistics
                        signals = self.HISTORICAL_DATA[asset]['signals']
                        self.LOGGER.debug(f"Signal stats:")
                        self.LOGGER.debug(f"  Entries: {signals['entries'].sum()}")
                        self.LOGGER.debug(f"  Short entries: {signals['short_entries'].sum()}")
                        self.LOGGER.debug(f"  Exits: {signals['exits'].sum()}")
                        self.LOGGER.debug(f"  Short exits: {signals['short_exits'].sum()}")
                        
                        # Apply leverage by multiplying size
                        leverage_multiplier = self.LEVERAGE if hasattr(self, 'LEVERAGE') else 1.0                        
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
                            "size":  self.HISTORICAL_DATA[asset]['signals']['qty'].abs().reset_index(level='symbol', drop=True),                            "freq": timeFrame.unit.value[0].lower(),
                            "size_type": "amount",  # Use absolute amounts, not percentages
                            "accumulate": True,  # Enable DCA-style accumulation
                            "upon_opposite_entry": "Reverse",  # Handle reversals properly
                        }

                        # run the backtest
                        results[asset] = vbt.Portfolio.from_signals(**vbtParams)
                        
                        # Log VBT results
                        self.LOGGER.debug(f"\n=== VBT DEBUG: Portfolio Results ===")
                        self.LOGGER.debug(f"Final value: ${results[asset].final_value():,.2f}")
                        self.LOGGER.debug(f"Total return: {results[asset].total_return():.2%}")
                        self.LOGGER.debug(f"Total trades: {results[asset].trades.count()}")
                        self.LOGGER.debug(f"Leverage applied: {leverage_multiplier}x")
                        
                        # Show first few trades executed by VBT with corresponding PaperBroker orders
                        if results[asset].trades.count() > 0:
                            self.LOGGER.debug(f"\n=== Trade Comparison: VBT vs PaperBroker ===")
                            trades_df = results[asset].trades.records_readable
                            
                            for idx in range(min(3, len(trades_df))):
                                trade = trades_df.iloc[idx]
                                self.LOGGER.debug(f"\n--- VBT Trade {idx} ---")
                                self.LOGGER.debug(f"  Entry: {trade['Entry Timestamp']} | Exit: {trade['Exit Timestamp']}")
                                self.LOGGER.debug(f"  Size: {trade['Size']:.0f} | Entry Price: ${trade['Avg Entry Price']:.2f} | Exit Price: ${trade['Avg Exit Price']:.2f}")
                                self.LOGGER.debug(f"  PnL: ${trade['PnL']:.2f} | Return: {trade['Return']:.2%}")
                                
                                # Find corresponding PaperBroker orders
                                entry_time = pd.Timestamp(trade['Entry Timestamp'])
                                exit_time = pd.Timestamp(trade['Exit Timestamp'])
                                
                                # Get PaperBroker orders in this time window (normalize timezone)
                                paper_orders = []
                                for order in self.FILLED_ORDERS_HISTORY:
                                    if order['symbol'] == asset:
                                        order_time = pd.Timestamp(order['date'])
                                        # Normalize timezone
                                        if entry_time.tz is not None and order_time.tz is None:
                                            order_time = order_time.tz_localize(entry_time.tz)
                                        elif entry_time.tz is None and order_time.tz is not None:
                                            order_time = order_time.tz_localize(None)
                                        
                                        if entry_time <= order_time <= exit_time:
                                            paper_orders.append(order)
                                
                                if paper_orders:
                                    self.LOGGER.debug(f"\n  Corresponding PaperBroker orders ({len(paper_orders)}):")
                                    for i, order in enumerate(paper_orders[:5]):  # Show first 5
                                        side_label = "BUY" if order['side'] == IOrderSide.BUY else "SELL"
                                        self.LOGGER.debug(f"    {i}: {order['date']} | {side_label} {order['qty']:.0f} @ ${order['price']:.2f}")
                                else:
                                    self.LOGGER.debug(f"\n  ⚠️  No matching PaperBroker orders found in this time window")
                        
                        print(results[asset].stats(
                            metrics=[*vbt.Portfolio.metrics, expectancy_ratio]))
                    except Exception as e:
                        self.LOGGER.warning("Failed to run backtest for ", asset, e)
                        import traceback
                        traceback.print_exc()
                        continue
                else:
                    self.LOGGER.warning("No signals for feature ", asset)
                    continue
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')
        return results

    def export_trade_log(self, filename="trade_log.csv"):
        import pandas as pd
        rows = []
        for symbol, orders in self.Positions.items():
            for order_id, pos in orders.items():
                rows.append({
                    'symbol': symbol,
                    'order_id': order_id,
                    **pos
                })
        df = pd.DataFrame(rows)
        df.to_csv(filename, index=False)
        self.LOGGER.info(f"[EXPORT] Trade log exported to {filename}")

    def export_vbt_signals(self, asset, filename="vbt_signals.csv"):
        import pandas as pd
        if asset in self.HISTORICAL_DATA and 'signals' in self.HISTORICAL_DATA[asset]:
            df = self.HISTORICAL_DATA[asset]['signals']
            df.to_csv(filename)
            self.LOGGER.info(f"[EXPORT] VBT signals for {asset} exported to {filename}")
        else:
            self.LOGGER.info(f"[EXPORT] No signals found for asset {asset}")

    def update_account_history(self):
        if self.VERBOSE >= 2:
            self.LOGGER.info("Updating Account History")
            self.LOGGER.info("Account: ", self.Account)
        self.ACCOUNT_HISTORY[self.get_current_time] = self.Account

    def update_account_balance(self):
        # Calculate total unrealized P&L across all positions
        # print("[AUDIT] Updating account balance")

        self.ACCOUNT.cash = max(np.round(self.ACCOUNT.cash, 2),0)
        total_unrealized_pl = sum(
            position.get('unrealized_pl', 0)
            for positions in self.Positions.values()
            for position in positions.values()
        )

        # Calculate total market value of all open positions (ignore closed ones)
        total_position_value = sum(
            abs(position.get('market_value', 0))
            for positions in self.Positions.values()
            for position in positions.values()
            if position.get('qty', 0) != 0
        )
        # Debug info: number of open positions and their total market value
        open_positions = [p for positions in self.Positions.values() for p in positions.values() if p.get('qty', 0) != 0]
        self.LOGGER.debug(f"[AUDIT] Open positions count: {len(open_positions)}; total market value: {total_position_value}")
        # self.LOGGER.debug(f"[AUDIT] Open positions: {open_positions}")

        # Update equity: cash + unrealized P&L
        self.ACCOUNT.equity = max(np.round(
            self.ACCOUNT.cash + total_unrealized_pl, 2), 0)
        
        # Buying power = (cash * leverage) - total position value
        total_account_value_with_leverage = self.ACCOUNT.cash * self.ACCOUNT.leverage
        self.ACCOUNT.buying_power = max((
            np.round(total_account_value_with_leverage - total_position_value, 2)), 0)
        self.LOGGER.debug(f"[AUDIT] Buying Power after calc: {self.ACCOUNT.buying_power}")

    @property
    def Account(self) -> IAccount:
        """ Returns the state of the strategy."""
        self.update_account_balance()
        return self.ACCOUNT

    @Account.setter
    def Account(self, account: IAccount):
        """ Sets the state of the strategy."""
        cash = account.cash
        self.LOGGER.debug("updated account cash from:",
              self.Account.cash, "->", account.cash)
        if cash and cash != self.ACCOUNT.cash:
            self.ACCOUNT.cash = max(np.round(cash, 2), 0)
        equity = account.equity
        if equity and equity != self.ACCOUNT.equity:
            self.ACCOUNT.equity = max(np.round(equity, 2), 0)

        if account.get('leverage') and account.leverage != self.ACCOUNT.leverage:
            self.ACCOUNT.leverage = account.leverage

        self.update_account_balance()


if __name__ == '__main__':
    # os.path.join(os.path.dirname(__file__), 'data')
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 5, 27), end_date=datetime(2024, 5, 31))
