import abc
import asyncio
from dataclasses import asdict
import functools
import os
from pathlib import Path
from threading import BrokenBarrierError
from time import sleep
from typing import Any, List, Optional, Literal
from uuid import uuid4, UUID
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import datetime
import nest_asyncio
import timeit
from collections import deque
import logging

import pandas_ta as ta
import pytz
from tqdm import tqdm
from vectorbt.portfolio import Portfolio

from ..broker.base_broker import BaseBroker
from ..broker.interfaces import IOrderSide, ISupportedBrokers, ITradeUpdateEvent, IAsset, IAccount, IPosition, IOrder

from .sharedmemory import SharedStrategyManager
from .interfaces import IBacktestingConfig, IMarketDataStream, IStrategyMatrics, IStrategyMode
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
    STRATEGY_ID: UUID = uuid4()
    NAME: str = "BaseStrategy"
    BROKER: BaseBroker
    ACCOUNT: Optional[IAccount] = None
    POSITIONS: dict[str, IPosition] = {}
    ORDERS: Optional[dict[str, IOrder]] = {}
    HISTORY: dict[str, pd.DataFrame] = {}
    INSIGHTS: dict[UUID, Insight] = {}
    UNIVERSE: dict[str, IAsset] = {}
    RESOLUTION = ITimeFrame(5, ITimeFrameUnit.Minute)
    STREAMS: List[IMarketDataStream] = []
    VARIABLES: AttributeDict
    MODE: IStrategyMode
    WITHUI: bool = True
    SSM: Optional[SharedStrategyManager] = None
    # DASHBOARD: Dashboard = None
    tradeOnFeatureEvents: bool = False

    TOOLS: Optional[ITradingTools] = None

    # DEBUG
    VERBOSE: int = 0

    _Running = False

    # ALPHA MODELS
    ALPHA_MODELS: List[BaseAlpha] = []
    """Alpha models to be used in the strategy"""

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
    shouldClosePartialFilledIfCancelled: bool = True
    """Insights that are partially filled and are cancelled should be closed if the insight is cancelled"""
    insightRateLimit: int = 1

    BACKTESTING_CONFIG: IBacktestingConfig = IBacktestingConfig(
        preemptiveTA=False)
    """Backtesting configuration"""
    BACKTESTING_RESULTS: dict[str, Portfolio] = {}
    """Backtesting results"""

    MATRICS: IStrategyMatrics = IStrategyMatrics()

    @abc.abstractmethod
    def __init__(self, broker: BaseBroker, variables: AttributeDict = AttributeDict({}), resolution: ITimeFrame = ITimeFrame(1, ITimeFrameUnit.Minute), verbose: int = 0, ui: bool = True, mode:
                 IStrategyMode = IStrategyMode.LIVE, tradeOnFeatureEvents: bool = False) -> None:
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
        self.tradeOnFeatureEvents = tradeOnFeatureEvents
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

        try:
            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            self.ORDERS = self.BROKER.get_orders()

            # Initialise the strategy metrics
            self.MATRICS.updateStart((pd.Timestamp(self.BROKER.get_current_time, tz='UTC')-datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds(), self.ACCOUNT.equity)

        except Exception as e:
            print(f'Failed to get account info from the broker {e}')
            pass

    @abc.abstractmethod
    def start(self):
        """ Start the strategy. This method is called once at the start of the strategy."""
        pass

    @abc.abstractmethod
    def init(self, asset: IAsset):
        """ Initialize the strategy. This method is called once before the start of the strategy on every asset in the universe."""

    @abc.abstractmethod
    def universe(self) -> set[str]:
        """ Used to generate the stock in play. """
        pass

    @abc.abstractmethod
    def on_bar(self, symbol: str, bar: dict):
        """ Called once per bar. open, high, low, close, volume """
        print('IS THIS WORKING, Add on_bar Function? ->  async def on_bar(self, bar):')
        pass

    @abc.abstractmethod
    def generateInsights(self, symbol: str):
        """Called once per bar to generate insights. """
        print('IS THIS WORKING, Add generateInsights Function? -> def generateInsights(self, symbol: str):')
        pass

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
        """Starts the strategy."""
        nest_asyncio.apply()
        self._Running = True

        self._start_strategy()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            with ThreadPoolExecutor(max_workers=5, thread_name_prefix="OlympusTrader") as pool:
                self._start_streams_and_listeners(loop, pool)
                self._run_strategy(loop, pool)
        except KeyboardInterrupt as e:
            print("Interrupted execution by user:", e)
            self._handle_close_streams(loop, pool)
        finally:
            self.run_teardown(loop)

    def _start_strategy(self):
        """Set up the strategy and check if the universe is empty."""
        self._start()
        assert len(self.UNIVERSE) > 0, 'Universe is empty'

    def _start_streams_and_listeners(self, loop, pool):
        """Start the trading data streams, market data streams, UI shared memory server, and insight listener."""
        self.TRADE_STREAM = loop.run_in_executor(
            pool, self.BROKER.startTradeStream, self._on_trade_update)
        self.MARKET_DATA_STREAM = loop.run_in_executor(
            pool, self.BROKER.streamMarketData, self._on_bar, self.STREAMS)
        self.INSIGHT_STREAM = loop.run_in_executor(pool, self._insightListener)

        if self.WITHUI:
            server = self.SSM.get_server()
            # Run the UI Shared Memory Server
            self.UI_SSM_STREAM = loop.run_in_executor(
                pool, server.serve_forever)
            from OlympusTrader.ui.__main__ import app
            # FIXME: Enabling dev tools is not working in a pool executor for some reason
            # if self.VERBOSE > 0:
            #     # Enable the dev tools
            #     app.enable_dev_tools(
            #         debug=True,
            #         dev_tools_ui=True,
            #         dev_tools_serve_dev_bundles=True,
            #         dev_tools_hot_reload=True
            #     )

            #     # Run the UI Dashboard Server in debug mode
            #     self.UI_STREAM = loop.run_in_executor(pool,  functools.partial(app.run, debug=True))
            # else:
            #     log = logging.getLogger('werkzeug')
            #     log.setLevel(logging.ERROR)
            #     # Run the UI Dashboard Server in production mode
            #     self.UI_STREAM = loop.run_in_executor(pool, functools.partial(app.run, host='0.0.0.0', threaded=True))
                # Run the UI Dashboard Server in production mode
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            
            self.UI_STREAM = loop.run_in_executor(pool, functools.partial(app.run, host='0.0.0.0', threaded=True))
            print('UI Shared Memory Server Started')

    def _run_strategy(self, loop, pool):
        """Run the strategy in backtest mode or live mode."""
        if self.MODE == IStrategyMode.BACKTEST:
            self._run_backtest()
        else:
            loop.run_forever()

        self.teardown()

    def _run_backtest(self):
        """Run the strategy in backtest mode."""
        while not self.BROKER.RUNNING_MARKET_STREAM or not self.BROKER.RUNNING_TRADE_STREAM:
            if self.BROKER.RUNNING_MARKET_STREAM and self.BROKER.RUNNING_TRADE_STREAM:
                break
        if self.VERBOSE > 0:
            print(f"Running Backtest - {datetime.datetime.now()}")
            start_time = timeit.default_timer()

        while self.BROKER.RUNNING_MARKET_STREAM and self.BROKER.RUNNING_TRADE_STREAM:
            if not self.BROKER.RUNNING_MARKET_STREAM or not self.BROKER.RUNNING_TRADE_STREAM:
                break

        if self.VERBOSE > 0:
            print('Backtest Completed:', timeit.default_timer() - start_time)
        # self.BACKTESTING_RESULTS = self.BROKER.get_VBT_results(self.resolution)
        # self.saveBacktestResults()

        raise KeyboardInterrupt("Backtest Completed")

    def _handle_close_streams(self, loop, pool):
        """Handle interruptions and ensure all streams and listeners are closed."""
        """Handle interruptions and ensure all streams and listeners are closed."""
        try:
            self.teardown()

            # Cancel all running tasks
            for task in asyncio.all_tasks(loop):
                task.cancel()

            # Cancel individual streams
            if hasattr(self, 'TRADE_STREAM'):
                self.TRADE_STREAM.cancel("From Main: Trade Stream Cancel")
            if hasattr(self, 'MARKET_DATA_STREAM'):
                self.MARKET_DATA_STREAM.cancel(
                    "From Main: Market Stream Cancel")
            if hasattr(self, 'INSIGHT_STREAM'):
                self.INSIGHT_STREAM.cancel()

            # Cancel UI streams if UI is enabled
            if self.WITHUI:
                if hasattr(self, 'UI_STREAM'):
                    self.UI_STREAM.cancel("From Main: UI Stream Cancel")
                if hasattr(self, 'UI_SSM_STREAM'):
                    self.UI_SSM_STREAM.cancel(
                        "From Main: UI SSM Stream Cancel")

            # Shutdown the thread pool
            pool.shutdown(wait=False, cancel_futures=True)
            # Stop the event loop
            loop.stop()

        except Exception as e:
            print(f"Error during interruption handling: {e}")
        finally:
            # Ensure the broker streams are closed
            asyncio.run(self.BROKER.closeTradeStream())
            asyncio.run(self.BROKER.closeStream(self.STREAMS))
            self._Running = False

    def run_teardown(self, loop):
        """Clean up resources and save backtest results if applicable."""
        asyncio.run(self.BROKER.closeTradeStream())
        asyncio.run(self.BROKER.closeStream(self.STREAMS))
        loop.stop()
        self._Running = False

        if self.MODE == IStrategyMode.BACKTEST and len(self.BACKTESTING_RESULTS) == 0:
            self.BACKTESTING_RESULTS = self.BROKER.get_VBT_results(
                self.resolution)
            self.saveBacktestResults()
            print("Simulation Account", self.BROKER.Account)

        exit(0)

    def saveBacktestResults(self):
        """ Save the backtest results."""
        if self.MODE != IStrategyMode.BACKTEST:
            print("Backtest results can only be saved in backtest mode")
            return
        # check if there are backtest results
        if len(self.BACKTESTING_RESULTS) == 0:
            print("No backtest results to save")
            return

        # Save the backtest results
        for symbol in tqdm(self.BACKTESTING_RESULTS.keys(), desc="Saving Backtest Results"):
            save_path = Path(f"backtests/{self.NAME}/{self.STRATEGY_ID}")
            save_path.mkdir(parents=True, exist_ok=True)
            path = f"{save_path}/{symbol}-{self.resolution}-backtest"
            if (self.BACKTESTING_RESULTS.get(symbol)):
                self.BACKTESTING_RESULTS[symbol].save(path)
                self.BACKTESTING_RESULTS[symbol].plot().show()
                print("Backtesting results saved for", symbol, "at", path)
            else:
                print("No backtesting results found for", symbol)

    def _startUISharedMemory(self):
        """ Starts the UI shared memory."""
        if not self.WITHUI:
            print('UI is not enabled')
            return
        try:
            assert os.getenv(
                "SSM_PASSWORD"), 'SSM_PASSWORD not found in environment variables'
            SharedStrategyManager.register(
                'get_strategy', callable=lambda: self)
            SharedStrategyManager.register(
                'get_account', callable=lambda: {str(key): v for key, v in asdict(self.account).items()})
            SharedStrategyManager.register(
                'get_mode', callable=lambda: self.MODE.value)
            SharedStrategyManager.register(
                'get_assets', callable=lambda: self.assets)
            SharedStrategyManager.register(
                'get_positions', callable=lambda: self.positions)
            SharedStrategyManager.register(
                'get_insights', callable=lambda: {str(key): asdict(insight.dataclass) for key, insight in self.INSIGHTS.items()})
            # SharedStrategyManager.register(
            #     'get_history', callable=lambda: { k : history_to_trading_view_format(v) for k, v in self.history.items() })
            SharedStrategyManager.register(
                'get_history', callable=lambda: self.history)
            SharedStrategyManager.register(
                'get_metrics', callable=lambda: asdict(self.metrics))
            # SharedStrategyManager.register(
            #     'get_time', callable=lambda:  pd.Timestamp(self.BROKER.get_current_time, tz='UTC').timestamp())
            
            SharedStrategyManager.register(
                'get_time', callable=lambda:  (pd.Timestamp(self.BROKER.get_current_time, tz='UTC')-datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds())

            self.SSM = SharedStrategyManager(
                address=('', 50000), authkey=os.getenv('SSM_PASSWORD').encode())
            print('UI Shared Memory Server configured')

        except Exception as e:
            print(f'Error in _startUISharedMemory: {e}')
            pass

    def _insightListener(self):
        """ Listen to the insights and manage the orders. """
        assert callable(
            self.executeInsight), 'executeInsight must be a callable function'
        print('Running Insight Listener')
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
                        if self.VERBOSE > 1:
                            print(
                                f'Executor {result.executor}: {result.message}')

                    if not passed:
                        continue

                    # latestInsight = self.INSIGHTS.get(insight.INSIGHT_ID)
                    # if latestInsight is not None:
                    #     self.executeInsight(self.INSIGHTS[insight.INSIGHT_ID])

                    self.executeInsight(insight)

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
                    # TODO: Should be checking if the backtesting range is completed but for now we will just break
                    break
            else:
                # await asyncio.sleep(1)
                sleep(self.insightRateLimit)
            # Update the account and positions
            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            if self.POSITIONS == None:
                self.POSITIONS = {}
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
        self.ORDERS[orderdata["order_id"]] = orderdata
        for i, insight in self.INSIGHTS.items():
            # Check if the insight is managing the order by checking the symbol
            if insight.symbol != orderdata['asset']['symbol']:
                continue

            match insight.state:
                case InsightState.EXECUTED:
                    # We aleady know that the order has been executed because it will never be in the insights list as executed if it was not accepted by the broker
                    if insight.order_id == orderdata['order_id']:
                        match event:
                            # case ITradeUpdateEvent.PENDING_NEW:
                            case ITradeUpdateEvent.NEW | ITradeUpdateEvent.PENDING_NEW:
                                if orderdata['legs']:
                                    insight.updateLegs(
                                        legs=orderdata['legs'])
                                return

                            case ITradeUpdateEvent.FILLED:
                                if orderdata['legs']:
                                    insight.updateLegs(
                                        legs=orderdata['legs'])
                                try:

                                    # Update the insight with the filled price
                                    insight.positionFilled(
                                        orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata["filled_qty"], orderdata['order_id'])
                                    self.MATRICS.positionOpened()
                                except AssertionError as e:
                                    continue
                                if insight.PARANT == None and len(insight.CHILDREN) > 0:
                                    # set the childe insight to be active
                                    for uid, childInsight in insight.CHILDREN.items():
                                        self.add_insight(childInsight)
                                    pass
                                return

                            case ITradeUpdateEvent.PARTIAL_FILLED:
                                # keep track of partial fills as some positions may be partially filled and not fully filled. in these cases we need to update the insight with the filled quantity and price
                                insight.partialFilled(
                                    orderdata['filled_qty'])
                                return

                            case ITradeUpdateEvent.CANCELED:
                                # check if we have been partially filled and remove the filled quantity from the insight
                                if insight._partial_filled_quantity != None and self.shouldClosePartialFilledIfCancelled:
                                    insight.updateState(
                                        InsightState.FILLED, 'Order Canceled, Closing Partial Filled Position')
                                    oldQuantity = insight.quantity
                                    if insight.uses_contract_size:
                                        insight.update_contracts(
                                            insight._partial_filled_quantity)
                                    else:
                                        insight.update_quantity(
                                            insight._partial_filled_quantity)
                                    if insight.close():
                                        pass
                                    else:
                                        print("Partial Filled Quantity Before Canceled: ",
                                              insight._partial_filled_quantity, " / ", oldQuantity, " - And Failed to close the position")
                                else:
                                    insight.updateState(
                                        InsightState.CANCELED, 'Order Canceled')
                                return

                            case  ITradeUpdateEvent.REJECTED:
                                insight.updateState(
                                    InsightState.REJECTED, 'Order Rejected')
                                return
                            case _:
                                pass
                case InsightState.FILLED | InsightState.CLOSED:
                    # Check if the position has been closed via SL or TP
                    # if insight.state == InsightState.CANCELED and insight._partial_filled_quantity == None:
                    #     # Check if we has a partial fill and need to get the results of the partial fill that was closed
                    #     break
                    if ((event == ITradeUpdateEvent.FILLED) or (event == ITradeUpdateEvent.CLOSED)):

                        if insight.state == InsightState.CLOSED:
                            # Insight has already been closed
                            continue
                        # check partials closes before closing the position
                        if len(insight.partial_closes) > 0:
                            for p, partialClose in enumerate(insight.partial_closes):
                                if partialClose['order_id'] == orderdata['order_id']:
                                    if (event == ITradeUpdateEvent.FILLED) or (event == ITradeUpdateEvent.CLOSED):
                                        # Update the insight closed price
                                        if self.MODE != IStrategyMode.BACKTEST:
                                            insight.partial_closes[p].set_filled_price(
                                                orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'])
                                        else:
                                            insight.partial_closes[p].set_filled_price(
                                                orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['filled_price'])

                                        closePnL = insight.partial_closes[p].getPL(
                                        )
                                        if insight.uses_contract_size:
                                            # TODO: might not to do this if quantity is in units of the contract size
                                            closePnL = closePnL * \
                                                insight.ASSET.get(
                                                    "contract_size")
                                        # Update the metrics with the closed PnL
                                        self.MATRICS.positionClosed(closePnL)
                                        return
                        # Make sure the order is part of the insight as we dont have a clear way to tell if the closed fill is part of the strategy- to ensure that the the strategy is managed well
                        if (((orderdata['qty'] == insight.quantity) and (orderdata['side'] != insight.side) and insight.close_order_id == None)) or \
                            ((insight.close_order_id != None) and (insight.close_order_id == orderdata['order_id'])) or \
                            (insight.order_id == orderdata['order_id']) or \
                            (insight.legs != None and
                                ((insight.takeProfitOrderLeg != None and orderdata['order_id'] == insight.takeProfitOrderLeg['order_id']) or
                                    (insight.stopLossOrderLeg != None and orderdata['order_id'] == insight.stopLossOrderLeg['order_id']) or
                                    (insight.trailingStopOrderLeg !=
                                     None and orderdata['order_id'] == insight.trailingStopOrderLeg['order_id'])
                                 )
                             ):
                            # Update the insight closed price
                            try:
                                if self.MODE != IStrategyMode.BACKTEST and self.broker.NAME != ISupportedBrokers.PAPER:
                                    insight.positionClosed(
                                        orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['order_id'], orderdata['filled_qty'])
                                else:
                                    insight.positionClosed(
                                        orderdata['stop_price'] if orderdata['stop_price'] != None else orderdata['filled_price'], orderdata['order_id'], orderdata['filled_qty'])

                                closePnL = 0
                                if insight.side == IOrderSide.BUY:
                                    closePnL = round(
                                        ((insight.close_price - insight.limit_price) * insight.quantity), 2)
                                else:
                                    closePnL = round(
                                        ((insight.limit_price - insight.close_price) * insight.quantity), 2)
                                if insight.uses_contract_size:
                                    # TODO: might not to do this if quantity is in units of the contract size
                                    closePnL = closePnL * \
                                        insight.ASSET.get("contract_size")

                                self.MATRICS.positionClosed(closePnL)
                                return  # No need to continue
                            except AssertionError as e:
                                continue

                    continue

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
            case 'bar':
                options: IMarketDataStream = {
                }

                if self.MODE == IStrategyMode.BACKTEST:
                    # Check if we should apply TA to the stream at the start of the backtest
                    if kwargs.get('applyTA', True):
                        options['applyTA'] = True
                        options['TA'] = self.TaStrategy
                        self.BACKTESTING_CONFIG['preemptiveTA'] = True
                    else:
                        options['applyTA'] = False
                        self.BACKTESTING_CONFIG['preemptiveTA'] = False

                    options['start'] = self.BROKER.START_DATE
                    options['end'] = self.BROKER.END_DATE
                    options['stored'] = kwargs.get('stored', False)
                    options['stored_path'] = kwargs.get('stored_path', "data")

                if kwargs.get('time_frame'):
                    options['time_frame'] = kwargs.get('time_frame')
                    if options['time_frame'] != self.RESOLUTION and not self.broker.supportedFeatures.featuredBarDataStreaming:
                        print(
                            "Feature Bar Data Streaming is not supported by the broker")
                        return
                else:
                    options['time_frame'] = self.RESOLUTION
                    options['feature'] = None

                for assetInfo in self.UNIVERSE.values():
                    assetDataStreamInfo = options.copy()
                    assetDataStreamInfo['symbol'] = assetInfo.get('symbol')
                    assetDataStreamInfo['exchange'] = assetInfo.get('exchange')
                    assetDataStreamInfo['asset_type'] = assetInfo.get(
                        'asset_type')
                    if options['time_frame'] != self.RESOLUTION:
                        assetDataStreamInfo['feature'] = f"{assetDataStreamInfo['symbol']}.{
                            assetDataStreamInfo['time_frame']}"
                        if assetDataStreamInfo['feature'] in self.HISTORY:
                            if not isinstance(self.HISTORY[assetDataStreamInfo['feature']], pd.DataFrame):
                                self.HISTORY[assetDataStreamInfo['feature']
                                             ] = pd.DataFrame()
                        else:
                            self.HISTORY[assetDataStreamInfo['feature']
                                         ] = pd.DataFrame()

                    assetDataStreamInfo['type'] = eventType
                    self.STREAMS.append(
                        IMarketDataStream(**assetDataStreamInfo))
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

    async def _on_bar(self, bar: Any, timeframe: ITimeFrame):
        """ format the bar stream to the strategy. """
        try:
            # set_index(['symbol', 'timestamp']
            data: pd.DataFrame = None
            if (self.MODE != IStrategyMode.BACKTEST and self.BROKER.NAME != ISupportedBrokers.PAPER) and not isinstance(bar, pd.DataFrame):
                data = self.BROKER.format_on_bar(bar)
            else:
                data = bar

            if data.empty:
                print('Bar is None')
                return

            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            self.ORDERS = self.BROKER.get_orders()

            if self.ORDERS == None:
                self.ORDERS = {}

            if self.POSITIONS == None:
                self.POSITIONS = {}

            if not data.empty:
                symbol = data.index[0][0]
                timestamp = data.index[0][1]
                if symbol == None:
                    if self.VERBOSE > 0:
                        print('Symbol is None - ignoring BaseStrategy_on_bar')
                    return
                # Check if the bar is part of the resolution of the strategy or if it is a feature event
                isFeature = False
                for stream in self.STREAMS:
                    if stream["type"] == "bar" and (stream['symbol'] == symbol or stream['feature'] == symbol) and stream['time_frame'].value != self.resolution.value:
                        if stream["time_frame"].value == timeframe.value and stream["time_frame"].is_time_increment(timestamp):
                            isFeature = True
                            # Update the feature symbol name
                            if stream['feature'] != symbol:
                                data.rename(
                                    index={symbol: stream['feature']}, inplace=True)
                                symbol = stream['feature']
                            if self.VERBOSE > 0:
                                print(f'Feature Bar is part of the resolution of the strategy: {
                                      symbol} - {timestamp} - {datetime.datetime.now()}')
                            break

                if (self.resolution.value == timeframe.value and self.resolution.is_time_increment(timestamp)) or isFeature:
                    if self.VERBOSE > 0:
                        print(f'New Bar is part of the resolution of the strategy: {
                              symbol} - {timestamp} - {datetime.datetime.now()}')
                        start_time = timeit.default_timer()

                    # TODO: check if the broker sends out multiple bar data when streaming bars with the same symbol

                    self.HISTORY[symbol] = pd.concat(
                        [self.HISTORY[symbol], data])
                    # Remove duplicates keys in the history as sometimes when getting warm up data we get duplicates
                    self.HISTORY[symbol] = self.HISTORY[symbol].loc[~self.HISTORY[symbol].index.duplicated(
                        keep='first')]
                    # Needs to be warm up
                    if (len(self.HISTORY[symbol]) < self.WARM_UP):
                        print(f"Waiting for warm up: {
                              symbol} - {len(self.HISTORY[symbol])} / {self.WARM_UP}")
                        return

                    if (not self.BACKTESTING_CONFIG.get('preemptiveTA') and self.MODE == IStrategyMode.BACKTEST) or (self.MODE != IStrategyMode.BACKTEST):
                        # Run the pandas TA
                        self.HISTORY[symbol].ta.strategy(self.TaStrategy)

                    # Call the on_bar function and process the bar
                    try:
                        if (isFeature == False) or (isFeature == True and self.tradeOnFeatureEvents):
                            self.on_bar(symbol, data)
                            self._generateInsights(symbol)
                    except Exception as e:
                        print('Error in on_bar:', e)

                    if self.VERBOSE > 0:
                        print('Time taken on_bar:', symbol,
                              timeit.default_timer() - start_time)
                else:
                    """ Bar is not part of the resolution of the strategy  nor is it a feature event"""
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

    @property
    def account(self) -> Optional[IAccount]:
        """ Returns the account of the strategy."""

        return self.ACCOUNT

    @property
    def positions(self) -> dict[str, IPosition]:
        """ Returns the positions of the strategy."""
        return self.POSITIONS

    @property
    def orders(self) -> Optional[dict[str, IOrder]]:
        """ Returns the orders of the strategy."""
        return self.ORDERS

    @property
    def history(self) -> dict[str, pd.DataFrame]:
        """ Returns the candle history of the strategy."""
        return self.HISTORY

    @property
    def insights(self) -> dict[UUID, Insight]:
        """ Returns the insights of the strategy."""
        return self.INSIGHTS

    @property
    def state(self) -> dict:
        """ Returns the state of the strategy."""
        return self.VARIABLES

    @state.setter
    def state(self, state: AttributeDict):
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
    def metrics(self) -> IStrategyMatrics:
        """ Returns the metrics of the strategy."""
        return self.MATRICS

    @property
    def resolution(self) -> ITimeFrame:
        """ Returns the resolution of the strategy."""
        return self.RESOLUTION

    @property
    def tools(self) -> ITradingTools:
        """ Returns the tools of the strategy."""
        return self.TOOLS

    @property
    def streams(self) -> List[IMarketDataStream]:
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
