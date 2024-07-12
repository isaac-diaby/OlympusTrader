import abc
import asyncio
import os
from threading import BrokenBarrierError, Thread
from typing import Any, List, override, Union, Literal
from uuid import uuid4
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import datetime
import nest_asyncio
import timeit
from collections import deque

import pandas_ta as ta

from ..broker.base_broker import BaseBroker
from ..broker.interfaces import ISupportedBrokers, ITradeUpdateEvent, IAsset, IAccount, IPosition, IOrder

from .sharedmemory import SharedStrategyManager
from .interfaces import IMarketDataStream, IStrategyMode
from ..insight.insight import Insight, InsightState
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit
from ..utils.types import AttributeDict
from ..utils.tools import ITradingTools

from ..alpha.base_alpha import BaseAlpha
from ..insight.executors.base_executor import BaseExecutor
# from ..ui.base_ui import Dashboard
import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class BaseStrategy(abc.ABC):
    NAME: str = "BaseStrategy"
    BROKER: BaseBroker
    ACCOUNT: IAccount = {}
    POSITIONS: dict[str, IPosition] = {}
    ORDERS: deque[IOrder] = deque([])
    HISTORY: dict[str, pd.DataFrame] = {}
    INSIGHTS: dict[str, Insight] = {}
    UNIVERSE: dict[str, IAsset] = {}
    RESOLUTION = ITimeFrame(5, ITimeFrameUnit.Minute)
    STREAMS: List[IMarketDataStream] = []
    VARIABLES: AttributeDict
    MODE: IStrategyMode
    WITHUI: bool = True
    SSM: SharedStrategyManager = None
    # DASHBOARD: Dashboard = None

    TOOLS: ITradingTools = None

    # DEBUG
    VERBOSE: int = 0

    _Running = False
    STARTING_CASH: float = None

    # ALPHA MODELS
    ALPHA_MODELS: List[BaseAlpha] = []

    # Insight Executors Models
    INSIGHT_EXECUTORS: dict[InsightState, deque[BaseExecutor]] = {
        InsightState.NEW: deque([]),
        InsightState.EXECUTED: deque([]),
        InsightState.FILLED: deque([]),
        InsightState.CLOSED: deque([]),
        InsightState.REJECTED: deque([]),
        InsightState.CANCELED: deque([])
    }
    """Insight Executors Models"""

    # Strategy Execution Parameters
    TaStrategy: ta.Strategy = None
    WARM_UP: int = 0
    execution_risk: float = 0.01  # 1% of account per trade
    minRewardRiskRatio: float = 2.0  # 2:1 Reward to Risk Ratio minimum
    baseConfidence: float = 0.1  # Base Confidence level for the strategy

    @abc.abstractmethod
    def __init__(self, broker: BaseBroker, variables: AttributeDict = AttributeDict({}), resolution: ITimeFrame = ITimeFrame(1, ITimeFrameUnit.Minute), verbose: int = 0, ui: bool = True, mode:
                 IStrategyMode = IStrategyMode.LIVE) -> None:
        """Abstract class for strategy implementations."""
        self.NAME = self.__class__.__name__
        self.MODE = mode
        self.WITHUI = ui
        self.VARIABLES = variables
        self.BROKER = broker
        self.TOOLS = ITradingTools(self)
        self.VERBOSE = verbose  # TODO: Log Levels should be an derived from env file
        assert ITimeFrame.validate_timeframe(
            resolution.amount, resolution.unit), 'Resolution must be a valid timeframe'
        self.RESOLUTION = resolution

        # set the UI shared memory sever
        if self.WITHUI:
            self._startUISharedMemory()

        # Set up TA Strategy
        self.TaStrategy = ta.Strategy(
            name=self.NAME, description="Olympus Trader Framework", ta=[])

        self.start()
        # Load the universe
        self._loadUniverse()

        # Set backtesting configuration
        if self.MODE == IStrategyMode.BACKTEST:
            # check if the broker is paper
            assert self.BROKER.NAME == ISupportedBrokers.PAPER, 'Backtesting is only supported with the paper broker'
            # # change the broker to feed to backtest mode
            # self.BROKER.feed = IStrategyMode.BACKTEST
            pass

        self.ACCOUNT = self.BROKER.get_account()
        self.POSITIONS = self.BROKER.get_positions()
        self.STARTING_CASH = self.ACCOUNT['equity']

    @override
    @abc.abstractmethod
    def start(self):
        """ Start the strategy. This method is called once at the start of the strategy."""
        pass

    @override
    @abc.abstractmethod
    def init(self, asset: IAsset):
        """ Initialize the strategy. This method is called once before the start of the strategy on every asset in the universe."""

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
    def generateInsights(self, symbol: str):
        """Called once per bar to generate insights. """
        print('IS THIS WORKING, Add generateInsights Function? -> def generateInsights(self, symbol: str):')
        pass

    @override
    @abc.abstractmethod
    def executeInsight(self, insight: Insight):
        """ Called for each active insight in the strategy. 
        it allows you to conrol the execution of the insight and manage the order.
        """
        print('IS THIS WORKING, Add executeInsight Function? ->  async def executeInsight(self, symbol: str):')
        match insight.state:
            # case InsightState.NEW:
            #     pass
            # case InsightState.EXECUTED:
            #     pass
            # case InsightState.FILLED:
            #     pass
            # case InsightState.CLOSED:
            #     pass
            # case InsightState.REJECTED:
            #     pass
            # case InsightState.CANCELED:
            #     pass
            case _:
                print(
                    'Implement the insight state in the executeInsight function:', insight.state)
                pass

    @override
    @abc.abstractmethod
    def teardown(self):
        """ Called once at the end of the strategy. """
        print("Tear Down: Closing all positions")
        self.BROKER.close_all_positions()

    def _start(self):
        """Start the alpha models."""
        # assert callable(self.start), 'start must be a callable function'
        # print("Running start function")

        for alpha in self.ALPHA_MODELS:
            alpha.start()
        # self.start()

    def _init(self, asset: IAsset):
        """ Initialize the strategy. """
        assert callable(self.init), 'init must be a callable function'
        for alpha in self.ALPHA_MODELS:
            alpha.init(asset)
        self.init(asset)

    def _generateInsights(self, symbol: str):
        """ Generate insights for the strategy. """
        assert callable(
            self.generateInsights), 'generateInsights must be a callable function'
        for alpha in self.ALPHA_MODELS:
            result = alpha.generateInsights(symbol)
            if result.success:
                if result.insight is not None:
                    self.add_insight(result.insight)
            else:
                print(f"Alpha {result.alpha} Failed: {result.message}")

        self.generateInsights(symbol)

    def run(self):
        """ starts the strategy. """
        nest_asyncio.apply()
        self._Running = True

        # set up the strategy
        self._start()

        # check if universe is empty
        assert len(self.UNIVERSE) > 0, 'Universe is empty'
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if self.MODE == IStrategyMode.LIVE:
            if self.BROKER.NAME == ISupportedBrokers.ALPACA:
                # Exchange specific setup
                pass

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
                        insighStream = loop.create_task(
                            self._insightListener(), name="OlympusTraderInsightListener")

                        insighStream = loop.run_in_executor(
                            pool, loop.run_forever)

                    except Exception as e:
                        print(f'Exception from Threads: {e}')

            except KeyboardInterrupt:
                print("Interrupted execution by user")
            finally:
                self.teardown()
                # asyncio.run(self.BROKER.closeTradeStream())
                pool.shutdown(wait=False)
                asyncio.run(self.BROKER.closeStream(self.STREAMS))
                self._Running = False
                exit(0)

        elif self.MODE == IStrategyMode.BACKTEST:
            # Backtest
            if self.VERBOSE > 0:
                print(f"Running Backtest - {datetime.datetime.now()}")
                start_time = timeit.default_timer()
            try:
                pool = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="OlympusTraderStreams")

                try:
                    #  Trading data streams
                    tradeStream = loop.run_in_executor(
                        pool, self.BROKER.startTradeStream, self._on_trade_update)
                    marketDataStream = loop.run_in_executor(
                        pool, self.BROKER.streamMarketData, self._on_bar, self.STREAMS)
                    # marketDataStream = asyncio.run( self.BROKER.streamMarketData(self._on_bar, self.STREAMS))

                    insighStream = loop.create_task(
                        self._insightListener(), name="OlympusTraderInsightListener")

                    insighStream = loop.run_in_executor(
                        pool, loop.run_forever)
                    # UI Shared Memory Server
                    if self.WITHUI:
                        server = self.SSM.get_server()
                        loop.run_in_executor(
                            pool, server.serve_forever)
                        print('UI Shared Memory Server started')

                    # TODO: Should probably use another barrier to check if the streams are running correctly after pulling the historical data
                    while not self.BROKER.RUNNING_MARKET_STREAM or not self.BROKER.RUNNING_TRADE_STREAM:
                        if self.BROKER.RUNNING_MARKET_STREAM and self.BROKER.RUNNING_TRADE_STREAM:
                            break

                    while self.BROKER.RUNNING_MARKET_STREAM and self.BROKER.RUNNING_TRADE_STREAM:
                        # print("***-- Running Backtest --***")
                        if not self.BROKER.RUNNING_MARKET_STREAM or not self.BROKER.RUNNING_TRADE_STREAM:
                            break
                        # TODO: Teardown on last candle
                        # self.teardown()

                    self.teardown()
                    pool.shutdown(wait=False)

                except Exception as e:
                    print(f'Exception from Threads: {e}')

                # loop.run_forever()

            except KeyboardInterrupt:
                print("Interrupted execution by user")
                # self.BROKER.closeTradeStream()
                # self.BROKER.closeStream(self.STREAMS)
                # insighStream.cancel()
            finally:
                self.teardown()
                asyncio.run(self.BROKER.closeTradeStream())
                asyncio.run(self.BROKER.closeStream(self.STREAMS))
                self._Running = False

            if self.VERBOSE > 0:
                print('Backtest Completed:',
                      timeit.default_timer() - start_time)

            print(self.BROKER.get_results())
            exit(0)

    def _startUISharedMemory(self):
        """ Starts the UI shared memory."""
        if not self.WITHUI:
            print('UI is not enabled')
            return
        try:
            assert os.getenv("SSM_PASSWORD"), 'SSM_PASSWORD not found in environment variables'
            SharedStrategyManager.register(
                'get_strategy', callable=lambda: self)
            SharedStrategyManager.register(
                'get_account', callable=lambda: self.account)
            SharedStrategyManager.register(
                'get_starting_cash', callable=lambda: self.STARTING_CASH)
            SharedStrategyManager.register(
                'get_mode', callable=lambda: self.MODE.value)
            SharedStrategyManager.register(
                'get_assets', callable=lambda: self.assets)
            SharedStrategyManager.register(
                'get_positions', callable=lambda: self.positions)
            SharedStrategyManager.register(
                'get_insights', callable=self._safe_insights)
            
            self.SSM = SharedStrategyManager(
                address=('', 50000), authkey=os.getenv('SSM_PASSWORD').encode())

        except Exception as e:
            print(f'Error in _startUISharedMemory: {e}')
            pass

    async def _insightListener(self):
        """ Listen to the insights and manage the orders. """
        assert callable(
            self.executeInsight), 'executeInsight must be a callable function'
        print('Running Insight Listener')
        loop = asyncio.get_running_loop()
        while self._Running:
            # TODO: could use a thread pool executor to run the executeInsight() functions
            for i in list(self.INSIGHTS):
                insight = self.INSIGHTS[i]
                if insight is None:
                    continue
                try:
                    # if self.VERBOSE > 0:
                    # print(f'Execute Insight: {
                    #     symbol}- {datetime.datetime.now()}')
                    # start_time = timeit.default_timer()

                    # Execute the insight Executors
                    passed = True
                    for executor in self.INSIGHT_EXECUTORS[insight.state]:
                        result = executor.run(
                            self.INSIGHTS[insight.INSIGHT_ID])
                        # Executor manage the insight state and mutates the insight
                        if not result.success:
                            print(f'Executor {result.executor}: {
                                  result.message}')
                            passed = False
                            break
                        elif not result.passed:
                            passed = False
                            break
                        if self.VERBOSE > 0:
                            print(
                                f'Executor {result.executor}: {result.message}')

                    if not passed:
                        continue

                    # TODO: also could feed latest price to the insight for better accr - maybe
                    self.executeInsight(self.INSIGHTS[insight.INSIGHT_ID])

                    # if self.VERBOSE > 0:
                    # print('Time taken executeInsight:', symbol,
                    #       timeit.default_timer() - start_time)
                except KeyError as e:
                    continue
                except Exception as e:
                    print('Error in _insightListener:', e)
                    continue
            if self.MODE == IStrategyMode.BACKTEST:
                try:
                    self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER.wait()
                except BrokenBarrierError as e:
                    # print('Error in _insightListener:', e)
                    pass
            else:
                await asyncio.sleep(2)
            # Update the account and positions
            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
        print("End of Insight Listener")

    async def _on_trade_update(self, trade):
        """ format the trade stream to the strategy. """
        orderdata, event = self.BROKER.format_on_trade_update(trade)
        # check if there is data and that the order symbol is in the universe
        if orderdata and orderdata['asset']['symbol'] not in self.UNIVERSE:
            # 'Order not in universe'
            return
        print(
            f"Order: {event:<16} {orderdata['created_at']}: {orderdata['asset']['symbol']:^6}: {str(orderdata['filled_qty']):^8} / {orderdata['qty']:^8} : {orderdata['type']} / {orderdata['order_class']} : {orderdata['side']} @ {orderdata['limit_price'] if orderdata['limit_price'] != None else orderdata['filled_price']} - {orderdata['order_id']}")
        self.ORDERS.append(orderdata)
        for i, insight in self.INSIGHTS.items():
            match insight.state:
                case InsightState.EXECUTED:
                    # We aleady know that the order has been executed becsue it will never be in the insights list as executed if it was not accepted by the broker
                    if insight.order_id == orderdata['order_id']:
                        match event:
                            case ITradeUpdateEvent.FILLED:
                                # Update the insight with the filled price
                                self.INSIGHTS[i].positionFilled(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata["filled_qty"])
                                break

                            # case ITradeUpdateEvent.CLOSED:
                            #     self.INSIGHTS[i].positionFilled(
                            #         orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['limit_price'], orderdata['qty'])

                            case ITradeUpdateEvent.PARTIAL_FILLED:
                                # keep track of partial fills as some positions may be partially filled and not fully filled. in these cases we need to update the insight with the filled quantity and price
                                self.INSIGHTS[i].partialFilled(
                                    orderdata['filled_qty'])
                                break

                            case ITradeUpdateEvent.CANCELED:
                                # TODO: Also check if we have been partially filled and remove the filled quantity from the insight
                                self.INSIGHTS[i].updateState(
                                    InsightState.CANCELED, 'Order Canceled')
                                break

                            case  ITradeUpdateEvent.REJECTED:
                                self.INSIGHTS[i].updateState(
                                    InsightState.REJECTED, 'Order Rejected')
                                break
                            case _:
                                pass
                case InsightState.FILLED | InsightState.CLOSED:
                    # Check if the position has been closed via SL or TP
                    if insight.symbol == orderdata['asset']['symbol']:
                        # Make sure the order is part of the insight as we dont have a clear way to tell if the closed fill is part of the strategy- to ensure that the the strategy is managed
                        if (event == ITradeUpdateEvent.FILLED) and ((((orderdata['qty'] == insight.quantity) and (orderdata['side'] != insight.side))) or
                                                                    (insight.close_order_id != None and insight.close_order_id == orderdata['order_id']) or
                                                                    (insight.order_id == orderdata['order_id'])):
                            # Update the insight closed price
                            if self.MODE != IStrategyMode.BACKTEST:
                                self.INSIGHTS[i].positionClosed(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['order_id'], orderdata['filled_qty'])
                            else:
                                self.INSIGHTS[i].positionClosed(
                                    orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['filled_price'], orderdata['order_id'], orderdata['filled_qty'])
                            break  # No need to continue

                        if len(insight.partial_closes) > 0:
                            for i, partialClose in enumerate(insight.partial_closes):
                                if partialClose['order_id'] == orderdata['order_id']:
                                    if (event == ITradeUpdateEvent.FILLED):
                                        # Update the insight closed price
                                        if self.MODE != IStrategyMode.BACKTEST:
                                            self.INSIGHTS[i].partial_closes[i].set_filled_price(
                                                orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'])
                                        else:
                                            self.INSIGHTS[i].partial_closes[i].set_filled_price(
                                                orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['filled_price'])
                                        break

        # TODOL Check if the order is part of the resolution of the strategy and has a insight that is managing it.

    def _loadUniverse(self):
        """ Loads the universe of the strategy."""
        assert callable(self.universe), 'Universe must be a callable function'
        universeSet = set(self.universe())
        for symbol in universeSet:
            self._loadAsset(symbol)
        assert (len(self.UNIVERSE) != 0), 'No assets loaded into the universe'

        for asset in self.UNIVERSE.values():
            # Init all assets in the strategy
            self._init(asset)

    def _loadAsset(self, symbol: str):
        """ Loads the asset into the universe of the strategy."""
        symbol = symbol.upper()
        assetInfo = self.BROKER.get_ticker_info(symbol)
        if assetInfo and assetInfo['status'] == 'active' and assetInfo['tradable']:
            self.UNIVERSE[assetInfo['symbol']] = assetInfo
            self.HISTORY[assetInfo['symbol']] = pd.DataFrame()
            print(
                f'Loaded {symbol}:{assetInfo["exchange"], }  into universe')
        else:
            print(f'Failed to load {symbol} into universe')

    def add_events(self, eventType: Literal['trade', 'quote', 'bar', 'news'] = 'bar', **kwargs):
        """ Adds bar streams to the strategy."""
        match eventType:
            case 'bar' | 'trade' | 'quote' | 'news':
                for assetInfo in self.UNIVERSE.values():
                    self.STREAMS.append(IMarketDataStream(symbol=assetInfo.get('symbol'), exchange=assetInfo.get(
                        'exchange'), time_frame=self.RESOLUTION, asset_type=assetInfo.get('asset_type'), type=eventType, **kwargs))
            case _:
                print(f"{eventType} Event not supported")

    def add_alpha(self, alpha: BaseAlpha):
        """ Adds an alpha to the strategy."""
        assert isinstance(
            alpha, BaseAlpha), 'alpha must be of type BaseAlpha object'

        alpha.registerAlpha()

    def add_alphas(self, alphas: List[BaseAlpha]):
        """ Adds a list of alphas to the strategy."""
        assert isinstance(
            alphas, List), 'alphas must be of type List[BaseAlpha] object'
        for alpha in alphas:
            self.add_alpha(alpha)

    def add_executor(self, executor: BaseExecutor):
        """ Adds an executor to the strategy."""
        assert isinstance(
            executor, BaseExecutor), 'executor must be of type BaseExecutor object'

        self.INSIGHT_EXECUTORS[executor.state].append(executor)

    def add_executors(self, executors: List[BaseExecutor]):
        """ Adds a list of executors to the strategy."""
        assert isinstance(
            executors, List), 'executors must be of type List[BaseExecutor] object'
        for executor in executors:
            self.add_executor(executor)

    def add_ta(self, ta: List[dict]):
        """ Adds a technical analysis to the strategy."""
        assert isinstance(
            ta, List), 'ta must be of type List[dict] object'
        if len(ta) == 0:
            return

        for ind in ta:
            if ind not in self.TaStrategy.ta:
                self.TaStrategy.ta.append(ind)

    def add_insight(self, insight: Insight):
        """ Adds an insight to the strategy."""
        assert isinstance(
            insight, Insight), 'insight must be of type Insight object'

        insight.set_mode(self.BROKER, self.assets[insight.symbol], self.MODE)

        self.INSIGHTS[insight.INSIGHT_ID] = insight

    async def _on_bar(self, bar: Any):
        """ format the bar stream to the strategy. """
        try:
            # set_index(['symbol', 'timestamp']

            if self.MODE != IStrategyMode.BACKTEST:
                data = self.BROKER.format_on_bar(bar)
            else:
                if bar.empty:
                    print('Bar is None')
                    return
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
                    if self.VERBOSE > 0:
                        print(f'New Bar is part of the resolution of the strategy: {
                              symbol} - {timestamp} - {datetime.datetime.now()}')
                        start_time = timeit.default_timer()

                    self.HISTORY[symbol] = pd.concat(
                        [self.HISTORY[symbol], data])
                    # Remove duplicates keys in the histoiry as sometimes when getting warm up data we get duplicates
                    self.HISTORY[symbol] = self.HISTORY[symbol].loc[~self.HISTORY[symbol].index.duplicated(
                        keep='first')]
                    # Needs to be warm up
                    if (len(self.HISTORY[symbol]) < self.WARM_UP):
                        print(f"Waiting for warm up: {
                              symbol} - {len(self.HISTORY[symbol])} / {self.WARM_UP}")
                        return

                    # Run the pandas TA
                    self.HISTORY[symbol].ta.strategy(self.TaStrategy)

                    # Call the on_bar function and process the bar
                    try:
                        self.on_bar(symbol, data)
                        self._generateInsights(symbol)
                    except Exception as e:
                        print('Error in on_bar:', e)

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
    # def get_variable(self, var='account'):
    #     """ Get a variable from the strategy class."""
    #     if not self.WITHUI:
    #         print('UI is not enabled')
    #         return None
    #     try:
    #         if getattr(self, var):
    #             return getattr(self, var)
    #     except AttributeError as e:
    #         return None
    

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
    def history(self) -> dict[str, pd.DataFrame]:
        """ Returns the orders of the strategy."""
        return self.HISTORY

    @property
    def insights(self) -> dict[str, Insight]:
        """ Returns the insights of the strategy."""
        return self.INSIGHTS
    def _safe_insights(self) -> dict[str, dict[str, Any]]:
        """ Returns the insights of the strategy. for the UI"""
        safe_insights = {}
        for insightID in self.INSIGHTS:
            insight = self.INSIGHTS[insightID]
            safe_insights[str(insightID)] = {
                'symbol': insight.symbol,
                'state': str(insight.state.value),
                'side': str(insight.side.value),
                'limit_price': insight.limit_price,
                'current_price': self.history[insight.symbol].iloc[-1]['close'],
                'take_profit': insight.TP,
                'stop_loss': insight.SL,
                'quantity': insight.quantity,
                'strategy': str(insight.strategyType),
                'execution_dependency': str(insight.executionDepends),
                'order_id': insight.order_id,
                'confidence': insight.confidence,
                'RRR': insight.getPnLRatio(),
                "TTL_unfilled": insight.periodUnfilled,
                "TTL_filled": insight.periodTillTp,
                'close_order_id': insight.close_order_id,
                'close_price': insight.close_price,
                'created_at': insight.createAt,
                'updated_at': insight.updatedAt,
                'filled_at': insight.filledAt,
                'closed_at': insight.closedAt,
            }
        return safe_insights
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
    def assets(self) -> dict[str, IAsset]:
        """ Returns the universe of the strategy."""
        return self.UNIVERSE

    @property
    def resolution(self) -> ITimeFrame:
        """ Returns the resolution of the strategy."""
        return self.RESOLUTION

    @property
    def tools(self) -> ITradingTools:
        """ Returns the tools of the strategy."""
        return self.TOOLS

    @property
    def streams(self) -> dict:
        """ Returns the streams of the strategy."""
        return self.STREAMS

    @property
    def warm_up(self) -> int:
        """ Returns the warm up period of the strategy."""
        return self.WARM_UP

    @warm_up.setter
    def warm_up(self, warm_up: int):
        """ Sets the warm up period of the strategy."""
        if warm_up < 0:
            raise ValueError('Warm up period must be greater than 0')
        if warm_up <= self.WARM_UP:
            # print('Warm up period cannot be reduced')
            return
        self.WARM_UP = warm_up
