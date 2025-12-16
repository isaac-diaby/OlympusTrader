from __future__ import annotations
import abc
import asyncio
from dataclasses import asdict
import functools
import os
from pathlib import Path
from threading import BrokenBarrierError
from time import sleep
from typing import Any, List, Optional, Literal, Self
from uuid import uuid4, UUID
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import datetime
import nest_asyncio
import timeit
from collections import deque
from typing import TYPE_CHECKING

import pandas_ta as ta
import pytz
from tqdm import tqdm
from vectorbt.portfolio import Portfolio

from ..broker.base_broker import BaseBroker
from ..broker.interfaces import (
    IOrderSide,
    ISupportedBrokers,
    ITradeUpdateEvent,
    IAsset,
    IAccount,
    IPosition,
    IOrder,
)

from .sharedmemory import SharedStrategyManager
from .interfaces import (
    IBacktestingConfig,
    IMarketDataStream,
    IStrategyMetrics,
    IStrategyMode,
)
from ..insight.insight import Insight, InsightState
from ..utils.timeframe import ITimeFrame, ITimeFrameUnit
from ..utils.types import AttributeDict
from ..utils.tools import ITradingTools

from ..alpha.base_alpha import BaseAlpha

from OlympusTrader.insight.executors import BaseExecutor

# from ..insight.executors.base_executor import BaseExecutor
# from ..ui.base_ui import Dashboard
import warnings


import asyncio
import functools
import logging
import signal
import types
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional


# ----------------------------
# Types / Protocols
# ----------------------------


AsyncCallback = Callable[..., Awaitable[None]]
AssetStream = Dict[str, Any]

warnings.simplefilter(action="ignore", category=FutureWarning)

