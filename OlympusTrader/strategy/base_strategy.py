import abc
import asyncio
import os
from threading import Thread
from typing import Any, List, override, Union, Literal
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time
import datetime
import nest_asyncio
import timeit
from collections import deque

from ..broker.base_broker import BaseBroker
from ..broker.interfaces import ISupportedBrokers, TradeUpdateEvent, Asset, IAccount, IPosition, IOrder

from .sharedmemory import SharedStrategyManager
from ..utils.interfaces import IMarketDataStream, IStrategyMode
from ..utils.insight import Insight, InsightState
from ..utils.timeframe import TimeFrame, TimeFrameUnit
from ..utils.types import AttributeDict
from ..utils.tools import TradingTools

# from ..ui.base_ui import Dashboard


class BaseStrategy(abc.ABC):
    NAME: str = "BaseStrategy"
    BROKER: BaseBroker
    ACCOUNT: IAccount = {}
    POSITIONS: dict[str, IPosition] = {}
    ORDERS: deque[IOrder] = deque([])
    HISTORY: pd.DataFrame = pd.DataFrame(
        columns=['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume'])
    INSIGHTS: dict[str, Insight] = {}
    UNIVERSE: dict[str, Asset] = {}
    RESOLUTION = TimeFrame(5, TimeFrameUnit.Minute)
    STREAMS: List[IMarketDataStream] = []
    VARIABLES: AttributeDict
    MODE: IStrategyMode
    WITHUI: bool = True
    SSM: SharedStrategyManager = None
    # DASHBOARD: Dashboard = None

    TOOLS: TradingTools = None
    VERBOSE: int = 0

    @abc.abstractmethod
    def __init__(self, broker: BaseBroker, variables: AttributeDict = AttributeDict({}), resolution: TimeFrame = TimeFrame(1, TimeFrameUnit.Minute), verbose: int = 0, ui: bool = True, mode:
                 IStrategyMode = IStrategyMode.LIVE ) -> None:
        """Abstract class for strategy implementations."""
        self.NAME = self.__class__.__name__
        self.MODE = mode
        self.WITHUI = ui
        self.VARIABLES = variables
        self.BROKER = broker
        self.TOOLS = TradingTools(self)
        self.VERBOSE = verbose
        assert TimeFrame.validate_timeframe(
            resolution.amount, resolution.unit), 'Resolution must be a valid timeframe'
        self.RESOLUTION = resolution
       
        
        # set the UI shared memory sever
        if self.WITHUI:
            self._startUISharedMemory()

        self._start()

        # Load the universe
        self._loadUniverse()
        for asset in self.UNIVERSE.values():
            self.init(asset)

        # Set backtesting configuration
        if self.MODE == IStrategyMode.BACKTEST:
            # check if the broker is paper
            assert self.BROKER.NAME == ISupportedBrokers.PAPER, 'Backtesting is only supported with the paper broker'
            # # change the broker to feed to backtest mode 
            # self.BROKER.feed = IStrategyMode.BACKTEST
            pass

        self.ACCOUNT = self.BROKER.get_account()
        self.POSITIONS = self.BROKER.get_positions()

    @override
    @abc.abstractmethod
    def start(self):
        """ Start the strategy. This method is called once at the start of the strategy."""
        pass
        
    @override
    @abc.abstractmethod
    def init(self, asset: Asset):
        """ Initialize the strategy. This method is called once before the start of the strategy on every asset in the universe."""
        pass

    @override
    @abc.abstractmethod
    def universe(self) -> set[str]:
        """ Used to generate the stock in play. """
        pass

    @override
    @abc.abstractmethod
    def on_bar(self, symbol: str, bar: dict):
        """ Called once per bar. open, high, low, close, volume """
        print('IS THIS WORKING, Add on_bar Function? ->  async def on_bar(self, bar):')
        pass

    @override
    @abc.abstractmethod
    def executeInsight(self, symbol: str):
        """ Called for each active insight in the strategy. 
        it allows you to conrol the execution of the insight and manage the order.
        """
        print('IS THIS WORKING, Add executeInsight Function? ->  async def executeInsight(self, symbol: str):')
        for i, insight in enumerate(self.insights[symbol]):
            match insight.state:
                # case InsightState.NEW:
                #     pass
                # case InsightState.EXECUTED:
                #     pass
                # case InsightState.FILLED:
                #     pass
                # case InsightState.EXPIRED:
                #     pass
                # case InsightState.CANCELED:
                #     pass
                # case InsightState.REJECTED:
                #     pass
                # case InsightState.CLOSED:
                #     pass
                case _:
                    print(
                        'Implement the insight state in the executeInsight function:', insight.state)
                    pass

    @override
    @abc.abstractmethod
    def teardown(self):
        """ Called once at the end of the strategy. """
        print('Teardown Function? -> def teardown(self):')
        self.BROKER.close_all_positions()

    def run(self):
        """ starts the strategy. """
        nest_asyncio.apply()

        # check if universe is empty
        assert len(self.UNIVERSE) > 0, 'Universe is empty'

        if self.MODE == IStrategyMode.LIVE:
            if self.BROKER.NAME == ISupportedBrokers.ALPACA:
                # Exchange specific setup
                pass

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                with ThreadPoolExecutor(max_workers=3, thread_name_prefix="OlympusTraderStreams") as pool:
                    try:
                        #  Trading data streams
                        tradeStream = loop.run_in_executor(
                            pool, self.BROKER.startTradeStream, self._on_trade_update)
                        marketDataStream = loop.run_in_executor(
                            pool, self.BROKER.streamMarketData, self._on_bar, self.STREAMS)

                        # UI Shared Memory Server
                        if self.WITHUI:
                            server = self.SSM.get_server()
                            loop.run_in_executor(
                                pool, server.serve_forever)
                            print('UI Shared Memory Server started')

                        #  Insight executor and listener
                        insighStream = asyncio.run(self._insightListener())

                    except Exception as e:
                        self.BROKER.closeTradeStream()
                        print(f'Exception from Threads: {e}')
                loop.run_forever()

            except KeyboardInterrupt:
                print("Interrupted execution by user")
            finally:
                self.teardown()
                # pool.shutdown(wait=False)
                # loop.close()
                exit(0)

        
        elif self.MODE == IStrategyMode.BACKTEST:
            # Backtest
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                print('Running Backtest')
                with ThreadPoolExecutor(max_workers=3, thread_name_prefix="OlympusTraderStreams") as pool:
                    try:
                        #  Trading data streams
                        tradeStream = loop.run_in_executor(
                            pool, self.BROKER.startTradeStream, self._on_trade_update)
                        marketDataStream = loop.run_in_executor(
                            pool, self.BROKER.streamMarketData, self._on_bar, self.STREAMS)
                        # marketDataStream = asyncio.run( self.BROKER.streamMarketData(self._on_bar, self.STREAMS))

                        # UI Shared Memory Server
                        if self.WITHUI:
                            server = self.SSM.get_server()
                            loop.run_in_executor(
                                pool, server.serve_forever)
                            print('UI Shared Memory Server started')

                        #  Insight executor and listener
                        insighStream = asyncio.run(self._insightListener())

                    except Exception as e:
                        self.BROKER.closeTradeStream()
                        print(f'Exception from Threads: {e}')

                # loop.run_forever()

            except KeyboardInterrupt:
                print("Interrupted execution by user")
            finally:
                self.teardown()
                # pool.shutdown(wait=False)
                # loop.close()
            print('Backtest Completed')
            # TODO: Add backtest results
            exit(0)
            

    def _startUISharedMemory(self):
        """ Starts the UI shared memory."""
        if not self.WITHUI:
            print('UI is not enabled')
            return
        try:
            assert os.getenv(
                'SSM_PASSWORD'), 'SSM_PASSWORD not found in environment variables'
            SharedStrategyManager.register(
                'get_strategy', callable=lambda: self)
            SharedStrategyManager.register(
                'get_account', callable=lambda: self.ACCOUNT)
            self.SSM = SharedStrategyManager(
                address=('', 50000), authkey=os.getenv('SSM_PASSWORD').encode())

        except Exception as e:
            print(f'Error in _startUISharedMemory: {e}')
            pass

    async def _insightListener(self):
        """ Listen to the insights and manage the orders. """
        print('Running Insight Listener')
        loop = asyncio.get_running_loop()
        while True:
            for symbol in self.INSIGHTS.keys():

                if (len(self.INSIGHTS[symbol]) > 0):
                    try:
                        if self.VERBOSE > 0:
                            print(f'Execute Insight: {
                                symbol}- {datetime.datetime.now()}')
                            start_time = timeit.default_timer()
                        self.executeInsight(symbol)
                        if self.VERBOSE > 0:
                            print('Time taken executeInsight:', symbol,
                                  timeit.default_timer() - start_time)
                    except Exception as e:
                        print('Error in _insightListener:', e)
                        continue
            await asyncio.sleep(10)
            # Update the account and positions
            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()

    async def _on_trade_update(self, trade):
        """ format the trade stream to the strategy. """
        orderdata, event = self.BROKER.format_on_trade_update(trade)
        # check if there is data and that the order symbol is in the universe
        if orderdata and orderdata['asset']['symbol'] in self.UNIVERSE:
            print(
                f"Order: {event:<16} {orderdata['created_at']}: {orderdata['asset']['symbol']:^6}:{orderdata['qty']:^8}: {orderdata['type']} / {orderdata['order_class']} : {orderdata['side']} @ {orderdata['limit_price'] if orderdata['limit_price'] != None else orderdata['filled_price']}, {orderdata['order_id']}")
            self.ORDERS.append(orderdata)
            for i, insight in enumerate(self.INSIGHTS[orderdata['asset']['symbol']]):
                match insight.state:
                    case InsightState.EXECUTED:
                        # We aleady know that the order has been executed becsue it will never be in the insights list as executed if it was not accepted by the broker
                        if insight.order_id == orderdata['order_id']:
                            if event == TradeUpdateEvent.FILL:
                                # Update the insight with the filled price
                                self.INSIGHTS[orderdata['asset']['symbol']][i].positionFilled(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['qty'])
                                break  # No need to continue
                            
                            if event == TradeUpdateEvent.CLOSED:
                                self.INSIGHTS[orderdata['asset']['symbol']][i].positionFilled(
                                    orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['limit_price'], orderdata['qty'])
                            # TODO: also keep track of partial fills as some positions may be partially filled and not fully filled. in these cases we need to update the insight with the filled quantity and price,
                            if event == 'canceled':
                                # TODO: Also check if we have been partially filled and remove the filled quantity from the insight
                                self.INSIGHTS[orderdata['asset']['symbol']][i].updateState(
                                    InsightState.CANCELED, 'Order Canceled')
                            if event == 'rejected':
                                self.INSIGHTS[orderdata['asset']['symbol']][i].updateState(
                                    InsightState.REJECTED, 'Order Rejected')
                                break
                    case InsightState.FILLED | InsightState.CLOSED:
                        # Check if the position has been closed via SL or TP
                        if insight.symbol == orderdata['asset']['symbol']:
                            # Make sure the order is part of the insight as we dont have a clear way to tell if the closed fill is part of the strategy- to ensure that the the strategy is managed
                            if (event == TradeUpdateEvent.FILL) and ((orderdata['qty'] == insight.quantity and orderdata['side'] != insight.side) or \
                                                                    (insight.close_order_id != None and insight.close_order_id == orderdata['order_id']) or \
                                                                    (insight.order_id == orderdata['order_id'])):
                                # Update the insight closed price
                                self.INSIGHTS[orderdata['asset']['symbol']][i].positionClosed(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['order_id'])
                                break  # No need to continue
        else:
            # 'Order not in universe'
            pass
        # TODOL Check if the order is part of the resolution of the strategy and has a insight that is managing it.

    def _start(self):
        """ Start the strategy. """
        assert callable(self.start), 'start must be a callable function'
         # 1% of account per trade
        print("Running start function")
        self.state['execution_risk'] = 0.01
        # 2:1 Reward to Risk Ratio minimum
        self.state['RewardRiskRatio'] = 2.0

        self.start()

    def _loadUniverse(self):
        """ Loads the universe of the strategy."""
        assert callable(self.universe), 'Universe must be a callable function'
        universeSet = set(self.universe())
        for symbol in universeSet:
            self._loadAsset(symbol)
        if len(self.UNIVERSE) == 0:
            print('No assets loaded into the universe')

    def _loadAsset(self, s: str):
        """ Loads the asset into the universe of the strategy."""
        symbol = s.upper()
        assetInfo = self.BROKER.get_ticker_info(symbol)
        if assetInfo and assetInfo['status'] == 'active' and assetInfo['tradable']:
            self.UNIVERSE[symbol] = assetInfo
            self.INSIGHTS[symbol] = []

            print(
                f'Loaded {symbol}:{assetInfo["exchange"], }  into universe')
        else:
            print(f'Failed to load {symbol} into universe')

    def add_events(self, eventType: Literal['trade', 'quote', 'bar', 'news'] = 'bar'):
        """ Adds bar streams to the strategy."""
        match eventType:
            case 'bar' | 'trade' | 'quote' | 'news':
                for assetInfo in self.UNIVERSE.values():
                    self.STREAMS.append(IMarketDataStream(symbol=assetInfo.get('symbol'), exchange=assetInfo.get(
                        'exchange'), time_frame=self.RESOLUTION, asset_type=assetInfo.get('asset_type'), type=eventType))
            case _:
                print(f"{eventType} Event not supported")

    def add_insight(self, insight: Insight):
        """ Adds an insight to the strategy."""
        assert isinstance(
            insight, Insight), 'insight must be of type Insight object'
        
        insight.set_mode(self.BROKER, self.MODE )


        self.INSIGHTS[insight.symbol].append(insight)

    async def _on_bar(self, bar: Any):
        """ format the bar stream to the strategy. """
        try:
            # set_index(['symbol', 'timestamp']
            if bar.empty:
                print('Bar is None')
                return
            
            if self.MODE != IStrategyMode.BACKTEST:
                data = self.BROKER.format_on_bar(bar)
            else:
                data = bar

            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            orders = self.BROKER.get_orders()
            if orders:
                self.ORDERS = deque(orders)
            else:
                self.ORDERS = deque([])

            if self.POSITIONS == None:
                self.POSITIONS = {}

            if not data.empty:
                symbol = data.index[0][0]
                timestamp = data.index[0][1]
                # Check if the bar is part of the resolution of the strategy
                if self.resolution.is_time_increment(timestamp):
                    self.HISTORY = pd.concat([self.HISTORY, data])
                    # print('New Bar is part of the resolution of the strategy', data)
                    if self.VERBOSE > 0:
                        print(f'New Bar is part of the resolution of the strategy: {
                              symbol} - {timestamp} - {datetime.datetime.now()}')
                        start_time = timeit.default_timer()

                    # Call the on_bar function and process the bar
                    self.on_bar(symbol, data)
                    if self.VERBOSE > 0:
                        print('Time taken on_bar:', symbol,
                              timeit.default_timer() - start_time)
                else:
                    # print('Bar is not part of the resolution of the strategy', data)
                    pass
                    # Will need to take the the 1 min bar and convert it to the resolution of the strategy
            else:
                print('Data is empty - BROKER.format_on_bar(bar) not working')
        except Exception as e:
            print('Error in _on_bar_format in base Strategy:', e)

    def submit_order(self, insight: Insight):
        """ Submits an order to the broker."""
        assert isinstance(
            insight, Insight), 'insight must be of type Insight object'
        try:
            order = self.BROKER.execute_insight_order(
                insight, self.assets[insight.symbol])
            return order
        except BaseException as e:
            # print('Error in submit_order:', e)
            raise e

    def close_position(self, symbol, qty=None, percent=None):
        """ Cancels an order to the broker."""
        return self.BROKER.close_position(symbol, qty, percent)

    # dynamic function to get variables from the strategy class - used in the UI shared server.
    def get_variable(self, var='account'):
        """ Get a variable from the strategy class."""
        if not self.WITHUI:
            print('UI is not enabled')
            return None
        try:
            if getattr(self, var):
                return getattr(self, var)
        except AttributeError as e:
            return None

    @property
    def account(self) -> IAccount:
        """ Returns the account of the strategy."""
        return self.ACCOUNT

    @property
    def positions(self) -> dict[str, IPosition]:
        """ Returns the positions of the strategy."""
        return self.POSITIONS

    @property
    def orders(self) -> deque[IOrder]:
        """ Returns the orders of the strategy."""
        return self.ORDERS

    @property
    def history(self) -> pd.DataFrame:
        """ Returns the orders of the strategy."""
        return self.HISTORY

    @property
    def insights(self) -> dict[str, Insight]:
        """ Returns the insights of the strategy."""
        return self.INSIGHTS

    @property
    def state(self) -> dict:
        """ Returns the state of the strategy."""
        return self.VARIABLES

    @state.setter
    def state(self, state: dict):
        """ Sets the state of the strategy."""
        self.VARIABLES = state

    @property
    def broker(self) -> BaseBroker:
        """ Returns the broker used by the strategy."""
        return self.BROKER

    @property
    def assets(self) -> dict[str, Asset]:
        """ Returns the universe of the strategy."""
        return self.UNIVERSE

    @property
    def resolution(self) -> TimeFrame:
        """ Returns the resolution of the strategy."""
        return self.RESOLUTION

    @property
    def tools(self) -> TradingTools:
        """ Returns the tools of the strategy."""
        return self.TOOLS

    @property
    def streams(self) -> dict:
        """ Returns the streams of the strategy."""
        return self.STREAMS
