import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import datetime
from types import NoneType
import uuid
import numpy as np
from typing import List, Literal
from collections import deque
from threading import Barrier, BrokenBarrierError
from concurrent.futures import as_completed
from pathlib import Path


import pandas as pd

from .base_broker import BaseBroker
from .interfaces import ITimeInForce, ISupportedBrokers, IOrderClass, IOrderRequest, IOrderSide, IOrderType, ITimeInForce, ITradeUpdate, ITradeUpdateEvent
from ..utils.insight import Insight
from .interfaces import IAccount, IOrder, IPosition, IAsset, IOrderLegs
from ..utils.interfaces import IMarketDataStream, IStrategyMode
from ..utils.timeframe import ITimeFrame


import yfinance as yf


class PaperBroker(BaseBroker):
    MODE: IStrategyMode = IStrategyMode.BACKTEST

    Account: IAccount = None
    Possitions: dict[str, IPosition] = {}
    Orders: dict[str, IOrder] = {}
    LEVERAGE: int = 4

    # Backtest mode
    STARTING_CASH: float = 100_000.00
    START_DATE: datetime.date = None
    END_DATE: datetime.date = None
    CURRENT: datetime.date = None
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

    TICKER_INFO: dict[str, IAsset] = {}

    def __init__(self, cash: float = 100_000.00, start_date: datetime.date = None, end_date: datetime.date = None, leverage: int = 4, currency: str = "USD", allow_short: bool = True, mode: IStrategyMode = IStrategyMode.BACKTEST, feed: Literal['yf', 'eod'] = 'yf'):

        super().__init__(ISupportedBrokers.PAPER, True, feed)
        self.MODE = mode
        self.LEVERAGE = leverage
        self.STARTING_CASH = cash
        self.Account = IAccount(account_id='PAPER_ACCOUNT', cash=self.STARTING_CASH, currency=currency,
                                buying_power=cash*self.LEVERAGE, shorting_enabled=allow_short)

        # Set the backtest configuration
        if self.MODE == IStrategyMode.BACKTEST:
            assert start_date and end_date, 'Start and End date must be provided for backtesting'
            assert start_date < end_date, 'Start date must be before end date'
            # self.START_DATE = start_date.replace(tzinfo=datetime.timezone.utc)
            self.START_DATE = start_date
            self.END_DATE = end_date
            self.CURRENT = self.START_DATE
            self.ACCOUNT_HISTORY = {self.CURRENT: self.Account}
            self.BACKTEST_FlOW_CONTROL_BARRIER = Barrier(3)
            # self.BACKTEST_FlOW_CONTROL_BARRIER.reset()
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    def get_ticker_info(self, symbol: str):
        if symbol in self.TICKER_INFO:
            return self.TICKER_INFO[symbol]

        if self.DataFeed == 'yf':
            symbol = symbol.replace('/', '-')
            tickerInfo = yf.Ticker(symbol).info

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
            return tickerAsset
        else:
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def get_history(self, asset: IAsset, start: datetime.datetime, end: datetime.datetime, resolution: ITimeFrame, shouldDelta: bool = True) -> pd.DataFrame:
        super().get_history(asset, start, end, resolution)

        if self.DataFeed == 'yf':
            symbol = asset['symbol'].replace('/', '-')
            formatTF = f'{resolution.amount}{resolution.unit.value[0].lower()}'
            if self.MODE == IStrategyMode.BACKTEST:
                delta: datetime.timedelta = start - \
                    self.CURRENT if shouldDelta else datetime.timedelta()
                # print("start: ", self.CURRENT-start, "end: ", self.CURRENT-end)
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
        return self.Possitions.get(symbol)

    def get_positions(self):
        return self.Possitions

    def get_orders(self):
        return [order for order in self.Orders.values()]

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
                order['updated_at'] = self.CURRENT
                self.CANCELED_ORDERS.append(order)
                return order
        else:
            raise BaseException({
                "code": "order_not_found",
                "data": {"order_id": order_id}
            })

    def startTradeStream(self, callback):
        super().startTradeStream(callback)
        self.RUNNING_TRADE_STREAM = True
        if self.MODE == IStrategyMode.BACKTEST:
            loop = asyncio.new_event_loop()
            # TODO: trade stream for all of the pending, filled, canceled oerders.
            while self.CURRENT <= self.END_DATE and self.RUNNING_TRADE_STREAM:
                try:
                    self.BACKTEST_FlOW_CONTROL_BARRIER.wait()
                    print("pending: ", len(self.PENDING_ORDERS),
                          "active: ", len(self.ACTIVE_ORDERS),
                          "closed: ", len(self.CLOSE_ORDERS),
                          "canceled: ", len(self.CANCELED_ORDERS))

                    for i, order in enumerate(list(self.PENDING_ORDERS)):
                        currentBar = self._get_current_bar(
                            order['asset']['symbol'])
                        if currentBar is None:
                            continue

                        if order['created_at'] == self.CURRENT:
                            order['status'] = ITradeUpdateEvent.NEW
                            self._update_order(order)
                            loop.run_until_complete(
                                callback(ITradeUpdate(order, ITradeUpdateEvent.NEW)))
                        if order['type'] == IOrderType.MARKET:
                            # Market order - fill at the current close price
                            order['filled_price'] = currentBar['close']
                            order['status'] = ITradeUpdateEvent.FILLED
                            order['filled_at'] = self.CURRENT
                            order['updated_at'] = self.CURRENT
                            self._update_order(order)
                            loop.run_until_complete(callback(ITradeUpdate(
                                order, ITradeUpdateEvent.FILLED)))

                        elif order['type'] == IOrderType.LIMIT:
                            if order['limit_price'] >= currentBar['low'].values[0] and order['limit_price'] <= currentBar['high'].values[0]:
                                order['filled_price'] = order['limit_price']
                                order['status'] = ITradeUpdateEvent.FILLED
                                order['filled_at'] = self.CURRENT
                                order['updated_at'] = self.CURRENT
                                self._update_order(order)
                                loop.run_until_complete(callback(ITradeUpdate(
                                    order, ITradeUpdateEvent.FILLED)))

                    for i, order in enumerate(list(self.ACTIVE_ORDERS)):
                        # update the position information as the position is filled and keep track of all  positions PNL
                        self._update_position(order['asset']['symbol'])

                        currentBar = self._get_current_bar(
                            order['asset']['symbol'])
                        if currentBar is None:
                            continue

                        # check if the order has take profit or stop loss
                        if order['legs']:
                            # FIXME: Figure out if the take profit or stop loss is hit first

                            if order['legs']['take_profit']:
                                take_profit = order['legs']['take_profit']
                                if take_profit['limit_price'] >= currentBar['low'].values[0] and take_profit['limit_price'] <= currentBar['high'].values[0]:
                                    take_profit['filled_price'] = take_profit['limit_price']
                                    take_profit['status'] = ITradeUpdateEvent.CLOSED
                                    take_profit['filled_at'] = self.CURRENT
                                    take_profit['updated_at'] = self.CURRENT

                                    order['stop_price'] = take_profit['limit_price']
                                    order['updated_at'] = self.CURRENT
                                    order['status'] = ITradeUpdateEvent.CLOSED
                                    order['legs']['take_profit'] = take_profit

                                    self._update_order(order)
                                    self._update_position(
                                        order['asset']['symbol'], take_profit['filled_price'])

                                    loop.run_until_complete(callback(ITradeUpdate(
                                        order, ITradeUpdateEvent.CLOSED)))
                            elif order['legs']['stop_loss']:
                                stop_loss = order['legs']['stop_loss']
                                if stop_loss['limit_price'] >= currentBar['low'].values[0] and stop_loss['limit_price'] <= currentBar['high'].values[0]:
                                    stop_loss['filled_price'] = stop_loss['limit_price']
                                    stop_loss['status'] = ITradeUpdateEvent.CLOSED
                                    stop_loss['filled_at'] = self.CURRENT
                                    stop_loss['updated_at'] = self.CURRENT

                                    order['stop_price'] = stop_loss['limit_price']
                                    order['updated_at'] = self.CURRENT
                                    order['status'] = ITradeUpdateEvent.CLOSED
                                    order['legs']['stop_loss'] = stop_loss

                                    self._update_order(order)
                                    self._update_position(
                                        order['asset']['symbol'], stop_loss['filled_price'])

                                    loop.run_until_complete(callback(ITradeUpdate(
                                        order, ITradeUpdateEvent.CLOSED)))
                        else:
                            # USually a market order or limit order without take profit or stop loss
                            pass
                    for i, order in enumerate(list(self.CLOSE_ORDERS)):
                        # update the position information as the position is filled and keep track of all  positions PNL
                        self._update_position(order['asset']['symbol'])

                        currentBar = self._get_current_bar(
                            order['asset']['symbol'])
                        if currentBar is None:
                            continue

                        order['stop_price'] = currentBar.at[0, 'open']
                        order['status'] = ITradeUpdateEvent.CLOSED
                        order['filled_at'] = self.CURRENT
                        order['updated_at'] = self.CURRENT
                        self._update_order(order)
                        self._update_position(
                            order['asset']['symbol'], order['stop_price'])
                        loop.run_until_complete(callback(ITradeUpdate(
                            order, ITradeUpdateEvent.CLOSED)))

                    for i, order in enumerate(list(self.CANCELED_ORDERS)):
                        order['status'] = ITradeUpdateEvent.CANCELED
                        order['updated_at'] = self.CURRENT
                        self._update_order(order)
                        loop.run_until_complete(callback(ITradeUpdate(
                            order, ITradeUpdateEvent.CANCELED)))

                except BrokenBarrierError:
                    continue
                except Exception as e:
                    print("Error: ", e)
                    continue
            print("End of Trade Stream")

        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    async def closeTradeStream(self):
        if self.MODE == IStrategyMode.BACKTEST:
            self.RUNNING_TRADE_STREAM = False
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    def _update_position(self, symbol: str, close_price: float = None):
        currentBar = self._get_current_bar(symbol)
        oldPosition = self.Possitions[symbol]
        self.Possitions[symbol]['current_price'] = currentBar['close'] if not close_price else close_price

        if self.Possitions[symbol]['qty'] != 0:
            self.Possitions[symbol]['market_value'] = self.Possitions[symbol]['current_price'] * \
                np.abs(self.Possitions[symbol]['qty']
                       )  # qunaity can be negative for short positions
            self.Possitions[symbol]['unrealized_pl'] = self.Possitions[symbol]['market_value'] - \
                self.Possitions[symbol]['cost_basis']
            changeInPL = self.Possitions[symbol]['unrealized_pl'] - \
                oldPosition['unrealized_pl']
            self.Account['buying_power'] += changeInPL
            self.Account['cash'] += changeInPL
        else:
            # self.Possitions[symbol]['market_value']
            self.Account['buying_power'] += self.Possitions[symbol]['cost_basis']
            # TODO: Later we can remove the position from the possitions dictionary
            # del self.Possitions[symbol]
        print("Updated Position: ", self.Possitions[symbol], self.Account['cash'], self.Account['buying_power'])

    def _update_order(self, order: IOrder):
        oldOrder = self.Orders.get(order['order_id'])
        
        match order['status']:
            case ITradeUpdateEvent.NEW: 
                if not oldOrder:
                    self.PENDING_ORDERS.append(order)

            case ITradeUpdateEvent.FILLED:
                if oldOrder['status'] == ITradeUpdateEvent.NEW:
                    if oldOrder in self.PENDING_ORDERS:
                        self.PENDING_ORDERS.remove(oldOrder)
                        if self.Possitions[order['asset']['symbol']]:
                            # position already exists
                            if order['side'] == IOrderSide.BUY:
                                self.Possitions[order['asset']
                                                ['symbol']]['qty'] += order['qty']
                            else:
                                self.Possitions[order['asset']
                                                ['symbol']]['qty'] -= order['qty']

                            self._update_position(order['asset']['symbol'])
                        else:
                            # add positions dictionary
                            self.Possitions[order['asset']['symbol']] = IPosition(
                                asset=order['asset'],
                                avg_entry_price=order['filled_price'],
                                qty=order['qty'],
                                side=order['side'],
                                market_value=order['filled_price'] * order['qty'],
                                cost_basis=order['filled_price'] * order['qty'],
                                current_price=order['filled_price'],
                                unrealized_pl=0
                            )
                    # Add the order to the active orders
                    self.ACTIVE_ORDERS.append(order)

            case ITradeUpdateEvent.CANCELED:
                if (oldOrder['status'] == ITradeUpdateEvent.NEW) or (oldOrder in self.PENDING_ORDERS):
                    self.PENDING_ORDERS.remove(oldOrder)
                elif oldOrder['status'] == ITradeUpdateEvent.FILL:
                    raise BaseException({
                        "code": "already_filled",
                        "data": {"symbol": order['asset']['symbol']}
                    })
                # if oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                if oldOrder in self.CANCELED_ORDERS:
                    self.CANCELED_ORDERS.remove(oldOrder)
                # else:
                #     raise BaseException({
                #         "code": "order_not_found",
                #         "data": {"order_id": order['order_id']}
                #     })
            case ITradeUpdateEvent.CLOSED:
                if oldOrder:
                    if oldOrder['status'] == ITradeUpdateEvent.FILL and oldOrder in self.ACTIVE_ORDERS:
                        self.ACTIVE_ORDERS.remove(oldOrder)
                    elif oldOrder['status'] == ITradeUpdateEvent.CANCELED and oldOrder in self.CANCELED_ORDERS:
                        self.CANCELED_ORDERS.remove(oldOrder)
                    if order['side'] == IOrderSide.BUY:
                        self.Possitions[order['asset']
                                        ['symbol']]['qty'] -= order['qty']
                    else:
                        self.Possitions[order['asset']
                                        ['symbol']]['qty'] += order['qty']

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

                if self.MODE == IStrategyMode.BACKTEST:
                    order = self._submit_order(orderRequest)
                    return order
                else:
                    raise NotImplementedError(
                        f'Mode {self.MODE} not supported')

        except BaseException as e:
            raise e

    def _submit_order(self, orderRequest: IOrderRequest) -> IOrder:
        # check if the buying power is enough to place the order
        error = None
        marginRequired = orderRequest['qty'] * orderRequest['limit_price']
        buying_power = self.Account["buying_power"]

        # Account for the market value of the position if the order is in the opposite direction
        if self.Possitions.get(orderRequest['symbol']):
            if (orderRequest['side'] == IOrderSide.SELL and self.Possitions.get(orderRequest['symbol'])['qty'] < 0) or \
                    (orderRequest['side'] == IOrderSide.BUY and self.Possitions.get(orderRequest['symbol'])['qty'] > 0):
                buying_power += self.Possitions[orderRequest['symbol']
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
        legs = {}
        if orderRequest.get('take_profit'):
            legs["take_profit"] = {
                "order_id": uuid.uuid4(), "limit_price": orderRequest['take_profit'], "filled_price": None}
        if orderRequest.get('stop_loss'):
            legs["stop_loss"] = {
                "order_id": uuid.uuid4(), "limit_price": orderRequest['stop_loss'], "filled_price": None}
        if orderRequest.get('trail_price'):
            legs["trailing_stop"] = {
                "order_id": uuid.uuid4(), "limit_price": orderRequest['trail_price'], "filled_price": None}

        if self.MODE == IStrategyMode.BACKTEST:
            order = IOrder(
                order_id=uuid.uuid4(),
                asset=self.get_ticker_info(orderRequest['symbol']),
                limit_price=orderRequest['limit_price'] if orderRequest['limit_price'] else None,
                filled_price=None,
                stop_price=None,
                qty=orderRequest['qty'],
                side=orderRequest['side'],
                type=orderRequest['type'],
                time_in_force=orderRequest['time_in_force'],
                status=ITradeUpdateEvent.NEW,
                order_class=orderRequest['order_class'],
                created_at=self.CURRENT,
                updated_at=self.CURRENT,
                submitted_at=self.CURRENT,
                filled_at=None,
                legs=IOrderLegs(take_profit=legs.get("take_profit"), stop_loss=legs.get(
                    "stop_loss"), trailing_stop=legs.get("trailing_stop"))

            )
            self.Account['buying_power'] -= marginRequired
            self._update_order(order)
            return order

        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

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

    def format_on_trade_update(self, trade: ITradeUpdate):
        if isinstance(trade, ITradeUpdate):
            # self.add_order(trade.order)
            return trade.order, trade.event
        else:
            # format trade update from data feed
            raise NotImplementedError(
                f'DataFeed {self.DataFeed} not supported')

    def _load_historical_bar_data(self, asset: IMarketDataStream):
        try:
            bar_data_path = None
            if asset.get('stored'):
                if asset['stored_path']:
                    bar_data_path = asset['stored_path'] + \
                        f'/bar/{asset["symbol"]}.h5'
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
                print("Saving data to ",
                      asset['stored_path']+f'/bar/{asset["symbol"]}.h5')
                self.HISTORICAL_DATA[asset['symbol']]['bar'].to_hdf(
                    asset['stored_path']+f'/bar/{asset["symbol"]}.h5', mode='a', key=asset["exchange"], index=True, format='table')

                return True

        else:
            print('DataFeed not supported')

    def streamMarketData(self, callback, assetStreams):
        """Listen to market data and call the callback function with the data"""
        super().streamMarketData(callback, assetStreams)
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
            self.RUNNING_MARKET_STREAM = True
            loop = asyncio.new_event_loop()
            while self.CURRENT <= self.END_DATE and self.RUNNING_MARKET_STREAM and len(assetStreams) > 0:
                try:
                    print("streaming data for ", self.CURRENT)
                    # self.BACKTEST_FlOW_CONTROL_BARRIER.reset()
                    # futures = set()
                    # with ThreadPoolExecutor(max_workers=len(assetStreams), thread_name_prefix="MarketDataStream") as pool:
                    for asset in assetStreams:
                        if asset['type'] == 'bar':
                            try:
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
                    # Go to next time frame
                    # FIXME: Implement time frame increment
                    self.CURRENT += datetime.timedelta(minutes=1)
                    if self.CURRENT > self.END_DATE:
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
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    async def closeStream(self,  assetStreams: List[IMarketDataStream]):
        if self.MODE == IStrategyMode.BACKTEST:
            self.RUNNING_MARKET_STREAM = False
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    def close_position(self, symbol: str, qty=None, percent=None):
        position = self.Possitions.get(symbol)
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
                side=counterPosistionSide,
                type=IOrderType.MARKET,
                time_in_force=ITimeInForce.GTC,
                status=ITradeUpdateEvent.NEW,
                order_class=IOrderClass.SIMPLE,
                created_at=self.CURRENT,
                updated_at=self.CURRENT,
                submitted_at=self.CURRENT,
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
        for symbol in self.Possitions.keys():
            if self.Possitions[symbol]['qty'] != 0:
                self.close_position(symbol, qty=self.Possitions[symbol]['qty'])
        return True

    def get_current_time(self):
        if self.MODE == IStrategyMode.BACKTEST:
            return self.CURRENT
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

    def _get_current_bar(self, symbol: str):
        if self.MODE == IStrategyMode.BACKTEST:
            if symbol in self.HISTORICAL_DATA:
                # current_time = self.CURRENT.replace(
                #     tzinfo=None)
                current_time = self.CURRENT.replace(
                    tzinfo=datetime.timezone.utc)
                # current_time = self.CURRENT
                try:
                    idx = pd.IndexSlice
                    currentBar = self.HISTORICAL_DATA[symbol]['bar'].loc[idx[symbol,
                                                                             current_time:current_time], :]
                    if currentBar.empty:
                        return None
                    return currentBar
                except KeyError:
                    return None
            else:
                raise BaseException({
                    "code": "symbol_not_found",
                    "data": {"symbol": symbol}
                })
        else:
            raise NotImplementedError(f'Mode {self.MODE} not supported')

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

if __name__ == '__main__':
    # os.path.join(os.path.dirname(__file__), 'data')
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 5, 27), end_date=datetime(2024, 5, 31))