@dataclass
class BaseStrategy(abc.ABC):
    BROKER: BaseBroker
    """Broker for the strategy"""
    RESOLUTION: ITimeFrame = field(default_factory=lambda: ITimeFrame(5, ITimeFrameUnit.Minute))
    """Resolution for the strategy"""
    MODE: IStrategyMode = field(default=IStrategyMode.BACKTEST)
    """Strategy mode"""

    STRATEGY_ID: UUID =field(default_factory=uuid4)
    """Unique ID for the strategy"""
    NAME: str = "BaseStrategy"
    """Name of the strategy"""
    ACCOUNT: Optional[IAccount] = field(default_factory=dict)
    """Account for the strategy"""
    POSITIONS: dict[str, IPosition] = field(default_factory=dict)
    """Positions for the strategy"""
    ORDERS: Optional[dict[str, IOrder]] = field(default_factory=dict)
    """Orders for the strategy"""
    HISTORY: dict[str, pd.DataFrame] = field(default_factory=dict)
    """History for the strategy"""
    INSIGHTS: dict[UUID, Insight] = field(default_factory=dict)
    """Insights for the strategy"""
    UNIVERSE: dict[str, IAsset] = field(default_factory=dict)
    """Universe of assets for the strategy"""
   
    STREAMS: List[IMarketDataStream] = field(default_factory=list)
    """Market Data Streams for the strategy"""
    VARIABLES: AttributeDict = field(default_factory=lambda: AttributeDict({}))
    """Variables for the strategy"""
   
    WITHUI: bool = True
    """Enable UI for the strategy"""
    WITHSSM: bool = True
    """Enable Shared Strategy Manager for the strategy functions""" 
    SSM: Optional[SharedStrategyManager] = None
    """Shared Strategy Manager for the strategy functions"""
    tradeOnFeatureEvents: bool = field(default=False)
    """Trade on feature events"""

    TOOLS: Optional[ITradingTools] = field(default=None)
    """Trading tools for the strategy"""

    # DEBUG
    VERBOSE: int = 0
    """Verbose level for the strategy"""
    LOGGER: logging.Logger = None

    _RUNNING = False
    """Running flag for the strategy"""

    # ALPHA MODELS
    ALPHA_MODELS: List[BaseAlpha] = field(default_factory=list)
    """Alpha models to be used in the strategy"""

    INSIGHT_EXECUTORS: dict[InsightState, deque[BaseExecutor]] = field(default_factory=lambda: {
        InsightState.NEW: deque(),
        InsightState.EXECUTED: deque(),
        InsightState.FILLED: deque(),
        InsightState.CLOSED: deque(),
        InsightState.REJECTED: deque(),
        InsightState.CANCELED: deque(),
        })
    """Insight Executors Models"""
    TaStrategy: ta.Study = None
    """TA Strategy"""
    WARM_UP: int = 0
    """Warm up bars for the strategy to ensure the strategy has enough data to make decisions"""
    execution_risk: float = 0.01
    """Execution risk per trade"""
    minRewardRiskRatio: float = 2.0
    """Minimum Reward to Risk Ratio required for the strategy"""
    baseConfidence: float = 0.1
    """Base Confidence level for the strategy"""
    shouldClosePartialFilledIfCancelled: bool = True
    """Insights that are partially filled and are cancelled should be closed if the insight is cancelled"""
    insightRateLimit: int = 1
    """Insight rate limit"""

    BACKTESTING_CONFIG: IBacktestingConfig =  field(default_factory=lambda: IBacktestingConfig(preemptiveTA=False))
    """Backtesting configuration"""
    BACKTESTING_RESULTS: dict[str, Portfolio] = field(default_factory=dict)
    """Backtesting results"""

    METRICS: IStrategyMetrics = field(default_factory=IStrategyMetrics)
    """Strategy metrics"""

    # Internal task registry
    _tasks: Dict[str, asyncio.Task] = field(default_factory=dict, init=False)
    _watchdog_timeout: int = 30
    _teardown_timeout: int = 30

    # Internal Optimiser
    _MAX_HISTORY_SIZE: int = field(default=1000) # Max history size for the strategy

    # def __init__(
    #     self,
    #     broker: BaseBroker,
    #     variables: AttributeDict = AttributeDict({}),
    #     resolution: ITimeFrame = ITimeFrame(1, ITimeFrameUnit.Minute),
    #     verbose: int = 0,
    #     ui: bool = True,
    #     ssm: bool = True,
    #     mode: IStrategyMode = IStrategyMode.LIVE,
    #     tradeOnFeatureEvents: bool = False,
    # ) -> None:
    # @abc.abstractmethod
    def __post_init__(self):
        """Abstract class for strategy implementations."""
        self.NAME = self.__class__.__name__
        self.LOGGER = logging.getLogger("OlympusTrader."+self.NAME)
        # self.VERBOSE = verbose  # TODO: Log Levels should be an derived from env file
        logging.basicConfig(level=logging.INFO)
        if self.VERBOSE > 0:
            self.LOGGER.setLevel(logging.DEBUG)
        else:
            self.LOGGER.setLevel(logging.INFO)


        if not isinstance(self.VARIABLES, AttributeDict):
            self.VARIABLES = AttributeDict(self.VARIABLES)

        self.TOOLS = ITradingTools(self)

        # Validate timeframe
        assert ITimeFrame.validate_timeframe(
            self.RESOLUTION.amount, self.RESOLUTION.unit
        ), "Resolution must be a valid timeframe"

       # Shared memory server
        if self.WITHUI:
            self.WITHSSM = True

        if self.WITHSSM:
            self._startUISharedMemory()

        # Set up TA Strategy
        self.TaStrategy = ta.Study(
            name=self.NAME, description="Olympus Trader Framework", ta=[]
        )
        self.start()
        # Load the universe
        self._loadUniverse()

        # Set backtesting configuration
        if self.MODE == IStrategyMode.BACKTEST:
            # check if the broker is paper
            assert (
                self.BROKER.NAME == ISupportedBrokers.PAPER
            ), "Backtesting is only supported with the paper broker"
            # # change the broker to feed to backtest mode
            # self.BROKER.feed = IStrategyMode.BACKTEST
            pass

        try:
            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            self.ORDERS = self.BROKER.get_orders()

            # Initialise the strategy metrics
            self.METRICS.updateStart(
                (
                    pd.Timestamp(self.BROKER.get_current_time, tz="UTC")
                    - datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)
                ).total_seconds(),
                self.ACCOUNT.equity,
            )

        except Exception as e:
            self.LOGGER.error(f"Failed to get account info from the broker {e}")


    @abc.abstractmethod
    def start(self):
        """Start the strategy. This method is called once at the start of the strategy."""
        pass

    @abc.abstractmethod
    def init(self, asset: IAsset):
        """Initialize the strategy. This method is called once before the start of the strategy on every asset in the universe."""

    @abc.abstractmethod
    def universe(self) -> set[str]:
        """Used to generate the stock in play."""
        pass

    @abc.abstractmethod
    def on_bar(self, symbol: str, bar: dict):
        """Called once per bar. open, high, low, close, volume"""
        print("IS THIS WORKING, Add on_bar Function? ->  async def on_bar(self, bar):")
        pass

    @abc.abstractmethod
    def generateInsights(self, symbol: str):
        """Called once per bar to generate insights."""
        print(
            "IS THIS WORKING, Add generateInsights Function? -> def generateInsights(self, symbol: str):"
        )
        pass

    @abc.abstractmethod
    def executeInsight(self, insight: Insight):
        """Called for each active insight in the strategy.
        it allows you to conrol the execution of the insight and manage the order.
        ### Example:
        ```python
        def executeInsight(self, insight: Insight):
            match insight.state:
                case InsightState.NEW:
                    pass
                case InsightState.EXECUTED:
                    pass
                case InsightState.FILLED:
                    pass
                case InsightState.CLOSED:
                    pass
                case InsightState.REJECTED:
                    pass
                case InsightState.CANCELED:
                    pass
                case _:
                    pass
        ```

        """
        print(
            "IS THIS WORKING, Add executeInsight Function? ->  async def executeInsight(self, symbol: str):"
        )
        # match insight.state:
        #     # case InsightState.NEW:
        #     #     pass
        #     # case InsightState.EXECUTED:
        #     #     pass
        #     # case InsightState.FILLED:
        #     #     pass
        #     # case InsightState.CLOSED:
        #     #     pass
        #     # case InsightState.REJECTED:
        #     #     pass
        #     # case InsightState.CANCELED:
        #     #     pass
        #     case _:
        #         print(
        #             "Implement the insight state in the executeInsight function:",
        #             insight.state,
        #         )
        #         pass

    @abc.abstractmethod
    def teardown(self):
        """Called once at the end of the strategy."""
        self.LOGGER.info("Tear Down: Closing all positions")
        self.BROKER.close_all_positions()


    def _init(self, asset: IAsset):
        """Initialize the strategy."""
        assert callable(self.init), "init must be a callable function"
        for alpha in self.ALPHA_MODELS:
            alpha.init(asset)
        self.init(asset)

    def _generateInsights(self, symbol: str):
        """Generate insights for the strategy."""
        assert callable(
            self.generateInsights
        ), "generateInsights must be a callable function"
        for alpha in self.ALPHA_MODELS:
            if not alpha.isAllowedAsset(symbol):
                continue
            result = alpha.generateInsights(symbol)
            if result.success:
                if result.insight is not None:
                    self.add_insight(result.insight)
            else:
                self.LOGGER.warning(f"Alpha {result.alpha} Failed: {result.message}")

        self.generateInsights(symbol)

    def run(self):
        """Starts the strategy."""
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.LOGGER.info("Stopped by user")

    async def _run(self) -> None:
        """Top-level entry."""
        self._RUNNING = True
        await self._start_strategy()
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _signal_handler():
            self.LOGGER.info("Received stop signal")
            self._RUNNING = False
            stop_event.set()

        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(s, _signal_handler)
            except NotImplementedError:
                # Windows or event loop implementations may not support it
                pass

        # Safety watchdog to force exit if shutdown hangs (e.g. blocked sync calls)
        async def _shutdown_watchdog():
            await stop_event.wait()
            self.LOGGER.info(f"Shutdown initiated. Watchdog waiting {self._watchdog_timeout}s...")
            try:
                await asyncio.sleep(self._watchdog_timeout)
            except asyncio.CancelledError:
                return
            self.LOGGER.warning("Shutdown timed out. Forcing exit via watchdog.")
            import os
            os._exit(1)
            
        watchdog_task = asyncio.create_task(_shutdown_watchdog())

        async with AsyncExitStack() as stack:
            # In backtest mode, start UI/SSM servers OUTSIDE the main TaskGroup
            # so they persist after backtest completes
            ui_ssm_tasks = []
            if self.MODE == IStrategyMode.BACKTEST and (self.WITHUI or self.WITHSSM):
                ui_ssm_tasks = await self._start_ui_ssm_servers()
            
            # Create a TaskGroup for lifetime of strategy (market/trade/insight tasks)
            async with asyncio.TaskGroup() as tg:
                # Start streams/listeners/tasks
                await self._start_streams_and_listeners(tg)

                # Start the main strategy loop
                main_task = tg.create_task(self._run_strategy(), name="strategy_main")

                # Wait until a stop signal OR the strategy loop finishes (backtest done)
                # We wrap stop_event.wait() in a task so we can wait on it in asyncio.wait
                stop_task = tg.create_task(stop_event.wait(), name="stop_signal_waiter")

                self.LOGGER.info("Waiting for main_task or stop_task...")
                done, pending = await asyncio.wait(
                    [main_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                self.LOGGER.info(f"asyncio.wait returned. done count={len(done)}")

                # Track whether strategy completed naturally
                strategy_completed = main_task in done
                
                # If main_task finished (strategy done), stop everything and exit
                if strategy_completed:
                    self.LOGGER.info("Strategy main loop finished. Stopping...")
                    
                    # Run teardown logic (save results, close positions)
                    try:
                        await asyncio.wait_for(self._shutdown(), timeout=self._teardown_timeout)
                    except Exception as e:
                        self.LOGGER.exception(f"Error during teardown: {e}")

                    # Signal to stop the broker streams
                    self._RUNNING = False
                    if hasattr(self.BROKER, 'closeTradeStream'):
                        try:
                            await self.BROKER.closeTradeStream()
                        except Exception as e:
                            self.LOGGER.exception(f"Error closing trade stream: {e}")
                    
                    # Set stop event to trigger TaskGroup exit
                    stop_event.set()
                else:
                    # Stopped by user (Ctrl+C)
                    self.LOGGER.info("Strategy stopped by user. Cancelling main task...")
                    main_task.cancel()
                    try:
                        await main_task
                    except asyncio.CancelledError:
                        self.LOGGER.info("Main task cancelled")
                    
                    # Run teardown logic immediately
                    self.LOGGER.info("Running teardown before cancelling streams...")
                    try:
                        await asyncio.wait_for(self._shutdown(), timeout=20)
                    except Exception as e:
                        self.LOGGER.exception(f"Error during teardown: {e}")

                # Signal tasks to stop
                self.LOGGER.info("Cancelling tasks...")
                if hasattr(self, 'trade_stream') and not self.trade_stream.done():
                    self.trade_stream.cancel()
                    self.LOGGER.info("Cancelled trade_stream")
                if hasattr(self, 'market_data_stream') and not self.market_data_stream.done():
                    self.market_data_stream.cancel()
                    self.LOGGER.info("Cancelled market_data_stream")
                if hasattr(self, 'insight_listener') and not self.insight_listener.done():
                    self.insight_listener.cancel()
                    self.LOGGER.info("Cancelled insight_listener")
                
                # Exiting the TaskGroup context will cancel all remaining tasks
                self.LOGGER.info("Exiting TaskGroup...")

        self.LOGGER.info("TaskGroup exited.")
        # _shutdown() moved inside TaskGroup to ensure it runs before exit hangs

        # In BACKTEST mode, if UI/SSM are running and strategy completed naturally,
        # keep them alive for inspection
        if self.MODE == IStrategyMode.BACKTEST and ui_ssm_tasks and strategy_completed:
            self.LOGGER.info("Strategy complete. UI/SSM servers still running. Press Ctrl+C to exit.")
            # Clear the stop_event since it was set to exit the TaskGroup
            # Now we need to wait for a fresh SIGINT from the user
            stop_event.clear()
            try:
                # Wait for SIGINT
                await stop_event.wait()
            except asyncio.CancelledError:
                pass
        
        # Shutdown UI/SSM servers for ALL modes (LIVE, BACKTEST, etc.)
        if ui_ssm_tasks:
            self.LOGGER.info("Shutting down UI/SSM servers...")
            if hasattr(self, '_ssm_server'):
                try:
                    self._ssm_server.shutdown()
                except Exception as e:
                    self.LOGGER.debug(f"Error shutting down SSM server: {e}")
            # Cancel the tasks
            for task in ui_ssm_tasks:
                task.cancel()

        self.LOGGER.info("Strategy stopped")
        
        # Force exit if UI/SSM servers were running OR if in LIVE mode
        # (broker executor threads and websocket connections don't stop gracefully)
        if ui_ssm_tasks or self.MODE == IStrategyMode.LIVE:
            import os
            self.LOGGER.info("Forcing process exit to stop background threads...")
            os._exit(0)
        
        watchdog_task.cancel()
        return
        

    async def _start_strategy(self):
        """Set up the strategy and check if the universe is empty."""
        assert len(self.UNIVERSE) > 0, "Universe is empty"

        for alpha in self.ALPHA_MODELS:
            alpha.start()

# -------------------- stream and listener management --------------------
    async def _start_ui_ssm_servers(self):
        """Start UI and SSM servers outside the main TaskGroup.
        Returns a list of tasks that can be cancelled later.
        """
        tasks = []
        
        # Shared memory server (blocking) -> run in thread
        if self.WITHSSM and hasattr(self, "SSM"):
            self._ssm_server = self.SSM.get_server()
            task = asyncio.create_task(
                asyncio.to_thread(self._ssm_server.serve_forever), 
                name="ssm_server"
            )
            tasks.append(task)
            self.LOGGER.info("UI Shared Memory Server started")

            # UI server
            if self.WITHUI:
                try:
                    from OlympusTrader.ui.app import app
                    import functools

                    logging.getLogger("werkzeug").setLevel(logging.ERROR)
                    task = asyncio.create_task(
                        asyncio.to_thread(
                            functools.partial(app.run, host="0.0.0.0", threaded=True)
                        ),
                        name="ui_server",
                    )
                    tasks.append(task)
                    self.LOGGER.info("UI Dashboard Server started")
                except Exception as e:
                    self.LOGGER.exception(f"Failed to start UI server: {e}")
        
        return tasks

    async def _start_streams_and_listeners(self, tg: asyncio.TaskGroup) -> None:
        """Start broker streams, insight listener, shared servers, and UI.

        - `tg` is an asyncio.TaskGroup in which tasks should be created.
        - Non-async (blocking) servers are executed via asyncio.to_thread
        """
        # Start trade stream
        if hasattr(self.broker, "startTradeStream"):
            self.trade_stream = tg.create_task(
            self.broker.startTradeStream(self._on_trade_update),
            name="trade_stream",
            )
            self.LOGGER.info("Trade stream started")

        # Start market data stream
        if hasattr(self.broker, "streamMarketData"):
            self.market_data_stream = tg.create_task(
            self.broker.streamMarketData(self._on_bar, self.STREAMS),
            name="market_data_stream",
            )
            self.LOGGER.info("Market data stream started")

        # Start insight listener if defined
        if hasattr(self, "_insightListener"):
            self.insight_listener = tg.create_task(self._insightListener(), name="insight_listener")

        # In backtest mode, UI/SSM are started separately outside TaskGroup
        # In live mode, start them here within the TaskGroup
        if self.MODE != IStrategyMode.BACKTEST:
            # Shared memory server (blocking) -> run in thread
            if self.WITHSSM and hasattr(self, "SSM"):
                self._ssm_server = self.SSM.get_server()
                tg.create_task(
                asyncio.to_thread(self._ssm_server.serve_forever), name="ssm_server"
                )
                self.LOGGER.info("UI Shared Memory Server started")

                # UI server (e.g. Flask) - run in thread to avoid blocking
                if self.WITHUI:
                    try:
                        from OlympusTrader.ui.app import app


                        logging.getLogger("werkzeug").setLevel(logging.ERROR)
                        tg.create_task(
                        asyncio.to_thread(
                        functools.partial(app.run, host="0.0.0.0", threaded=True)
                        ),
                        name="ui_server",
                        )
                        self.LOGGER.info("UI Dashboard Server started")
                    except Exception as e:
                        self.LOGGER.exception(f"Failed to start UI server: {e}")
        return
    async def _run_strategy(self):
        """Run the strategy in backtest mode or live mode."""
        self.LOGGER.info("_run_strategy: starting")

        if self.MODE == IStrategyMode.BACKTEST:
            await self._run_backtest_loop()
        else:
            # Live mode: just stay alive until _RUNNING is False
            try:
                while not getattr(self.BROKER, 'RUNNING_MARKET_STREAM', False) or not getattr(self.BROKER, 'RUNNING_TRADE_STREAM', False):
                    await asyncio.sleep(0)
                while getattr(self.BROKER, 'RUNNING_MARKET_STREAM', False) and getattr(self.BROKER, 'RUNNING_TRADE_STREAM', False) and self._RUNNING:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                self.LOGGER.info("_run_strategy: cancelled")
                raise

        self.LOGGER.info("_run_strategy_loop: exiting")
        return

    async def _run_backtest_loop(self) -> None:
        """Backtest loop: waits for streams to start and controls backtest flow."""
        # Wait until both market and trade streams are _RUNNING
        while not getattr(self.BROKER, 'RUNNING_MARKET_STREAM', False) or not getattr(self.BROKER, 'RUNNING_TRADE_STREAM', False):
            await asyncio.sleep(0.1)

        if self.VERBOSE > 0:
            import datetime, timeit
            self.LOGGER.info(f"Running Backtest - {datetime.datetime.now()}")
            start_time = timeit.default_timer()

        # Main backtest control loop
        while getattr(self.BROKER, 'RUNNING_MARKET_STREAM', False) and getattr(self.BROKER, 'RUNNING_TRADE_STREAM', False):
            try:
                self.LOGGER.debug(f"Backtest itter: {self.BROKER.BACKTEST_FlOW_CONTROL._step_id}" )
                await self.BROKER.BACKTEST_FlOW_CONTROL.wait_for_market()
                await asyncio.sleep(0)
                # await asyncio.to_thread(self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER.wait)
            except asyncio.CancelledError:
                self.LOGGER.info("Backtest loop cancelled")
                break

        if self.VERBOSE > 0:
            self.LOGGER.info("Backtest Completed:", timeit.default_timer() - start_time)

    async def run_teardown(self):
        """Clean up resources and save backtest results if applicable."""
        self.teardown()

        if self.MODE == IStrategyMode.BACKTEST and len(self.BACKTESTING_RESULTS) == 0:
            self.BACKTESTING_RESULTS = self.BROKER.get_VBT_results(self.resolution)
            self.saveBacktestResults()

        self.ACCOUNT = self.BROKER.get_account()
        self.LOGGER.info(f"End Account: {self.ACCOUNT}")
        
        self.METRICS.updateEnd(
            (
                pd.Timestamp(self.BROKER.get_current_time, tz="UTC")
                - datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)
            ).total_seconds(),
            self.ACCOUNT.equity,
        )
        self.LOGGER.info(f"Trade METRICS: {self.METRICS}")

    def saveBacktestResults(self):
        """Save the backtest results."""
        if self.MODE != IStrategyMode.BACKTEST:
            self.LOGGER.info("Backtest results can only be saved in backtest mode")
            return
        # check if there are backtest results
        if len(self.BACKTESTING_RESULTS) == 0:
            self.LOGGER.info("No backtest results to save")
            return

        # Save the backtest results
        for symbol in tqdm(
            self.BACKTESTING_RESULTS.keys(), desc="Saving Backtest Results"
        ):
            save_path = Path(f"backtests/{self.NAME}/{self.STRATEGY_ID}")
            save_path.mkdir(parents=True, exist_ok=True)
            path = f"{save_path}/{symbol}-{self.resolution}-backtest"
            if self.BACKTESTING_RESULTS.get(symbol):
                self.BACKTESTING_RESULTS[symbol].save(path)
                self.BACKTESTING_RESULTS[symbol].plot().show()
                self.LOGGER.info(f"Backtesting results saved for {symbol} at {path}")
            else:
                self.LOGGER.info(f"No backtesting results found for {symbol}")

        # Save the account history
        self.BROKER.export_trade_log()
        self.BROKER.export_vbt_signals(list(self.UNIVERSE.keys())[0])

    def _startUISharedMemory(self):
        """Starts the UI shared memory."""
        if not self.WITHSSM:
            print("SSM is not enabled")
            return
        try:
            assert os.getenv(
                "SSM_PASSWORD"
            ), "SSM_PASSWORD not found in environment variables"
            SharedStrategyManager.register("get_strategy", callable=lambda: self)
            SharedStrategyManager.register(
                "get_account",
                callable=lambda: {
                    str(key): v for key, v in asdict(self.account).items()
                },
            )
            SharedStrategyManager.register("get_mode", callable=lambda: self.MODE.value)
            SharedStrategyManager.register("get_assets", callable=lambda: self.assets)
            SharedStrategyManager.register(
                "get_positions", callable=lambda: self.positions
            )
            SharedStrategyManager.register(
                "get_insights",
                callable=lambda: {
                    str(key): asdict(insight.dataclass)
                    for key, insight in self.INSIGHTS.items()
                },
            )
            # SharedStrategyManager.register(
            #     'get_history', callable=lambda: { k : history_to_trading_view_format(v) for k, v in self.history.items() })
            SharedStrategyManager.register("get_history", callable=lambda: self.history)
            SharedStrategyManager.register(
                "get_metrics", callable=lambda: asdict(self.metrics)
            )
            # SharedStrategyManager.register(
            #     'get_time', callable=lambda:  pd.Timestamp(self.BROKER.get_current_time, tz='UTC').timestamp())

            SharedStrategyManager.register(
                "get_time",
                callable=lambda: (
                    pd.Timestamp(self.BROKER.get_current_time, tz="UTC")
                    - datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)
                ).total_seconds(),
            )

            self.SSM = SharedStrategyManager(
                address=("", 50000), authkey=os.getenv("SSM_PASSWORD").encode()
            )
            self.LOGGER.info("UI Shared Memory Server configured")

        except Exception as e:
            self.LOGGER.error(f"Error in _startUISharedMemory: {e}")
            pass

    async def _insightListener(self):
        """Listen to the insights and manage the orders."""
        assert callable(
            self.executeInsight
        ), "executeInsight must be a callable function"
        self.LOGGER.info("Running Insight Listener")
        self.ACCOUNT = await asyncio.to_thread(self.BROKER.get_account)
        self.POSITIONS = await asyncio.to_thread(self.BROKER.get_positions)
        if self.POSITIONS == None:
            self.POSITIONS = {}
        try:
            while self._RUNNING:

                if self.MODE == IStrategyMode.BACKTEST:
                    # Wait for market producers to finish this timestep
                    await self.BROKER.BACKTEST_FlOW_CONTROL.wait_for_market()
                else:
                    await asyncio.sleep(self.insightRateLimit if (self.insightRateLimit >= 0) else 1)

                for i in list(self.INSIGHTS):
                    insight = self.INSIGHTS.get(i, None)
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
                            if not executor.should_run(insight):
                                continue                            
                            result = executor.run(self.INSIGHTS[insight.INSIGHT_ID])
                            # Executor manage the insight state and mutates the insight
                            if not result.success:
                                self.LOGGER.error(
                                    f"Executor {result.executor}: {result.message}"
                                )
                                passed = False
                                break
                            elif not result.passed:
                                passed = False
                                break
                            self.LOGGER.debug(f"Executor {result.executor}: {result.message}")

                        if not passed:
                            continue

                        # latestInsight = self.INSIGHTS.get(insight.INSIGHT_ID)
                        # if latestInsight is not None:
                        #     self.executeInsight(self.INSIGHTS[insight.INSIGHT_ID])

                        self.executeInsight(insight)

                        # Change the flag to indicate that the insight has been ran once against the executor list
                        if insight.state == InsightState.FILLED and insight._first_on_fill:
                            insight._first_on_fill = False

                        # if self.VERBOSE > 0:
                        # print('Time taken executeInsight:', symbol,
                        #       timeit.default_timer() - start_time)
                    except KeyError as e:
                        continue
                    except Exception as e:
                        self.LOGGER.error("Error in _insightListener:", e)
                        continue

                if self.MODE == IStrategyMode.BACKTEST:
                    # signal insight stage done
                    await self.BROKER.BACKTEST_FlOW_CONTROL.report_insight()
                # note: we do NOT step_complete here; trade will signal trade complete, then market will call step_complete()
                # Wait small time to yield control (optional)
                await asyncio.sleep(0)

                # if self.MODE == IStrategyMode.BACKTEST:
                #     try:
                #         await asyncio.to_thread(self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER.wait)
                #     except BrokenBarrierError as e:
                #         # print('Error in _insightListener:', e)
                #         # TODO: Should be checking if the backtesting range is completed but for now we will just break
                #         break
                
                # Update the account and positions
                self.ACCOUNT = await asyncio.to_thread(self.BROKER.get_account)
                self.POSITIONS = await asyncio.to_thread(self.BROKER.get_positions)
                if self.POSITIONS == None:
                    self.POSITIONS = {}
        except asyncio.CancelledError:
            pass
        finally:
            self._INSIGHT_RUNNING = False
        self.LOGGER.info("End of Insight Listener")
        return

    async def _on_trade_update(self, trade):
        """format the trade stream to the strategy."""
        orderdata, event = self.BROKER.format_on_trade_update(trade)
        # check if there is data and that the order symbol is in the universe
        if orderdata and orderdata["asset"]["symbol"] not in self.UNIVERSE:
            # 'Order not in universe'
            return
        self.LOGGER.info(
            f"Order: {event:<16} {orderdata['created_at']}: {orderdata['asset']['symbol']:^6}: {str(orderdata['filled_qty']):^8} / {orderdata['qty']:^8} : {orderdata['type']} / {orderdata['order_class']} : {orderdata['side']} @ {orderdata['limit_price'] if orderdata['limit_price'] is not None else orderdata['filled_price']} - {orderdata['order_id']}"
        )
        self.ORDERS[orderdata["order_id"]] = orderdata
        for i, insight in self.INSIGHTS.items():
            # Check if the insight is managing the order by checking the symbol
            if insight.symbol != orderdata["asset"]["symbol"]:
                continue

            match insight.state:
                case InsightState.NEW:
                    if orderdata["order_id"] == insight.order_id:
                        match event:
                            case ITradeUpdateEvent.PENDING_NEW:
                                if orderdata["legs"]:
                                    insight.updateLegs(legs=orderdata["legs"])
                                insight.updateState(
                                    InsightState.EXECUTED, "Order Pending"
                                )
                                return
                            case ITradeUpdateEvent.NEW:
                                if orderdata["legs"]:
                                    insight.updateLegs(legs=orderdata["legs"])
                                insight.updateState(
                                    InsightState.EXECUTED, "Order Accepted"
                                )
                                return
                            case ITradeUpdateEvent.REJECTED:
                                insight.updateState(
                                    InsightState.REJECTED, "Order Rejected"
                                )
                                return
                            case _:
                                pass
                case InsightState.EXECUTED:
                    # We aleady know that the order has been executed because it will never be in the insights list as executed if it was not accepted by the broker
                    if insight.order_id == orderdata["order_id"]:
                        match event:
                            # case ITradeUpdateEvent.PENDING_NEW:
                            # case ITradeUpdateEvent.NEW | ITradeUpdateEvent.PENDING_NEW:
                            #     if orderdata['legs']:
                            #         insight.updateLegs(
                            #             legs=orderdata['legs'])
                            #     return

                            case ITradeUpdateEvent.REPLACED:
                                """Check if the order has been replaced and update the insight with the new order data"""
                                if orderdata["limit_price"] != insight.limit_price:
                                    insight.limit_price = orderdata["limit_price"]
                                if (
                                    insight.uses_contract_size
                                    and orderdata["qty"] != insight.contracts
                                ) or (
                                    not insight.uses_contract_size
                                    and orderdata["qty"] != insight.quantity
                                ):
                                    if insight.uses_contract_size:
                                        insight.update_contracts(orderdata["qty"])
                                    else:
                                        insight.update_quantity(orderdata["qty"])
                                if orderdata["legs"]:
                                    insight.updateLegs(legs=orderdata["legs"])
                                return

                            case ITradeUpdateEvent.FILLED:
                                if orderdata["legs"]:
                                    insight.updateLegs(legs=orderdata["legs"])
                                try:
                                    # Update the insight with the filled price
                                    insight.positionFilled(
                                        orderdata["filled_price"]
                                        if orderdata["filled_price"] != None
                                        else orderdata["limit_price"],
                                        orderdata["filled_qty"],
                                        orderdata["order_id"],
                                    )
                                    self.METRICS.positionOpened()
                                except AssertionError as e:
                                    continue
                                if insight.PARENT == None and len(insight.CHILDREN) > 0:
                                    # set the childe insight to be active
                                    for uid, childInsight in insight.CHILDREN.items():
                                        self.add_insight(childInsight)
                                    pass
                                return

                            case ITradeUpdateEvent.PARTIAL_FILLED:
                                # keep track of partial fills as some positions may be partially filled and not fully filled. in these cases we need to update the insight with the filled quantity and price
                                insight.partialFilled(orderdata["filled_qty"])
                                return

                            case ITradeUpdateEvent.CANCELED:
                                # check if we have been partially filled and remove the filled quantity from the insight
                                if (
                                    insight._partial_filled_quantity != None
                                    and self.shouldClosePartialFilledIfCancelled
                                ):
                                    insight.updateState(
                                        InsightState.FILLED,
                                        "Order Canceled, Closing Partial Filled Position",
                                    )
                                    oldQuantity = insight.quantity
                                    if insight.uses_contract_size:
                                        insight.update_contracts(
                                            insight._partial_filled_quantity
                                        )
                                    else:
                                        insight.update_quantity(
                                            insight._partial_filled_quantity
                                        )
                                    if insight.close():
                                        pass
                                    else:
                                        self.LOGGER.warning(
                                            f"Partial Filled Quantity Before Canceled: {insight._partial_filled_quantity} / {oldQuantity} - And Failed to close the position"
                                        )
                                else:
                                    insight.updateState(
                                        InsightState.CANCELED, "Order Canceled"
                                    )
                                return

                            case ITradeUpdateEvent.REJECTED:
                                insight.updateState(
                                    InsightState.REJECTED, "Order Rejected"
                                )
                                return
                            case _:
                                pass
                case InsightState.FILLED | InsightState.CLOSED:
                    # Check if the position has been closed via SL or TP
                    # if insight.state == InsightState.CANCELED and insight._partial_filled_quantity == None:
                    #     # Check if we have a partial fill and need to get the results of the partial fill that was closed
                    #     break
                    if (event == ITradeUpdateEvent.FILLED) or (
                        event == ITradeUpdateEvent.CLOSED
                    ):
                        if insight.state == InsightState.CLOSED:
                            # Insight has already been closed
                            continue
                        # check partials closes before closing the position
                        if len(insight.partial_closes) > 0:
                            for p, partialClose in enumerate(insight.partial_closes):
                                if partialClose["order_id"] == orderdata["order_id"]:
                                    if (event == ITradeUpdateEvent.FILLED) or (
                                        event == ITradeUpdateEvent.CLOSED
                                    ):
                                        # Update the insight closed price
                                        if self.MODE != IStrategyMode.BACKTEST:
                                            match (self.BROKER.NAME):
                                                case ISupportedBrokers.MT5:
                                                    insight.partial_closes[p].set_filled_price(
                                                        orderdata["stop_price "]
                                                        if orderdata["stop_price"] != None
                                                        else orderdata["filled_price"]
                                                    )
                                                case _:
                                                    insight.partial_closes[p].set_filled_price(
                                                        orderdata["filled_price"]
                                                        if orderdata["filled_price"] != None
                                                        else orderdata["limit_price"]
                                                    )
                                        else:
                                            insight.partial_closes[p].set_filled_price(
                                                orderdata["stop_price"]
                                                if orderdata["stop_price"] != None
                                                else orderdata["filled_price"]
                                            )

                                        closePnL = insight.partial_closes[p].getPL()
                                        if insight.uses_contract_size:
                                            closePnL = closePnL * insight.ASSET.get(
                                                "contract_size"
                                            )
                                        # Update the metrics with the closed PnL
                                        self.METRICS.positionClosed(closePnL)
                                        return
                        # Make sure the order is part of the insight as we dont have a clear way to tell if the closed fill is part of the strategy- to ensure that the the strategy is managed well
                        if (
                            (
                                (insight.close_order_id != None)
                                and (insight.close_order_id == orderdata["order_id"])
                            )
                            or (insight.order_id == orderdata["order_id"])
                            or (
                                insight.legs != None
                                and (
                                    (
                                        insight.takeProfitOrderLeg != None
                                        and orderdata["order_id"]
                                        == insight.takeProfitOrderLeg["order_id"]
                                    )
                                    or (
                                        insight.stopLossOrderLeg != None
                                        and orderdata["order_id"]
                                        == insight.stopLossOrderLeg["order_id"]
                                    )
                                    or (
                                        insight.trailingStopOrderLeg != None
                                        and orderdata["order_id"]
                                        == insight.trailingStopOrderLeg["order_id"]
                                    )
                                )
                            )
                        ):
                            # Update the insight closed price
                            try:
                                if (
                                    self.MODE != IStrategyMode.BACKTEST
                                    and self.broker.NAME != ISupportedBrokers.PAPER
                                ):
                                    match (self.BROKER.NAME):
                                        case ISupportedBrokers.MT5:
                                             insight.positionClosed(
                                                orderdata["stop_price"]
                                                if orderdata["stop_price"] != None
                                                else orderdata["filled_price"],
                                                orderdata["order_id"],
                                                orderdata["filled_qty"],
                                            )
                                        case _:
                                            insight.positionClosed(
                                                orderdata["filled_price"]
                                                if orderdata["filled_price"] != None
                                                else orderdata["limit_price"],
                                                orderdata["order_id"],
                                                orderdata["filled_qty"],
                                            )
                                else:
                                    insight.positionClosed(
                                        orderdata["stop_price"]
                                        if orderdata["stop_price"] != None
                                        else orderdata["filled_price"],
                                        orderdata["order_id"],
                                        orderdata["filled_qty"],
                                    )

                        
                                closePnL = insight.getPL(False) or 0
                                if insight.uses_contract_size:
                                    # TODO: might not to do this if quantity is in units of the contract size
                                    closePnL = closePnL * insight.ASSET.get(
                                        "contract_size"
                                    )

                                self.METRICS.positionClosed(closePnL)
                                return  # No need to continue
                            except AssertionError as e:
                                continue

                    continue

        # TODOL Check if the order is part of the resolution of the strategy and has a insight that is managing it.

    def _loadUniverse(self):
        """Loads the universe of the strategy."""
        assert callable(self.universe), "Universe must be a callable function"
        universeSet = set(self.universe())
        for symbol in universeSet:
            self._loadAsset(symbol)
        assert len(self.UNIVERSE) != 0, "No assets loaded into the universe"

        for asset in self.UNIVERSE.values():
            # Init all assets in the strategy
            self._init(asset)

    def _loadAsset(self, symbol: str):
        """Loads the asset into the universe of the strategy."""
        assetInfo = self.BROKER.get_ticker_info(symbol)
        if assetInfo and assetInfo["status"] == "active" and assetInfo["tradable"]:
            self.UNIVERSE[assetInfo["symbol"]] = assetInfo
            self.HISTORY[assetInfo["symbol"]] = pd.DataFrame()
            self.LOGGER.info(f'Loaded {symbol}:{assetInfo["exchange"], }  into universe')
        else:
            self.LOGGER.warning(f"Failed to load {symbol} into universe")

    def add_events(
        self, eventType: Literal["trade", "quote", "bar", "news"] = "bar", applyTA: bool = True, stored: bool = False, stored_path: str = "data", time_frame: Optional[ITimeFrame] = None, **kwargs
    ):
        """Adds bar streams to the strategy."""
        match eventType:
            case "bar":
                options: IMarketDataStream = {}

                if self.MODE == IStrategyMode.BACKTEST:
                    # Check if we should apply TA to the stream at the start of the backtest
                    if applyTA:
                        options["applyTA"] = True
                        options["TA"] = self.TaStrategy
                        self.BACKTESTING_CONFIG["preemptiveTA"] = True
                    else:
                        options["applyTA"] = False
                        self.BACKTESTING_CONFIG["preemptiveTA"] = False

                    options["start"] = self.BROKER.START_DATE
                    options["end"] = self.BROKER.END_DATE
                    options["stored"] = stored if stored else False
                    options["stored_path"] = stored_path if stored_path else "data"

                if time_frame is not None:
                    options["time_frame"] = time_frame
                    if (
                        options["time_frame"] != self.RESOLUTION
                        and not self.broker.supportedFeatures.featuredBarDataStreaming
                    ):
                        print(
                            "Feature Bar Data Streaming is not supported by the broker"
                        )
                        return
                else:
                    options["time_frame"] = self.RESOLUTION
                    options["feature"] = None

                for assetInfo in self.UNIVERSE.values():
                    assetDataStreamInfo = options.copy()
                    assetDataStreamInfo["symbol"] = assetInfo.get("symbol")
                    assetDataStreamInfo["exchange"] = assetInfo.get("exchange")
                    assetDataStreamInfo["asset_type"] = assetInfo.get("asset_type")
                    if options["time_frame"] != self.RESOLUTION:
                        assetDataStreamInfo[
                            "feature"
                        ] = f"{assetDataStreamInfo['symbol']}~{
                            assetDataStreamInfo['time_frame']}"
                        if assetDataStreamInfo["feature"] in self.HISTORY:
                            if not isinstance(
                                self.HISTORY[assetDataStreamInfo["feature"]],
                                pd.DataFrame,
                            ):
                                self.HISTORY[assetDataStreamInfo["feature"]] = (
                                    pd.DataFrame()
                                )
                        else:
                            self.HISTORY[assetDataStreamInfo["feature"]] = (
                                pd.DataFrame()
                            )

                    assetDataStreamInfo["type"] = eventType
                    self.STREAMS.append(IMarketDataStream(**assetDataStreamInfo))
            case _:
                print(f"{eventType} Event not supported")

    def add_alpha(self, alpha: BaseAlpha):
        """Adds an alpha to the strategy."""
        assert isinstance(alpha, BaseAlpha), "alpha must be of type BaseAlpha object"

        alpha.registerAlpha()

    def add_alphas(self, alphas: List[BaseAlpha]):
        """Adds a list of alphas to the strategy."""
        assert isinstance(alphas, List), "alphas must be of type List[BaseAlpha] object"
        for alpha in alphas:
            self.add_alpha(alpha)

    def add_executor(self, executor: BaseExecutor, state: InsightState = None):
        """Adds an executor to the strategy."""
        assert isinstance(
            executor, BaseExecutor
        ), "executor must be of type BaseExecutor object"
        if state is not None:
            executor._override_state(state)

        self.INSIGHT_EXECUTORS[executor.state].append(executor)

    def add_executors(self, executors: List[BaseExecutor], state: InsightState = None):
        """Adds a list of executors to the strategy."""
        assert isinstance(
            executors, List
        ), "executors must be of type List[BaseExecutor] object"
        for executor in executors:
            self.add_executor(executor, state)

    def add_ta(self, ta: List[dict]):
        """Adds a technical analysis to the strategy."""
        assert isinstance(ta, List), "ta must be of type List[dict] object"
        if len(ta) == 0:
            return

        for ind in ta:
            if ind not in self.TaStrategy.ta:
                self.TaStrategy.ta.append(ind)

    def add_insight(self, insight: Insight):
        """Adds an insight to the strategy."""
        assert isinstance(insight, Insight), "insight must be of type Insight object"

        insight.set_mode(self.BROKER, self.assets[insight.symbol], self.MODE)

        self.INSIGHTS[insight.INSIGHT_ID] = insight

    async def _on_bar(self, bar: Any, timeframe: ITimeFrame):
        """format the bar stream to the strategy."""
        if not self._RUNNING:
            return
        try:
            data: pd.DataFrame = None
            if (
                self.MODE != IStrategyMode.BACKTEST
                and self.BROKER.NAME != ISupportedBrokers.PAPER
            ) and not isinstance(bar, pd.DataFrame):
                data = self.BROKER.format_on_bar(bar)
            else:
                data = bar

            if data is None or data.empty:
                self.LOGGER.warning("Bar is None or empty in _on_bar")
                return

            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            self.ORDERS = self.BROKER.get_orders() or {}
            self.POSITIONS = self.POSITIONS or {}

            symbol, timestamp = None, None
            if not data.empty:
                # Ensure index names
                if data.index.names != ["symbol", "timestamp"]:
                    data.index.set_names(["symbol", "timestamp"], inplace=True)
                try:
                    symbol = data.index[0][0]
                    timestamp = data.index[0][1]
                except Exception as e:
                    self.LOGGER.error(f"Failed to extract symbol/timestamp from bar index: {e}")
                    return
                if symbol is None:
                    self.LOGGER.warning("Symbol is None - ignoring BaseStrategy_on_bar")
                    return
                # Feature event check
                isFeature = False
                for stream in self.STREAMS:
                    if (
                        stream["type"] == "bar"
                        and (stream["symbol"] == symbol or stream["feature"] == symbol)
                        and stream["time_frame"].value != self.resolution.value
                    ):
                        if stream["time_frame"].value == timeframe.value and stream["time_frame"].is_time_increment(timestamp):
                            isFeature = True
                            # Update the feature symbol name
                            if stream["feature"] != symbol:
                                data.rename(index={symbol: stream["feature"]}, inplace=True)
                                symbol = stream["feature"]
                            self.LOGGER.info(f"Feature Bar is part of the resolution of the strategy: {symbol} - {timestamp} - {datetime.datetime.now()}")
                            break
                if (
                    self.resolution.value == timeframe.value
                    and self.resolution.is_time_increment(timestamp)
                ) or isFeature:
                    if self.VERBOSE > 0:
                        self.LOGGER.info(f"New Bar is part of the resolution of the strategy: {symbol} - {timestamp} - {datetime.datetime.now()}")
                        start_time = timeit.default_timer()
                    # Append to history and remove duplicates
                    self.HISTORY[symbol] = pd.concat([self.HISTORY[symbol], data])
                    self.HISTORY[symbol] = self.HISTORY[symbol].loc[
                        ~self.HISTORY[symbol].index.duplicated(keep="first")
                    ]
                    
                    # Truncate history to prevent memory leaks and slow TA calculations
                    MAX_HISTORY_SIZE = self.WARM_UP + self._MAX_HISTORY_SIZE # Keep a buffer above warm up
                    if len(self.HISTORY[symbol]) > MAX_HISTORY_SIZE:
                         self.HISTORY[symbol] = self.HISTORY[symbol].iloc[-MAX_HISTORY_SIZE:]

                    if len(self.HISTORY[symbol]) < self.WARM_UP:
                        self.LOGGER.info(f"Waiting for warm up: {symbol} - {len(self.HISTORY[symbol])} / {self.WARM_UP}")
                        return
                    if (
                        not self.BACKTESTING_CONFIG.get("preemptiveTA")
                        and self.MODE == IStrategyMode.BACKTEST
                    ) or (self.MODE != IStrategyMode.BACKTEST):
                        self.HISTORY[symbol].ta.study(self.TaStrategy)
                    try:
                        if (not isFeature) or (isFeature and self.tradeOnFeatureEvents):
                            self.on_bar(symbol, data)
                            self._generateInsights(symbol)
                    except Exception as e:
                        self.LOGGER.error(f"Error in on_bar: {e}")
                    if self.VERBOSE > 0:
                        self.LOGGER.debug(f"Time taken on_bar: {symbol} {timeit.default_timer() - start_time}")
                # else: not part of resolution/feature event
        except Exception as e:
            self.LOGGER.error(f"Exception in _on_bar: {e}")
        finally:
            # If in backtest mode and shutdown is signaled, ensure barrier is released
            if self.MODE == IStrategyMode.BACKTEST and hasattr(self.BROKER, 'BACKTEST_FlOW_CONTROL_BARRIER') and self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER:
                try:
                    # self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER.wait(timeout=2)
                     await asyncio.to_thread(self.BROKER.BACKTEST_FlOW_CONTROL_BARRIER.wait)
                except Exception as barrier_e:
                    self.LOGGER.warning(f"Barrier wait failed or timed out: {barrier_e}")
        return
        

    def submit_order(self, insight: Insight):
        """Submits an order to the broker."""
        assert isinstance(insight, Insight), "insight must be of type Insight object"
        try:
            if self.INSIGHTS.get(insight.INSIGHT_ID) == None:
                # Make sure the insight is added to the strategy
                self.add_insight(insight)

            insight.submit()

            order = self.BROKER.execute_insight_order(
                insight, self.assets[insight.symbol]
            )
            return order
        except BaseException as e:
            # print('Error in submit_order:', e)
            raise e

    def close_position(self, symbol, qty=None, percent=None):
        """Cancels an order to the broker."""
        return self.BROKER.close_position(symbol, qty, percent)

    @property
    def account(self) -> Optional[IAccount]:
        """Returns the account of the strategy."""

        return self.ACCOUNT

    @property
    def positions(self) -> dict[str, IPosition]:
        """Returns the positions of the strategy."""
        return self.POSITIONS

    @property
    def orders(self) -> Optional[dict[str, IOrder]]:
        """Returns the orders of the strategy."""
        return self.ORDERS

    @property
    def history(self) -> dict[str, pd.DataFrame]:
        """Returns the candle history of the strategy."""
        return self.HISTORY

    @property
    def insights(self) -> dict[UUID, Insight]:
        """Returns the insights of the strategy."""
        return self.INSIGHTS

    @property
    def state(self) -> dict:
        """Returns the state of the strategy."""
        return self.VARIABLES

    @state.setter
    def state(self, state: AttributeDict):
        """Sets the state of the strategy."""
        self.VARIABLES = state

    @property
    def broker(self) -> BaseBroker:
        """Returns the broker used by the strategy."""
        return self.BROKER

    @property
    def assets(self) -> dict[str, IAsset]:
        """Returns the universe of the strategy."""
        return self.UNIVERSE

    @property
    def metrics(self) -> IStrategyMetrics:
        """Returns the metrics of the strategy."""
        return self.METRICS

    @property
    def resolution(self) -> ITimeFrame:
        """Returns the resolution of the strategy."""
        return self.RESOLUTION

    @property
    def tools(self) -> ITradingTools:
        """Returns the tools of the strategy."""
        return self.TOOLS

    @property
    def streams(self) -> List[IMarketDataStream]:
        """Returns the streams of the strategy."""
        return self.STREAMS

    @property
    def warm_up(self) -> int:
        """Returns the warm up period of the strategy."""
        return self.WARM_UP

    @warm_up.setter
    def warm_up(self, warm_up: int):
        """Sets the warm up period of the strategy."""
        if warm_up < 0:
            raise ValueError("Warm up period must be greater than 0")
        if warm_up <= self.WARM_UP:
            # print('Warm up period cannot be reduced')
            return
        self.WARM_UP = warm_up

    @property
    def current_datetime(self) -> datetime:
        """Returns the current time of the strategy."""
        return self.BROKER.get_current_time.replace(tzinfo=datetime.UTC)
    
    @property
    def mode(self) -> IStrategyMode:
        """Returns the mode of the strategy."""
        return self.MODE
    
# -------------------- utilities --------------------
    def create_task(self, coro: Awaitable, name: Optional[str] = None) -> None:
        """Create and track a background task on the running loop.

        This helper is useful for launching tasks outside TaskGroup contexts.
        Tasks created here are stored in self._tasks and will be cancelled on teardown.
        """
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro, name=name)
        if name:
            self._tasks[name] = task
        else:
            self._tasks[f"task-{id(task)}"] = task


    async def cancel_tracked_tasks(self) -> None:
        """Cancel tasks created with create_task()."""
        if not self._tasks:
            return
        self.LOGGER.info(f"Cancelling %d tracked tasks {len(self._tasks)}")
        for name, t in list(self._tasks.items()):
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _shutdown(self):
        print("Shutting down streams...")

        # Broker or strategy cleanup
        try:
            await self.run_teardown()
        except Exception:
            self.LOGGER.exception("Error in run_teardown")
        self._RUNNING = False