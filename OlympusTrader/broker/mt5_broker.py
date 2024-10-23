
from concurrent.futures import ThreadPoolExecutor
import os
from time import sleep
import MetaTrader5 as mt5
from .base_broker import BaseBroker
from .interfaces import IOrderClass, IOrderLeg, IOrderLegs, ISupportedBrokers, ISupportedBrokerFeatures, IAsset, IAccount, IOrder, IPosition, IQuote, ITimeInForce, ITradeUpdate, ITradeUpdateEvent
from .interfaces import IOrderSide, IOrderType
from ..strategy.interfaces import IMarketDataStream
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, List, Optional, Union
import asyncio
import numpy as np


class Mt5Broker(BaseBroker):
    RUNNING_TRADE_STREAM: bool = False
    """ If The trade stream is running"""
    RUNNING_MARKET_STREAM: bool = False
    """if the market stream is running"""
    _MARKET_STREAMS: dict[IMarketDataStream, asyncio.Future] = {}
    """Market Streams"""

    TF_MAPPING = {
        '1Min': mt5.TIMEFRAME_M1,
        '5Min': mt5.TIMEFRAME_M5,
        '15Min': mt5.TIMEFRAME_M15,
        '30Min': mt5.TIMEFRAME_M30,
        '1Hour': mt5.TIMEFRAME_H1,
        '4Hour': mt5.TIMEFRAME_H4,
        '1Day': mt5.TIMEFRAME_D1,
        '1Week': mt5.TIMEFRAME_W1,
        '1Month': mt5.TIMEFRAME_MN1
    }
    """
    Supported timeframes for MT5 

    TODO: make sure the resolution is in the correct format
    """

    TIMEZONE = timezone.utc
    """MT5 Timezone"""


    def __init__(self, paper: bool, feed=None, timezone = None):
        super().__init__(ISupportedBrokers.MT5, paper, feed)
        print("MetaTrader5 package author: ", mt5.__author__)
        print("MetaTrader5 package version: ", mt5.__version__)

        if not mt5.initialize():
            raise BaseException(
                "initialize() failed, error code =", mt5.last_error())

        assert os.getenv('MT5_LOGIN'), 'MT5_LOGIN not set'
        assert os.getenv('MT5_SECRET_KEY'), 'MT5_SECRET_KEY not set'
        assert os.getenv('MT5_SERVER'), 'MT5_SERVER not set'

        auth = mt5.login(login=int(os.getenv('MT5_LOGIN')), password=os.getenv(
            'MT5_SECRET_KEY'), server=os.getenv('MT5_SERVER'))
        if not auth:
            raise BaseException(
                "Failed to login to MetaTrader 5", mt5.last_error())
        terminal_info=mt5.terminal_info()
        if terminal_info.tradeapi_disabled:
            raise BaseException(
                "Please enable trades from API in MetaTrader 5", mt5.last_error())
        # set time zone

        if timezone:
            self.TIMEZONE = timezone
        else:
            if not self.get_broker_timezone():
                raise BaseException("Failed to get broker's timezone from MetaTrader 5")



        self.supportedFeatures = ISupportedBrokerFeatures(
            barDataStreaming=True, featuredBarDataStreaming=True, trailingStop=False)

    def __del__(self):
        # Shut down connection to the MetaTrader 5
        mt5.shutdown()
    
    def get_broker_timezone(self):
        try:
            symbols=mt5.symbols_get()
            # Get the timezone shift from the first symbol
            # tzdif = pd.Timestamp(symbols[0].time, unit='s') - datetime.now()
            # tzdif = pd.Timestamp(symbols[0].time, unit='s') - pd.Timestamp.now()
            tzdif = pd.Timestamp(symbols[0].time, unit='s', tz=timezone.utc) - pd.Timestamp.now(timezone.utc)
            
            self.TIMEZONE = timezone(tzdif.round(freq='H'))
            # self.TIMEZONE = timezone(np.abs(tzdif).round(freq='H'))
            return True
        except Exception as e:
            print(f"Error: {e}")
            return None


    def get_ticker_info(self, symbol: str) -> Union[IAsset, None]:
        if self.TICKER_INFO.get(symbol):
            return self.TICKER_INFO[symbol]
        try:
            symbol = symbol.replace('/', '')
            tickerInfo = mt5.symbol_info(symbol)
            if not tickerInfo:
                return None
            if not tickerInfo.visible:
                print(symbol, "is not visible, trying to switch on")
                if not mt5.symbol_select(symbol, True):
                    print("Failed to switch on", symbol)
                    None

            # TODO: Store the size of one lot and max contract size
            tradeable = False if tickerInfo.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED or (
                tickerInfo.trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY) else True
            shortable = False if not tradeable or (
                tickerInfo.trade_mode == mt5.SYMBOL_TRADE_MODE_LONGONLY) else True

            fractionable = True if tickerInfo.volume_step < 1 else False

            asset_type = tickerInfo.path.split('\\')[0].lower()

            status = "active" if tickerInfo.visible else "inactive"

            tickerAsset: IAsset = IAsset(
                id=tickerInfo.name,
                name=tickerInfo.description,
                asset_type=asset_type,
                exchange="MT5",
                symbol=symbol,
                status=status,
                tradable=tradeable,
                marginable=True,
                shortable=shortable,
                fractionable=fractionable,
                min_order_size=tickerInfo.volume_min,
                max_order_size=tickerInfo.volume_max,
                min_price_increment=tickerInfo.point,
                price_base=tickerInfo.digits,
                contract_size=tickerInfo.trade_contract_size

            )
            self.TICKER_INFO[symbol] = tickerAsset
            return tickerAsset

        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_account(self) -> IAccount:
        try:
            account_info = mt5.account_info()

            if not account_info:
                return None

            account = IAccount(
                account_id=str(account_info.login),
                equity=account_info.equity,
                cash=account_info.balance,
                currency=account_info.currency,
                buying_power=account_info.margin_free,
                # TODO: Check if this is correct as we are just assuming
                shorting_enabled=account_info.trade_allowed,
                leverage=account_info.leverage
            )
            return account
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_position(self, symbol) -> IPosition:
        try:
            position = mt5.positions_get(symbol=symbol)
            if not position:
                return None

            position: IPosition = self.format_position(position[0])
            return position
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_positions(self) -> dict[str, IPosition]:
        try:
            positions = mt5.positions_get()
            if not positions:
                return None

            positions = {position.ticket: self.format_position(
                position) for position in positions}
            # positions = {position.symbol: self.format_position(position) for position in positions}
            return positions

        except Exception as e:
            print(f"Error: {e}")
            return None

    def format_position(self, position: Any) -> IPosition:
        try:
            # Should always be a Trade Posion Class
            return IPosition(
                asset=self.get_ticker_info(position.symbol),
                avg_entry_price=position.price_open,
                qty=position.volume,
                side=IOrderSide.BUY if position.type == 0 else IOrderSide.SELL,
                market_value=position.price_current * position.volume,
                cost_basis=position.price_open * position.volume,
                current_price=position.price_current,
                unrealized_pl=position.profit
            )
        except Exception as e:
            print("Error: {e}")
            return None

    def close_position(self, symbol: str, qty: Optional[float] = None, percent: Optional[float] = None) -> Optional[IOrder]:
        """
        Close a position the param symbol for mt5 is the ticket ID
        """
        super().close_position(symbol, qty, percent)
        try:
            #  Get the position
            positions = self.get_positions()
            if not positions:
                return
            position = positions[symbol]
            if not position:
                return None

            qty_confirmed = None
            # check if we are closing more than we have
            if qty:
                if qty > position['qty']:
                    raise BaseException("Cannot close more than you have")
                else:
                    qty_confirmed = qty
            elif percent:
                qty_confirmed = (position['qty'] * percent)

            # TODO: Will have to test if its position_by or position to close the position  -this looks right for now idk what the difference is rn
            if qty_confirmed != None:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": position['asset'].get('symbol'),
                    "volume": qty_confirmed,
                    "type": mt5.ORDER_TYPE_BUY if position.side == IOrderSide.SELL else mt5.ORDER_TYPE_SELL,
                    "magic": 234777,
                    "comment": "OlympusTrader Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_RETURN,
                    "position": symbol
                    # "position_by": symbol

                }
                result = mt5.order_send(request)
                return self.format_order(result)
            else:
                return None

        except BaseException as e:
            print(e)
            return None

    def close_all_positions(self):
        positions = self.get_positions()
        if not positions:
            return
        for ticket, position in enumerate(positions):
            mt5.Close(symbol=position.symbol, ticket=ticket)

    def get_orders(self) -> Optional[dict[str, IOrder]]:
        try:
            orders: dict[str, IOrder] = {}
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_order(self, order_id) -> Optional[IOrder]:
        try:
            order = self.format_order(mt5.order_get(ticket=order_id))
            return order
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_latest_quote(self, asset: IAsset) -> IQuote:
        try:
            quote = mt5.symbol_info_tick(asset.symbol)
            if not quote:
                return None
            return self.format_on_quote(quote, asset.symbol)
        except Exception as e:
            print(f"Error: {e}")
            return None

    def cancel_order(self, order_id: str) -> Optional[str]:
        try:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order_id,
                "comment": "OlympusTrader Cancel",
            }
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Order to cancel failed, retcode={
                      result.retcode}, comment={result.comment}")
                return None
            # FIXME: This could also return an error as the position has been filled so cant be cancelled - we will need to check for that.
            return order_id
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_history(self, asset: IAsset, start, end, resolution) -> pd.DataFrame:
        # TF_MAPPING
        try:
            # exchangeTime = pd.Timestamp(mt5.symbol_info(
            #     asset["symbol"]).time, unit='s', tz=self.TIMEZONE)
            # nowTime = datetime.now(self.TIMEZONE)
            # timeZoneShift = abs(exchangeTime - nowTime)

            # if nowTime > exchangeTime:
            #     start = start - timeZoneShift
            #     end = end - timeZoneShift
            # else:
            #     start = start + timeZoneShift
            #     end = end + timeZoneShift

            rates = mt5.copy_rates_range(
                asset['symbol'], int(resolution), start.astimezone(self.TIMEZONE).replace(tzinfo=timezone.utc), end.astimezone(self.TIMEZONE).replace(tzinfo=timezone.utc))
            # rates = mt5.copy_rates_range(
            #     asset['symbol'], int(resolution), start, end)
            if rates.size < 1:
                return None
            bar = self.format_on_bar(rates, asset['symbol'])

            return bar
        except Exception as e:
            print(f"Error: {e}")
            return None

    def execute_insight_order(self, insight, asset) -> Union[IOrder, None]:
        super().execute_insight_order(insight, asset)
        deviation = 5
        #   Might need to use the below action for limit orders
        # "action": TRADE_ACTION_PENDING

        if asset['contract_size'] > 1:
            volume = insight.contracts
        else:
            volume = insight.quantity
        
        if volume > self.get_ticker_info(insight.symbol).get("max_order_size", np.infty):
            # We could clamp here but user logic would not be aware until after we commit the order.
            print("exceesing max order limit")
            return None 

        si = mt5.symbol_info(asset['symbol'])

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": insight.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if insight.side == IOrderSide.BUY else mt5.ORDER_TYPE_SELL,
            "deviation": deviation,
            "magic": 234777,
            "comment": f"OlympusTrader Open - {insight.strategyType.value}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        if insight.type == IOrderType.LIMIT:
            request['type'] = mt5.ORDER_TYPE_BUY_LIMIT if insight.side == IOrderSide.BUY else mt5.ORDER_TYPE_SELL_LIMIT
            # currentPrice = mt5.symbol_info_tick(asset["symbol"]).ask   if insight.side == IOrderSide.BUY else mt5.symbol_info_tick(asset["symbol"]).bid
            # priceDiffInpoints = np.abs(currentPrice - insight.limit_price) * si.point
            # request['price'] =  (currentPrice-priceDiffInpoints  if insight.side == IOrderSide.BUY else currentPrice+priceDiffInpoints) * si.point
            request['price'] = insight.limit_price
            request['action'] = mt5.TRADE_ACTION_PENDING
            # if si.filling_mode == mt5.SYMBOL_TRADE_EXECUTION_MARKET:
            #      request['type_filling'] =  mt5.ORDER_FILLING_BOC
        elif insight.type == IOrderType.MARKET:
            request['type'] = mt5.ORDER_TYPE_BUY if insight.side == IOrderSide.BUY else mt5.ORDER_TYPE_SELL
            request['type_filling'] = mt5.ORDER_FILLING_IOC
            request['price'] = mt5.symbol_info_tick(asset["symbol"]).ask if insight.side == IOrderSide.BUY else mt5.symbol_info_tick(asset["symbol"]).bid
        # set the take profit and stop loss
        if insight.TP:
            # tp_points = round(np.abs(insight.TP[-1] - request['price']) * si.point)
            # request['tp'] = tp_points if insight.side == IOrderSide.BUY else tp_points
            request['tp'] = insight.TP[-1]
        if insight.SL:
            # sl_points = round(np.abs(insight.SL - request['price']) * si.point)
            # request['sl'] = sl_points if insight.side == IOrderSide.BUY else sl_points
            request['sl'] = insight.SL
        # MT5 requires you to set the position ID if you are wanting to close the order.
        # we can check if it is a close order and set the position ID (open ID is set)
        if insight.order_id:
            # This is likely a close order / reduce order
            request['position'] = insight.order_id
            request["comment"] = f"OlympusTrader Close - {insight.strategyType.value}"

        try:
            check_result = mt5.order_check(request)
            if check_result.retcode  != 0  and check_result.retcode != mt5.TRADE_RETCODE_DONE:
                # TODO: Check if we need to handle this differently return the error
                print(f"Order send failed, retcode={
                      check_result.retcode}, comment={check_result.comment}")
                # retcode=10027 Algorithmic trading is disabled
                #
                return None

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                # Should not error here as we have already checked
                print(f"Order send failed, retcode={
                      result.retcode}, comment={result.comment}")
                # retcode=10027 Algorithmic trading is disabled
                #
                return None
            legs = IOrderLegs()
            if result[10].tp:
                legs['take_profit'] = IOrderLeg(
                    order_id=None,
                    limit_price=result[10].tp,
                    filled_price=None,
                    type=IOrderType.LIMIT,
                    status=ITradeUpdateEvent.PENDING_NEW,
                    order_class=IOrderClass.OTO,
                    # created_at=leg.created_at,
                    # updated_at=leg.updated_at,
                    # submitted_at=leg.submitted_at,
                    # filled_at=leg.filled_at
                )
            elif result[10].sl:
                legs['stop_loss'] = IOrderLeg(
                    order_id=None,
                    limit_price=result[10].sl,
                    filled_price=None,
                    type=IOrderType.STOP,
                    status=ITradeUpdateEvent.PENDING_NEW,
                    order_class=IOrderClass.OTO,
                    # created_at=leg.created_at,
                    # updated_at=leg.updated_at,
                    # submitted_at=leg.submitted_at,
                    # filled_at=leg.filled_at
            )
            order = IOrder(
                order_id=result.order,
                asset=asset,
                filled_price=None,
                limit_price=result.ask if insight.side == IOrderSide.BUY else result.bid,
                stop_price=None,
                qty=result.volume,
                filled_qty=None,
                side=insight.side,
                type=insight.type,
                order_class=insight.classType,
                legs=legs
            )
            return order
        except Exception as e:
            print(f"Error: {e}")
            return None

    def startTradeStream(self, callback: Awaitable):
        """
        Starts a listener that will pass the trade events to the strategy
        """
        super().startTradeStream(callback)
        self.RUNNING_TRADE_STREAM = True
        # Rate limit for new trade signals
        rate = 0.5
        loop = asyncio.new_event_loop()

        lastChecked = datetime.now(self.TIMEZONE).replace(tzinfo=timezone.utc)
        while self.RUNNING_TRADE_STREAM:
            sleep(1/rate)
            now = datetime.now(self.TIMEZONE).replace(tzinfo=timezone.utc)
            new_incoming_orders = mt5.history_orders_get(lastChecked, now)
            new_incoming_deals = mt5.history_deals_get(lastChecked, now)
            # TODO:Check if they are sorted!
            if (new_incoming_orders and len(new_incoming_orders) > 0) or (new_incoming_deals and len(new_incoming_deals) > 0):
                # print("Oders", new_incoming_orders)
                # print("Deal", new_incoming_deals)
                for order in new_incoming_orders:
                    try:
                        loop.run_until_complete(callback(ITradeUpdate(order, order.state)))
                    except Exception as e:
                        print(f"Error: {e}")
                        
            lastChecked = now
        loop.close()
