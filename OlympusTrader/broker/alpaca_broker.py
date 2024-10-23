import datetime
from typing import Awaitable, Callable, List, Literal, Union
from concurrent.futures import ThreadPoolExecutor
import asyncio
import os
import pandas as pd
import json
import numpy as np

import alpaca
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.live import StockDataStream, CryptoDataStream
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest, StockLatestQuoteRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, CryptoFeed
from alpaca.common.enums import BaseURL
from alpaca.trading.models import Position, Order, TradeUpdate
from alpaca.data.models import Bar, Quote
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopLimitOrderRequest, ClosePositionRequest, OrderSide, OrderType, OrderClass, TimeInForce, TakeProfitRequest, StopLossRequest
from alpaca.trading.stream import TradingStream
# from alpaca.trading.enums import AssetClass

from .base_broker import BaseBroker
from .interfaces import ISupportedBrokerFeatures, ISupportedBrokers, IAsset, IAccount, IOrder, IPosition, IOrderSide, IOrderType, ITradeUpdateEvent, IQuote, IOrderLegs, IOrderLeg
from ..utils.timeframe import ITimeFrame as tf
from ..insight.insight import Insight


class AlpacaBroker(BaseBroker):
    trading_client: TradingClient = None
    trade_stream_client: TradingStream = None
    stock_client: StockHistoricalDataClient = None
    stock_stream_client: StockDataStream = None
    crypto_client: CryptoHistoricalDataClient = None
    crypto_stream_client: CryptoDataStream = None

    def __init__(self, paper: bool, feed: DataFeed = DataFeed.IEX):
        super().__init__(ISupportedBrokers.ALPACA, paper, feed)

        assert os.getenv('ALPACA_API_KEY'), 'ALPACA_API_KEY not found'
        assert os.getenv('ALPACA_SECRET_KEY'), 'ALPACA_SECRET_KEY not found'

        self.DataFeed = DataFeed.IEX if self.PAPER else DataFeed.SIP

        self.trading_stream_client = TradingStream(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'), paper=paper)
        self.trading_client = TradingClient(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'), paper=paper)
        self.stock_client = StockHistoricalDataClient(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'))
        self.crypto_client = CryptoHistoricalDataClient(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'))
        self.stock_stream_client = StockDataStream(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'))
        self.crypto_stream_client = CryptoDataStream(
            os.getenv('ALPACA_API_KEY'),  os.getenv('ALPACA_SECRET_KEY'), feed=CryptoFeed.US, url_override=BaseURL.MARKET_DATA_STREAM + "/v1beta3/crypto/" + CryptoFeed.US)

        self.supportedFeatures = ISupportedBrokerFeatures(
            barDataStreaming=True, trailingStop=False, maxOrderValue=200_000.00)

    def get_history(self, asset: IAsset, start: datetime, end: datetime, resolution: tf):
        # Convert to TimeFrame from OlympusTrader from alpaca
        super().get_history(asset, start, end, resolution)

        timeframe = TimeFrame(resolution.amount, resolution.unit)
        data = None
        try:
            if (asset['asset_type'] == 'stock'):
                # assert isinstance(
                #     feed, DataFeed), 'DataFeed must be of type DataFeed'
                data = self.stock_client.get_stock_bars(
                    StockBarsRequest(
                        symbol_or_symbols=asset['symbol'],
                        timeframe=timeframe,
                        start=start,
                        end=end,
                        feed=self.DataFeed
                    )).df
            elif (asset['asset_type'] == 'crypto'):
                # assert isinstance(
                #     feed, CryptoFeed), 'DataFeed must be of type CryptoFeed'
                data = self.crypto_client.get_crypto_bars(CryptoBarsRequest(
                    symbol_or_symbols=asset['symbol'],
                    timeframe=timeframe,
                    start=start,
                    end=end
                )).df
            else:
                assert False, 'Get History: IAsset type must be of type stock or crypto'

            if data.empty:
                return None
            # format Data Frame open, high, low, close, volume
            # 'timestamp'
            data = data[['open', 'high', 'low', 'close', 'volume']]
            # print(data)
            return self.format_on_bar(data)
        except:
            return None

    def get_ticker_info(self, symbol):
        try:
            if symbol in self.TICKER_INFO:
                return self.TICKER_INFO[symbol]

            tickerInfo = self.trading_client.get_asset(symbol)

            assert tickerInfo, f'Asset {symbol} not found'

            tickerAsset: IAsset = IAsset(
                id=tickerInfo.id,
                name=tickerInfo.name,
                asset_type='stock' if tickerInfo.asset_class == 'us_equity' else 'crypto',
                exchange=tickerInfo.exchange,
                symbol=tickerInfo.symbol,
                status=tickerInfo.status,
                tradable=tickerInfo.tradable,
                marginable=tickerInfo.marginable,
                shortable=tickerInfo.shortable,
                fractionable=tickerInfo.fractionable,
                min_order_size=tickerInfo.min_order_size if tickerInfo.min_order_size else 0.1,
                min_price_increment=tickerInfo.price_increment if tickerInfo.price_increment else 0.01,
            )
            self.TICKER_INFO[symbol] = tickerAsset
            return tickerAsset
        except alpaca.common.exceptions.APIError as e:
            print("Error: No asset for", symbol)
            return None

    def get_account(self):
        res = self.trading_client.get_account()
        res.non_marginable_buying_power
        account: IAccount = IAccount(account_id=str(res.id), equity=float(res.equity), cash=float(res.cash), currency=res.currency,
                                     buying_power=float(res.buying_power), leverage=float(res.multiplier), shorting_enabled=res.shorting_enabled)
        return account

    def get_position(self, symbol):
        res = self.trading_client.get_position(symbol)
        position: IPosition = self.format_position(position)
        return position

    def get_positions(self):
        res: List[Position] = self.trading_client.get_all_positions()

        positions: dict[str, IPosition] = {}
        for position in res:
            positions[position.symbol] = self.format_position(position)
        return positions

    def format_position(self, position: Position) -> IPosition:
        return IPosition(
            asset=self.get_ticker_info(position.symbol),
            avg_entry_price=float(position.avg_entry_price),
            qty=float(position.qty),
            side=position.side.value,
            market_value=float(position.market_value),
            cost_basis=float(position.cost_basis),
            current_price=float(position.current_price),
            unrealized_pl=float(position.unrealized_pl)
        )

    def get_orders(self):
        res = self.trading_client.get_orders()
        orders: dict[str, IOrder] = {}
        if not res:
            return None
        for order in res:
            orders[order.id] = self.format_order(order)
        return orders

    def get_order(self, order_id):
        return self.format_order(self.trading_client.get_order_by_id(order_id))

    def format_order(self, order: Order) -> IOrder:
        side = None
        match order.side:
            case OrderSide.BUY:
                side = IOrderSide.BUY
            case OrderSide.SELL:
                side = IOrderSide.SELL
            case _:
                side = "unknown"
        #  TODO: add support for order legs
        legs = IOrderLegs()
        if order.legs:
            for leg in order.legs:
                if leg.order_type == OrderType.LIMIT:
                    legs['take_profit'] = IOrderLeg(
                        order_id=leg.id,
                        limit_price=float(leg.limit_price),
                        filled_price=float(
                            leg.filled_avg_price) if leg.filled_avg_price else None,
                        type=IOrderType.LIMIT,
                        status=leg.status.value,
                        order_class=leg.order_class.value,
                        created_at=leg.created_at,
                        updated_at=leg.updated_at,
                        submitted_at=leg.submitted_at,
                        filled_at=leg.filled_at
                    )
                elif leg.order_type == OrderType.STOP:
                    legs['stop_loss'] = IOrderLeg(
                        order_id=leg.id,
                        limit_price=float(leg.stop_price),
                        filled_price=float(
                            leg.filled_avg_price) if leg.filled_avg_price else None,
                        type=IOrderType.STOP,
                        status=leg.status.value,
                        order_class=leg.order_class.value,
                        created_at=leg.created_at,
                        updated_at=leg.updated_at,
                        submitted_at=leg.submitted_at,
                        filled_at=leg.filled_at
                    )
                else:
                    continue

        order = IOrder(
            order_id=order.id,
            asset=self.get_ticker_info(order.symbol),
            filled_price=float(
                order.filled_avg_price) if order.filled_avg_price else None,
            limit_price=float(
                order.limit_price) if order.limit_price else None,
            stop_price=float(order.stop_price) if order.stop_price else None,
            qty=float(order.qty),
            filled_qty=float(order.filled_qty),
            side=side,
            type=order.type.value,
            order_class=order.order_class.value,
            time_in_force=order.time_in_force.value,
            status=order.status.value,
            created_at=order.created_at,
            updated_at=order.updated_at,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            legs=legs
        )

        return order

    def get_latest_quote(self, asset: IAsset):
        if asset['asset_type'] == 'crypto':
            quote = self.crypto_client.get_crypto_latest_quote(
                CryptoLatestQuoteRequest(symbol_or_symbols=asset['symbol']))
        elif asset['asset_type'] == 'stock':
            quote = self.stock_client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=asset['symbol'], feed=self.DataFeed))
        return self.format_on_quote(quote[asset['symbol']])

    def execute_insight_order(self, insight: Insight, asset: IAsset) -> IOrder | None:
        # TODO: manage insight order by planing entry and exit orders for a given insight
        # https://alpaca.markets/docs/trading/orders/#bracket-orders
        super().execute_insight_order(insight, asset)
        req = None
        orderRequest = {
            "symbol": insight.symbol,
            "qty": insight.quantity,
            "side": OrderSide.BUY if insight.side == IOrderSide.BUY else OrderSide.SELL,
            "time_in_force": TimeInForce.GTC,
            # OrderClass.BRACKET if insight.TP and insight.SL else OrderClass.SIMPLE,
            "order_class": OrderClass.SIMPLE
            # "take_profit": None if insight.TP == None else TakeProfitRequest(
            #     limit_price=insight.TP[-1]
            # ),
            # "stop_loss": None if insight.SL == None else StopLossRequest(
            #     stop_price=insight.SL,
            #     # stop_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
            # )
        }
        if insight.TP and insight.SL:
            orderRequest["order_class"] = OrderClass.BRACKET
            orderRequest["take_profit"] = TakeProfitRequest(
                limit_price=insight.TP[-1]
            )
            orderRequest["stop_loss"] = StopLossRequest(
                stop_price=insight.SL,
                # stop_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
            )
        elif insight.TP:
            orderRequest["order_class"] = OrderClass.OTO
            orderRequest["take_profit"] = TakeProfitRequest(
                limit_price=insight.TP[-1]
            )
        elif insight.SL:
            orderRequest["order_class"] = OrderClass.OTO
            orderRequest["stop_loss"] = StopLossRequest(
                stop_price=insight.SL,
                # stop_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
            )
        if insight.limit_price:
            orderRequest["limit_price"] = insight.limit_price

        if asset['asset_type'] == 'crypto':
            # "crypto orders not allowed for advanced order_class: otoco or OTO"}
            orderRequest["order_class"] = OrderClass.SIMPLE

        try:
            match insight.type:
                case IOrderType.MARKET:
                    req = MarketOrderRequest(**orderRequest)
                case IOrderType.LIMIT:
                    req = LimitOrderRequest(**orderRequest)
                case IOrderType.STOP:
                    req = StopLimitOrderRequest(**orderRequest)
                case _:
                    print(
                        f"ALPACA: Order Type not supported {insight.type} ")
                    return
            if req:
                order = self.trading_client.submit_order(req)
                return self.format_order(order)

        except alpaca.common.exceptions.APIError as e:
            # print ("ALPACA: Error submitting order", e)
            if e.code == 40310000:
                # '{"available":"0.119784","balance":"0.119784","code":40310000,"message":"insufficient balance for BTC (requested: 0.12, available: 0.119784)","symbol":"USD"}'
                error = BaseException({
                    "code": "insufficient_balance",
                    "data": json.loads(e.args[0])
                })
                # TODO: make a strutured error


                raise error
            raise e

        return None

    def close_all_positions(self):
        print("Closing all positions and orders")
        closeOrders = self.trading_client.close_all_positions(
            cancel_orders=True)
        return closeOrders

    def close_position(self, symbol, qty=None, percent=None):
        try:
            closePosReq = ClosePositionRequest(
                qty=str(qty)) if qty else ClosePositionRequest(percentage=str(percent))
            order = self.trading_client.close_position(symbol, closePosReq)
            # print("Closed position", order)
            return self.format_order(order)
        except alpaca.common.exceptions.APIError as e:
            print("Error closing position", e)
            raise e

    def cancel_order(self, order_id):
        try:
            self.trading_client.cancel_order_by_id(order_id)
            return order_id
        except alpaca.common.exceptions.APIError as e:
            if e.code == 42210000:
                error = BaseException({
                    "code": "already_filled",
                    "data": e
                })
                raise error
            raise e

    def startTradeStream(self, callback: Awaitable):
        super().startTradeStream(callback)
        self.trading_stream_client.subscribe_trade_updates(callback)
        self.trading_stream_client.run()

    async def closeTradeStream(self):
        self.trading_stream_client.stop()
        await self.trading_stream_client.close()

    def streamMarketData(self, callback: Awaitable, assetStreams):
        super().streamMarketData(callback, assetStreams)
        StockStreamCount = 0
        CryptoStreamCount = 0
        barStreamCount = len(
            [asset for asset in assetStreams if asset['type'] == 'bar'])

        pool = ThreadPoolExecutor(max_workers=(
            barStreamCount), thread_name_prefix="MarketDataStream")
        loop = asyncio.new_event_loop()

        for assetStream in assetStreams:

            if assetStream['type'] == 'bar':
                async def alpaca_stream_callback(data):
                    """ Alpaca only generates one bar at a time no matter the timeframe so we need to send the to each feature
                        base_strategy should handle the rest
                    """
                    barData = self.format_on_bar(data)
                    timestamp = barData.index[0][1]
                    # TODO: WE may be able to skip this if python still hass access to the local scope variables assetStream during the loop. 
                    # We may be able to use the assetStream variable directly in the callback instead of looping over it as we are passing by ref to the alpace callback.
                    for asset in assetStreams:
                        if asset['symbol'] == assetStream['symbol'] and asset['time_frame'].is_time_increment(timestamp):
                            # FIXME:Since this is one min candle we need to get the agreg of all of the previous candles if TF is greater than 1 min
                            await callback(barData, timeframe=asset['time_frame'])

                if assetStream.get('feature') != None:
                    # We dont want to add multiple streams for the same asset
                    
                    continue
                if assetStream['asset_type'] == 'stock':
                    StockStreamCount += 1
                    self.stock_stream_client.subscribe_bars(
                        alpaca_stream_callback, assetStream.get('symbol'))
                elif assetStream['asset_type'] == 'crypto':
                    CryptoStreamCount += 1
                    self.crypto_stream_client.subscribe_bars(
                        alpaca_stream_callback, assetStream.get('symbol'))
            else:
                raise NotImplementedError(
                    f"Stream type {assetStream['type']} not supported")
            # TODO: add support for quotes

        if StockStreamCount:
            loop.run_in_executor(pool, self.stock_stream_client.run)
            # self.stock_stream_client.run()
            print(f"Stock Stream Running: {StockStreamCount} streams")
        if CryptoStreamCount:
            loop.run_in_executor(pool, self.crypto_stream_client.run)
            # self.crypto_stream_client.run()
            print(f"Crypto Stream Running: {CryptoStreamCount} streams")
        # TODO: add support for qutoes

    # def streamBar(self, callback: Awaitable, symbol: str, AssetType: Literal['stock', 'crypto'] = 'stock'):
    #     if AssetType == 'stock':
    #         return self.stock_stream_client.subscribe_bars(callback, symbol)
    #     elif AssetType == 'crypto':
    #         return self.crypto_stream_client.subscribe_bars(callback, symbol)

    # def startStream(self, assetType, type):
    #     if assetType == 'stock':
    #         self.stock_stream_client.run()
    #     elif assetType == 'crypto':
    #         self.crypto_stream_client.run()

    async def closeStream(self, assetStreams):
        # TODO: unsubscribe from streams type close stream should be called when strategy is stopped - close WSS connection
        closeStockBarStream = False
        closeCryptoBarStream = False
        for assetStream in assetStreams:
            if assetStream['type'] == 'bar':
                assetType = assetStream['asset_type']
                symbol = assetStream['symbol']
                if assetType == 'stock':
                    self.stock_stream_client.unsubscribe_bars(symbol)
                    if not closeStockBarStream:
                        closeStockBarStream = True
                elif assetType == 'crypto':
                    self.crypto_stream_client.unsubscribe_bars(symbol)
                    if not closeCryptoBarStream:
                        closeCryptoBarStream = True

        if closeStockBarStream:
            self.stock_stream_client.close()
        if closeCryptoBarStream:
            self.crypto_stream_client.stop()

    def format_on_trade_update(self, trade: TradeUpdate):
        event: ITradeUpdateEvent = None
        match trade.event:
            case "fill":
                event = ITradeUpdateEvent.FILLED
            case "partial_fill":
                event = ITradeUpdateEvent.PARTIAL_FILLED
            case "canceled":
                event = ITradeUpdateEvent.CANCELED
            case "rejected":
                event = ITradeUpdateEvent.REJECTED
            case "pending_new":
                event = ITradeUpdateEvent.PENDING_NEW
            case "new":
                event = ITradeUpdateEvent.NEW
            case "expired":
                event = ITradeUpdateEvent.EXPIRED
            case "replaced":
                event = ITradeUpdateEvent.REPLACED
            case "accepted":
                event = ITradeUpdateEvent.ACCEPTED
            case _:
                event = trade.event
        return self.format_order(trade.order), event

    def format_on_bar(self, bar: Union[Bar, pd.DataFrame, pd.Series]):
        if isinstance(bar, pd.DataFrame):
            return bar
        elif isinstance(bar, Bar):
            index = pd.MultiIndex.from_product(
                [[bar.symbol], [bar.timestamp]], names=['symbol', 'date'])
            data = pd.DataFrame(data={
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
            }, index=index, columns=['open', 'high', 'low', 'close', 'volume'])
        # data.set_index(['symbol', )], inplace=True)
            return data
        return None

    def format_on_quote(self, quote: Quote):
        data = IQuote(
            symbol=quote.symbol,
            ask=quote.ask_price,
            ask_size=quote.ask_size,
            bid=quote.bid_price,
            bid_size=quote.bid_size,
            volume=(quote.bid_size + quote.ask_size),
            timestamp=quote.timestamp
        )
        return data
