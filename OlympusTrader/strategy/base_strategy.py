import abc
import asyncio
from threading import Thread
from typing import Any, List, override, Union
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time
import nest_asyncio


from ..broker.base_broker import BaseBroker
from ..utils.interfaces import Asset, IAccount, IPosition, IOrder
from ..utils.insight import Insight
from ..utils.timeframe import TimeFrame, TimeFrameUnit
from ..utils.types import AttributeDict


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
    STREAMS = {
        'stockTickers': set(),
        'cryptoTickers': set(),
        'bars': [],
        'quotes': [],
        'trades': [],
        'news': []
    }
    VARIABLES: AttributeDict

    @abc.abstractmethod
    def __init__(self, broker: BaseBroker, variables: AttributeDict = AttributeDict({}), resolution: TimeFrame = TimeFrame(5, TimeFrameUnit.Minute)) -> None:
        """Abstract class for strategy implementations."""
        self.VARIABLES = variables
        self.BROKER = broker
        assert TimeFrame.validate_timeframe(
            resolution.amount, resolution.unit), 'Resolution must be a valid timeframe'
        self.RESOLUTION = resolution
        self.__loadUniverse()
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
    def teardown(self):
        """ Called once at the end of the strategy. """
        print('Teardown Function? -> def teardown(self):')
        self.BROKER.close_all_positions()

    def run(self):
        """ starts the strategy. """
        nest_asyncio.apply()
        if self.BROKER.name == 'AlpacaBroker':
            self.runAlpaca()

    def runAlpaca(self):
        """ starts the event streams with strategy. """
        pool = ThreadPoolExecutor(max_workers=14)
        loop = asyncio.new_event_loop()

        try:
            tradeStream = loop.run_in_executor(
                pool, self.BROKER.startTradeStream, self.__on_trade_update)

            if (len(self.STREAMS['stockTickers']) > 0):
                stockStream = loop.run_in_executor(
                    pool, self.BROKER.startStream, 'stock', 'bars')

            if (len(self.STREAMS['cryptoTickers']) > 0):
                cryptoStream = loop.run_in_executor(
                    pool, self.BROKER.startStream, 'crypto', 'bars')

            loop.run_forever()

        except KeyboardInterrupt:
            print("Interrupted execution by user")
            if (len(self.STREAMS['stockTickers']) > 0):
                stockStream.cancel()
                # self.BROKER.closeStream('stock', 'bars')
                asyncio.run(self.BROKER.closeStream('stock', 'bars'))
            if (len(self.STREAMS['cryptoTickers']) > 0):
                cryptoStream.cancel()
                # self.BROKER.closeStream('crypto', 'bars')
                asyncio.run(self.BROKER.closeStream('crypto', 'bars'))

            # asyncio.run(self.BROKER.closeTradeStream())


        except Exception as e:
            print(f'Exception from websocket connection: {e}')
        finally:

            self.teardown()
            tradeStream.cancel()
            asyncio.run(self.BROKER.closeTradeStream())
            # self.BROKER.closeTradeStream()
            # print("Closing websocket connection... ")
            # if (len(self.STREAMS['stockTickers']) > 0):
            #     asyncio.run(self.BROKER.closeStream('stock', 'bars'))
            # if (len(self.STREAMS['cryptoTickers']) > 0):
            #     asyncio.run(self.BROKER.closeStream('crypto', 'bars'))

            loop.stop()
            exit(0)

    async def __on_trade_update(self, trade):
        """ format the trade stream to the strategy. """
        orderdata, event = self.BROKER.format_on_trade_update(trade)
        if not orderdata:
            return
        self.ORDERS.append(orderdata)
        print(f"Order: {event:<16} {orderdata['created_at']}: {orderdata['asset']['symbol']:^6}:{orderdata['qty']:^8}: {orderdata['type']} / {orderdata['order_class']} : {orderdata['side']} @ {orderdata['limit_price'] if orderdata['limit_price'] != None else orderdata['filled_price']} " )

    def __loadUniverse(self):
        """ Loads the universe of the strategy."""
        assert callable(self.universe), 'Universe must be a callable function'
        universeSet = self.universe()
        for symbol in universeSet:
            symbol = symbol.upper()
            assetInfo = self.BROKER.get_ticker_info(symbol)
            if assetInfo:
                self.UNIVERSE[symbol] = assetInfo
                self.INSIGHTS[symbol] = []
                print(f'Loaded {symbol}:{assetInfo["exchange"], }  into universe')

    # @abc.abstractmethod
    def addBar_events(self, asset: Asset):
        """ Adds bar streams to the strategy."""
        if (asset['asset_type'] == 'stock'):
            self.STREAMS['stockTickers'].add(asset['symbol'])
        elif (asset['asset_type'] == 'crypto'):
            self.STREAMS['cryptoTickers'].add(asset['symbol'])
        else:
            assert False, 'AddBar Event: Asset type must be of type stock or crypto'

        self.__addBar_event(asset['symbol'], asset['asset_type'])
    # @abc.abstractmethod

    def __addBar_event(self, symbol: str, assetType: str):
        """ build the bar stream to the strategy."""
        if self.BROKER.name == 'AlpacaBroker':
            if assetType == 'stock':
                self.STREAMS['bars'].append(self.BROKER.streamBar(
                    self.__on_bar, symbol, 'stock'))
            elif assetType == 'crypto':
                self.STREAMS['bars'].append(self.BROKER.streamBar(
                    self.__on_bar, symbol, 'crypto'))

    async def __on_bar(self, bar: Any):
        """ format the bar stream to the strategy. """
        try:
            # set_index(['symbol', 'timestamp']
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
                    self.on_bar(symbol, data)
                else:
                    # print('Bar is not part of the resolution of the strategy', data)
                    pass
                    # Will need to take the the 1 min bar and convert it to the resolution of the strategy

            else:
                print('Data is empty - BROKER.format_on_bar(bar) not working')
        except Exception as e:
            print('Error in __on_bar_format in base Strategy:', e)
            pass

    def submit_order(self, insight: Insight):
        """ Submits an order to the broker."""
        assert isinstance(insight, Insight), 'insight must be of type Insight object'
        order = self.BROKER.manage_insight_order(insight, self.assets[insight.symbol])
        return order
    
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
    def streams(self) -> dict:
        """ Returns the streams of the strategy."""
        return self.STREAMS