# TradeOrder(ticket=530218319, time_setup=1582282114, time_setup_msc=1582282114681, time_done=1582303777, time_done_msc=1582303777582, time_expiration=0, ...

    async def closeTradeStream(self):
        # TODO: Will have to build this out
        self.RUNNING_TRADE_STREAM = False
        pass

    def streamMarketData(self, callback: Awaitable, assetStreams):
        super().streamMarketData(callback, assetStreams)
        self.RUNNING_MARKET_STREAM = True
        barStreamCount = len(
            [asset for asset in assetStreams if asset['type'] == 'bar'])
        # Threading pools for the streams
        pool = ThreadPoolExecutor(max_workers=(
            barStreamCount), thread_name_prefix="MarketDataStream")
        loop = asyncio.new_event_loop()
        for asset in assetStreams:
            try:
                if asset['type'] == 'bar':

                    async def MT5BarStreamer(asset):
                        # Set to last valid time (May need to change as we dont want any signals for past data)
           
                        # lastChecked = pd.Timestamp(mt5.symbol_info(
                        #     asset["symbol"]).time, unit='s', tz=self.TIMEZONE)
                        lastChecked = pd.Timestamp.now(tz=self.TIMEZONE).replace(tzinfo=timezone.utc)
                        while self.RUNNING_MARKET_STREAM:
                            nextTimetoCheck = asset['time_frame'].get_next_time_increment(
                                lastChecked)
                            # .replace(tzinfo=tz)
                            await asyncio.sleep((nextTimetoCheck - lastChecked).total_seconds())
                            # may use self.TF_MAPPING[]

                            # bars = mt5.copy_rates_range(asset['symbol'], int(
                            #     asset['time_frame']), lastChecked.timestamp(), nextTimetoCheck.timestamp())

                            bars = mt5.copy_rates_from(asset['symbol'], int(
                                asset['time_frame']), lastChecked, 1)
                            # bars = mt5.copy_rates_from(asset['symbol'], int(
                            #     asset['time_frame']), lastChecked, 2)
                            # May need the one below if we need to make the bar if the time frame is not supported
                            # bars = mt5.copy_rates_from(asset['symbol'], int(
                            #     asset['time_frame']), lastChecked, asset['time_frame'].amount)
                            if isinstance(bars, np.ndarray) and len(bars) > 0:
                                barDatas = self.format_on_bar(
                                    bars, asset['symbol'])
                                for idx in range(0, len(barDatas)):
                                    try:
                                        bar = barDatas.iloc[[idx]]
                                        # if asset['time_frame'].is_time_increment(bar.index[0][1]) and (not (bar.index[0][1]) < lastChecked):
                                        if asset['time_frame'].is_time_increment(bar.index[0][1]) and (not (bar.index[0][1]) < lastChecked):
                                            # TODO: Handle Feature streams? Strategy already handles renaming the index to include feature name
                                            loop.run_until_complete(
                                                callback(bar, timeframe=asset['time_frame']))
                                    except Exception as e:
                                        print(f"Error: {e}")
                                        continue
                            # Update the last checked time for this stream. -> moved to the top as run_until_complete may take over a min and we are clamped to the next min
                            lastChecked = nextTimetoCheck

                    streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                    self._MARKET_STREAMS[streamKey] = loop.create_task(
                        MT5BarStreamer(asset), name=f"Market:{streamKey}")
                    # self._MARKET_STREAMS[streamKey] = loop.run_in_executor(pool, MT5BarStreamer, asset)
                else:
                    raise NotImplementedError(
                        f"Stream type {asset['type']} not supported")
            except Exception as e:
                print(f"Error: {e}")
                continue
        # TODO: Will need a way to close this stream as its not being referenced anywhere else
        loop.run_forever()

    async def closeStream(self, assetStreams):
        if self.RUNNING_MARKET_STREAM:
            for asset in assetStreams:
                streamKey = f"{asset['symbol']}:{str(asset['time_frame'])}"
                marketStream = self._MARKET_STREAMS.get(streamKey)
                if marketStream:
                    await marketStream.cancel()
                    del self._MARKET_STREAMS[streamKey]
                if len(self._MARKET_STREAMS) == 0:
                    self.RUNNING_MARKET_STREAM = False

    def format_on_bar(self, bar: Any, symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        if isinstance(bar, np.ndarray):
            index = pd.MultiIndex.from_product(
                [[symbol], pd.to_datetime(bar['time'], utc=True, unit='s')], names=['symbol', 'date'])

            res = pd.DataFrame(data={
                'open': bar['open'],
                'high': bar['high'],
                'low': bar['low'],
                'close': bar['close'],
                'volume': bar['tick_volume'],
            }, index=index, columns=['open', 'high', 'low', 'close', 'volume'])
            return res
        else:
            return None

    def format_on_quote(self, quote: Any, symbol=None) -> IQuote:
        data = IQuote(
            symbol=symbol,
            bid=quote.bid,
            ask=quote.ask,
            bid_size=0,
            ask_size=0,
            volume=quote.volume,
            timestamp=self.time
        )
        return data

    def format_order(self, order: Any) -> IOrder:
        # if isinstance(order, dict):
        #     return order
        if type(order) == IOrder:
            return order
        
        side = None
        orderType = None
        match order.type:
            case mt5.POSITION_TYPE_BUY:
                side = IOrderSide.BUY
                orderType = IOrderType.MARKET
            case mt5.POSITION_TYPE_SELL:
                side = IOrderSide.SELL
                orderType = IOrderType.MARKET
            case mt5.ORDER_TYPE_BUY_LIMIT:
                side = IOrderSide.BUY
                orderType = IOrderType.LIMIT
            case mt5.ORDER_TYPE_SELL_LIMIT:
                side = IOrderSide.SELL
                orderType = IOrderType.LIMIT
            case mt5.ORDER_TYPE_BUY_STOP:
                side = IOrderSide.BUY
                orderType = IOrderType.STOP
            case mt5.ORDER_TYPE_SELL_STOP:
                side = IOrderSide.SELL
                orderType = IOrderType.STOP
            case mt5.ORDER_TYPE_BUY_STOP_LIMIT:
                side = IOrderSide.BUY
                orderType = IOrderType.STOP_LIMIT
            case mt5.ORDER_TYPE_SELL_STOP_LIMIT:
                side = IOrderSide.SELL
                orderType = IOrderType.STOP_LIMIT
            case mt5.ORDER_TYPE_CLOSE_BY:
                pass
            #     side = IOrderSide.BUY
            #     orderType = IOrderType.STOP_LIMIT
            case _:
                raise NotImplementedError("Oder Type not found")

        
            


        orderID = order.ticket
        #  TODO: add support for order legs
        legs = IOrderLegs()
        if order.tp:
            legs['take_profit'] = IOrderLeg(
                order_id=None,
                limit_price=order.tp,
                filled_price=None,
                type=IOrderType.LIMIT,
                status=ITradeUpdateEvent.PENDING_NEW,
                order_class=IOrderClass.OTO,
                created_at=pd.Timestamp(order.time_done, unit='s', tz=timezone.utc),
                # updated_at=leg.updated_at,
                # submitted_at=leg.submitted_at,
                # filled_at=leg.filled_at
            )
        if order.sl:
            legs['stop_loss'] = IOrderLeg(
                order_id=None,
                limit_price=order.sl,
                filled_price=None,
                type=IOrderType.STOP,
                status=ITradeUpdateEvent.PENDING_NEW,
                order_class=IOrderClass.OTO,
                created_at=pd.Timestamp(order.time_done, unit='s', tz=timezone.utc),
                # updated_at=leg.updated_at,
                # submitted_at=leg.submitted_at,
                # filled_at=leg.filled_at
            )
            """
            ticket         
            time_setup  
            time_setup_msc  
            time_expiration  
            type  type_time  type_filling  
            state  magic  volume_current  
            price_open   sl   tp  price_current  symbol 
            comment external_id
            """

        res = IOrder(
            order_id=orderID,
            asset=self.get_ticker_info(order.symbol),
            filled_price=order.price_current if order.price_open != 0.0 else (None if orderType != IOrderType.MARKET else order.price_current),
            limit_price=order.price_open if order.price_open != 0.0 else None,
            stop_price=order.price_stoplimit if order.price_stoplimit != 0.0 else None,
            qty=order.volume_initial + order.volume_current,
            filled_qty=order.volume_initial,
            side=side,
            type=orderType,
            order_class=IOrderClass.SIMPLE if (
                order.tp == 0 and order.sl == 0) else IOrderClass.OTO,
            time_in_force=ITimeInForce.GTC if (
                order.type_time == mt5.ORDER_TIME_GTC) else ITimeInForce.DAY,
            status=order.state,
            created_at=pd.Timestamp(order.time_setup, unit='s', tz=timezone.utc),
            updated_at=pd.Timestamp(order.time_done, unit='s', tz=timezone.utc),
            submitted_at=pd.Timestamp(order.time_setup, unit='s', tz=timezone.utc),
            filled_at= pd.Timestamp(order.time_done, unit='s', tz=timezone.utc),
            legs=legs

        )
        return res

    def format_on_trade_update(self, trade: Any) -> tuple[IOrder, ITradeUpdateEvent]:
        event: ITradeUpdateEvent = None
        match trade.event:
            case mt5.ORDER_STATE_FILLED:
                event = ITradeUpdateEvent.FILLED
            case mt5.ORDER_STATE_PARTIAL:
                event = ITradeUpdateEvent.PARTIAL_FILLED
            case mt5.ORDER_STATE_CANCELED:
                event = ITradeUpdateEvent.CANCELED
            case mt5.ORDER_STATE_REJECTED:
                event = ITradeUpdateEvent.REJECTED
            case mt5.ORDER_STATE_PLACED:
                event = ITradeUpdateEvent.PENDING_NEW
            case mt5.ORDER_STATE_STARTED:
                event = ITradeUpdateEvent.NEW
            case mt5.ORDER_STATE_EXPIRED:
                event = ITradeUpdateEvent.EXPIRED
            case mt5.ORDER_STATE_REQUEST_MODIFY:
                event = ITradeUpdateEvent.REPLACED
            # case mt5.ORDER_STATE_PLACED:
            #     # Might not even be needed  as mt5 does not have the accepted
            #     event = ITradeUpdateEvent.ACCEPTED
            case _:
                event = trade.event
        order = self.format_order(trade.order)
        order["status"] = event
        return order, event
