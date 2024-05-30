import abc
import asyncio
from threading import Thread
from typing import Any, List, override, Union, Literal
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time
import datetime
import nest_asyncio
import timeit
# from numba.experimental import jitclass


from ..broker.base_broker import BaseBroker
from ..utils.interfaces import Asset, IAccount, IPosition, IOrder, IMarketDataStream
from ..utils.insight import Insight, InsightState
from ..utils.timeframe import TimeFrame, TimeFrameUnit
from ..utils.types import AttributeDict
from ..utils.tools import TradingTools


class BaseStrategy(abc.ABC):
    BROKER: BaseBroker
    ACCOUNT: IAccount = {}
    POSITIONS: dict[str, IPosition] = {}
    ORDERS: List[IOrder] = []
    HISTORY: pd.DataFrame = pd.DataFrame(
        columns=['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume'])
    INSIGHTS: dict[str, Insight] = {}
    UNIVERSE: dict[str, Asset] = {}
    RESOLUTION = TimeFrame(5, TimeFrameUnit.Minute)
    STREAMS: [IMarketDataStream] = []
    VARIABLES: AttributeDict

    TOOLS: TradingTools = None
    VERBOSE: int = 0

    @abc.abstractmethod
    def __init__(self, broker: BaseBroker, variables: AttributeDict = AttributeDict({}), resolution: TimeFrame = TimeFrame(1, TimeFrameUnit.Minute), verbose: int = 0) -> None:
        """Abstract class for strategy implementations."""
        self.VARIABLES = variables
        self.BROKER = broker
        self.TOOLS = TradingTools(self)
        self.VERBOSE = verbose
        assert TimeFrame.validate_timeframe(
            resolution.amount, resolution.unit), 'Resolution must be a valid timeframe'
        self.RESOLUTION = resolution
        # 4% of account per trade
        state = self.state
        # state['execution_risk'] = 0.01
        # 2:1 Reward to Risk Ratio minimum
        # state['RewardRiskRatio'] = 2.0
        self._loadUniverse()
        for asset in self.UNIVERSE.values():
            self.init(asset)

    @override
    @abc.abstractmethod
    def init(self, asset: Asset):
        """ Initialize the strategy. This method is called once before the start of the strategy. """
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

        if self.BROKER.NAME == 'AlpacaBroker':
            # Exchange specific setup
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="OlympusTraderStream") as pool:
                tradeStream = loop.run_in_executor(
                    pool, self.BROKER.startTradeStream, self._on_trade_update)
                marketDataSream = loop.run_in_executor(
                    pool, self.BROKER.streamMarketData, self._on_bar, self.STREAMS)
                insighStream = asyncio.run(self._insightListener())
                # insighStream = loop.run_in_executor( pool, self._insightListener)
            loop.run_forever()
           
            # with ThreadPoolExecutor(max_workers=3, thread_name_prefix="eventStream") as pool:

                # marketDataSream = asyncio.create_task(self.BROKER.streamMarketData(self._on_bar, self.STREAMS), name='marketDataStream')
                # self.BROKER.streamMarketData(self._on_bar, self.STREAMS)

                # loop.run_forever()
        except KeyboardInterrupt:
            print("Interrupted execution by user")
        except Exception as e:
            print(f'Exception from websocket connection: {e}')
        finally:
            self.teardown()
            loop.close()
            pool.shutdown(wait=False)
            exit(0)


    async def _insightListener(self):
        """ Listen to the insights and manage the orders. """
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
            await asyncio.sleep(1)
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
                            if event == 'fill':
                                # Update the insight with the filled price
                                self.INSIGHTS[orderdata['asset']['symbol']][i].positionFilled(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['qty'])
                                break  # No need to continue
                    case InsightState.FILLED | InsightState.CLOSED:
                        # Check if the position has been closed via SL or TP
                        if insight.symbol == orderdata['asset']['symbol']:
                            # Make sure the order is part of the insight as we dont have a clear way to tell if the closed fill is part of the strategy- to ensure that the the strategy is managed
                            if (event == 'fill') and ((orderdata['qty'] == insight.quantity and orderdata['side'] != insight.side) or (insight.close_order_id != None and insight.close_order_id == orderdata['order_id'])):
                                # Update the insight closed price
                                self.INSIGHTS[orderdata['asset']['symbol']][i].positionClosed(
                                    orderdata['filled_price'] if orderdata['filled_price'] != None else orderdata['limit_price'], orderdata['order_id'])
                                break  # No need to continue
        else: 
            # 'Order not in universe'
            pass              
        # TODOL Check if the order is part of the resolution of the strategy and has a insight that is managing it.

    def _loadUniverse(self):
        """ Loads the universe of the strategy."""
        assert callable(self.universe), 'Universe must be a callable function'
        universeSet = set(self.universe())
        for symbol in universeSet:
            self._loadAsset(symbol)

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

    async def _on_bar(self, bar: Any):
        """ format the bar stream to the strategy. """
        try:
            # set_index(['symbol', 'timestamp']
            if bar == None:
                print('Bar is None')
                return
            data = self.BROKER.format_on_bar(bar)

            self.ACCOUNT = self.BROKER.get_account()
            self.POSITIONS = self.BROKER.get_positions()
            self.ORDERS = self.BROKER.get_orders()
            if self.ORDERS == None:
                self.ORDERS = []
            if self.POSITIONS == None:
                self.POSITIONS = {}

            if not data.empty:
                symbol = data.index[0][0]
                timestamp = data.index[0][1]
                self.HISTORY = pd.concat([self.HISTORY, data])
                # Check if the bar is part of the resolution of the strategy
                if self.resolution.is_time_increment(timestamp):
                    # print('New Bar is part of the resolution of the strategy', data)
                    if self.VERBOSE > 0:
                        print(f'New Bar is part of the resolution of the strategy: {
                              symbol} - {timestamp} - {datetime.datetime.utcnow()}')
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
            order = self.BROKER.manage_insight_order(
                insight, self.assets[insight.symbol])
            return order
        except BaseException as e:
            # print('Error in submit_order:', e)
            raise e

    def close_position(self, symbol, qty=None, percent=None):
        """ Cancels an order to the broker."""
        return self.BROKER.close_position(symbol, qty, percent)

    @property
    def account(self) -> IAccount:
        """ Returns the account of the strategy."""
        return self.ACCOUNT

    @property
    def positions(self) -> dict[str, IPosition]:
        """ Returns the positions of the strategy."""
        return self.POSITIONS

    @property
    def orders(self) -> List[IOrder]:
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
    def resolution(self) -> str:
        """ Returns the resolution of the strategy."""
        return self.RESOLUTION

    @property
    def tools(self) -> str:
        """ Returns the tools of the strategy."""
        return self.TOOLS

    @property
    def streams(self) -> dict:
        """ Returns the streams of the strategy."""
        return self.STREAMS
