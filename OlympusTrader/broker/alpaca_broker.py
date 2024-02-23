import datetime
from typing import Awaitable, Callable, List, Literal, Union
import alpaca
from .base_broker import BaseBroker
from ..utils.interfaces import Asset, IAccount, IOrder, IPosition
from ..utils.timeframe import TimeFrame as tf
from ..utils.insight import Insight

import os
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.live import StockDataStream, CryptoDataStream
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, CryptoFeed
from alpaca.common.enums import BaseURL
from alpaca.trading.models import Position, Order, TradeUpdate
from alpaca.data.models import Bar
from alpaca.trading.requests import OrderRequest, MarketOrderRequest, LimitOrderRequest, ClosePositionRequest, OrderSide, OrderType, OrderClass, TimeInForce, TakeProfitRequest, StopLossRequest
from alpaca.trading.stream import TradingStream
# from alpaca.trading.enums import AssetClass


class AlpacaBroker(BaseBroker):
    trading_client: TradingClient = None
    trade_stream_client: TradingStream = None
    stock_client: StockHistoricalDataClient = None
    stock_stream_client: StockDataStream = None
    crypto_client: CryptoHistoricalDataClient = None
    crypto_stream_client: CryptoDataStream = None

    def __init__(self, paper: bool, feed: DataFeed = DataFeed.IEX, name='AlpacaBroker'):
        super().__init__(paper, feed, name)
        assert os.getenv('ALPACA_API_KEY'), 'ALPACA_API_KEY not found'
        assert os.getenv('ALPACA_SECRET_KEY'), 'ALPACA_SECRET_KEY not found'

        self.DataFeed = DataFeed.IEX if paper else DataFeed.SIP

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

    def get_history(self, asset: Asset, start: datetime, end: datetime, resolution: tf):
        # Convert to TimeFrame from OlympusTrader from alpaca
        super().get_history(asset, start, end, resolution)

        timeframe = TimeFrame(resolution.amount, resolution.unit)
        data = None
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
            assert False, 'Get History: Asset type must be of type stock or crypto'
        # format Data Frame open, high, low, close, volume
        data = data[['open', 'high', 'low', 'close', 'volume']]  # 'timestamp'
        # print(data)
        return data

    def get_ticker_info(self, symbol):
        try:
            tickerInfo = self.trading_client.get_asset(symbol)

            assert tickerInfo, f'Asset {symbol} not found'

            tickerAsset: Asset = Asset(
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
                min_order_size=tickerInfo.min_order_size
            )
            return tickerAsset
        except alpaca.common.exceptions.APIError as e:
            print("Error: No asset for", symbol)
            return None

    def get_account(self):
        res = self.trading_client.get_account()
        account: IAccount = IAccount(account_id=res.id, cash=float(res.cash), currency=res.currency,
                                     buying_power=float(res.buying_power), shorting_enabled=res.shorting_enabled)
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
            avg_entry_price=position.avg_entry_price,
            qty=position.qty,
            side=position.side.value,
            market_value=position.market_value,
            cost_basis=position.cost_basis,
            current_price=position.current_price,
            unrealized_pl=position.unrealized_pl
        )

    def get_orders(self):
        res = self.trading_client.get_orders()
        orders: List[IOrder] = []
        for order in res:
            orders.append(self.format_order(order))

    def get_order(self, order_id):
        return self.format_order(self.trading_client.get_order_by_id(order_id))

    def format_order(self, order: Order) -> IOrder:
        return IOrder(
            order_id=order.id,
            asset=self.get_ticker_info(order.symbol),
            filled_price=order.filled_avg_price,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            qty=order.qty,
            side=order.side.value,
            type=order.type.value,
            order_class=order.order_class.value,
            time_in_force=order.time_in_force.value,
            status=order.status.value,
            created_at=order.created_at,
            updated_at=order.updated_at,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at

        )

    def manage_insight_order(self, insight: Insight, asset: Asset) -> IOrder | None:
        # TODO: manage insight order by planing entry and exit orders for a given insight
        # https://alpaca.markets/docs/trading/orders/#bracket-orders
        super().manage_insight_order(insight, asset)
        req = None
        try:
            if asset['asset_type'] == 'stock':
                match insight.type:
                    case 'MARKET':
                        if insight.quantity > 1:
                            req = MarketOrderRequest(
                                symbol=insight.symbol,
                                qty=insight.quantity,
                                side=OrderSide.BUY if insight.side == 'long' else OrderSide.SELL,
                                time_in_force=TimeInForce.DAY,
                                order_class=OrderClass.BRACKET,
                                take_profit=TakeProfitRequest(
                                    limit_price=insight.TP[0]
                                ),
                                stop_loss=StopLossRequest(
                                    stop_price=insight.SL,
                                    # stop_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
                                ))
                        else:
                            req = MarketOrderRequest(
                                symbol=insight.symbol,
                                qty=insight.quantity,
                                side=OrderSide.BUY if insight.side == 'long' else OrderSide.SELL,
                                time_in_force=TimeInForce.DAY,
                                order_class=OrderClass.SIMPLE,
                            )
                            # take_profit=TakeProfitRequest(
                            #     limit_price=insight.TP[0]
                            # ),
                            # stop_loss=StopLossRequest(
                            #     stop_price=insight.SL,
                            #     # stop_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
                            # ))

                    case 'LIMIT':
                        req = LimitOrderRequest(
                            symbol=insight.symbol,
                            qty=insight.quantity,
                            side=OrderSide.BUY if insight.side == 'long' else OrderSide.SELL,
                            time_in_force=TimeInForce.DAY,
                            order_class=OrderClass.BRACKET,
                            limit_price=round(insight.limit_price, 2),
                            take_profit=TakeProfitRequest(
                                limit_price=insight.TP[0]
                            ),
                            stop_loss=StopLossRequest(
                                stop_price=insight.SL,
                                # limit_price=round(insight.SL-0.01 if insight.side == 'long' else insight.SL+0.01, 2),
                            )
                        )
                    case _:
                        print(
                            f"ALPACA: Order Type not supported {insight.type} {insight.symbol} ")
                        return
                if req:
                    order = self.trading_client.submit_order(req)
                    return self.format_order(order)

            elif asset['asset_type'] == 'crypto':
                # "crypto orders not allowed for advanced order_class: otoco"}
                match insight.type:
                    case 'MARKET':
                        req = MarketOrderRequest(
                            symbol=insight.symbol,
                            qty=insight.quantity,
                            side=OrderSide.BUY if insight.side == 'long' else OrderSide.SELL,
                            time_in_force=TimeInForce.GTC,
                            order_class=OrderClass.SIMPLE,
                            # take_profit=TakeProfitRequest(
                            #     limit_price=insight.TP[0]
                            # ),
                            # stop_loss=StopLossRequest(
                            #     stop_price=insight.SL,
                            #     limit_price=insight.SL*0.005
                            # )
                        )
                    case 'LIMIT':
                        req = LimitOrderRequest(
                            symbol=insight.symbol,
                            qty=insight.quantity,
                            side=OrderSide.BUY if insight.side == 'long' else OrderSide.SELL,
                            time_in_force=TimeInForce.GTC,
                            order_class=OrderClass.SIMPLE,
                            limit_price=insight.limit_price,
                            # take_profit=TakeProfitRequest(
                            #     limit_price=insight.TP[0]
                            # ),
                            # stop_loss=StopLossRequest(
                            #     stop_price=insight.SL,
                            #     limit_price=insight.SL*0.005
                            # )
                        )

                    case _:
                        print(
                            f"ALPACA: Order Type not supported for crypto {insight.type} {insight.symbol} ")
                        return
            if req:
                order = self.trading_client.submit_order(req)
                return self.format_order(order)
        except alpaca.common.exceptions.APIError as e:
            # print ("ALPACA: Error submitting order", e)
            raise e

        return None

    def close_all_positions(self):
        print("Closing all positions and orders")
        closeOrders = self.trading_client.close_all_positions(
            cancel_orders=True)
        return closeOrders

    def close_position(self, symbol, qty=None, percent=None):
        closePosReq = ClosePositionRequest(
            qty=qty) if qty else ClosePositionRequest(percent=percent)
        order = self.trading_client.close_position(symbol, closePosReq)
        # print("Closed position", order)
        return self.format_order(order)

    def startTradeStream(self, callback: Awaitable):
        self.trading_stream_client.subscribe_trade_updates(callback)
        self.trading_stream_client.run()

    async def closeTradeStream(self):
        self.trading_stream_client.stop()
        await self.trading_stream_client.close()

    def streamBar(self, callback: Awaitable, symbol: str, AssetType: Literal['stock', 'crypto'] = 'stock'):
        if AssetType == 'stock':
            return self.stock_stream_client.subscribe_bars(callback, symbol)
        elif AssetType == 'crypto':
            return self.crypto_stream_client.subscribe_bars(callback, symbol)

    def startStream(self, assetType, type):
        if assetType == 'stock':
            self.stock_stream_client.run()
        elif assetType == 'crypto':
            self.crypto_stream_client.run()

    async def closeStream(self, assetType, type):
        # TODO: unsubscribe from streams type close stream should be called when strategy is stopped - close WSS connection
        if assetType == 'stock':
            self.stock_stream_client.stop()
            if type == 'bars':
                self.stock_stream_client.unsubscribe_bars()
            await self.stock_stream_client.close()
        elif assetType == 'crypto':
            self.crypto_stream_client.stop()
            if type == 'bars':
                self.crypto_stream_client.unsubscribe_bars()
            await self.crypto_stream_client.close()

    def format_on_trade_update(self, trade: TradeUpdate):
        return self.format_order(trade.order), trade.event

    def format_on_bar(self, bar: Bar):
        # print("ALPACA Format", bar)

        data = pd.DataFrame(data={
            # 'symbol': bar.symbol,
            # 'timestamp': bar.timestamp,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
        }, index=[(bar.symbol, bar.timestamp)], columns=['open', 'high', 'low', 'close', 'volume'])
        # data.set_index(['symbol', )], inplace=True)
        return data
