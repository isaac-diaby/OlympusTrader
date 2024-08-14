import time
import pandas_ta as ta
import pandas as pd
from datetime import datetime, timedelta
from OlympusTrader.broker.interfaces import IOrderSide
from OlympusTrader.broker.paper_broker import PaperBroker
from OlympusTrader.insight.insight import Insight, StrategyTypes, InsightState, StrategyDependantConfirmation
from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit
from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader.utils.tools import dynamic_round
from OlympusTrader import AlpacaBroker, Strategy
import numpy as np

import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class QbitTB(Strategy):

    def start(self):
        state = self.state

        # Technical Indicators Params
        # name=f"RSI_OB/OS",
        # description="simple RSI OB/OS",
        self.add_ta([
                {"kind": 'atr', "length": 14},
                {"kind": 'rsi', "length": 14, "scalar": 10},
            ])
        self.warm_up = 14
        # 4% of account per trade
        self.execution_risk = 0.04
        # 2:1 Reward to Risk Ratio minimum
        self.minRewardRiskRatio = 2.0
        self.baseConfidence = 0.1

    def init(self, asset):
        state = self.state
        # inital market state
        if (state.get('market_state') == None):
            state['market_state'] = {}
        state['market_state'][asset['symbol']] = 0


        self.history[asset['symbol']] = self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(), self.warm_up), datetime.now(), self.resolution)

    def universe(self):
        # universe = {'btc-usd', 'eth-usd', 'xrp-usd'}
        # universe = {'btc-usd', 'eth-usd', 'xrp-usd', 'ada-usd'}
        # universe = {'aapl'}
        universe = {'btc-usd'}
        return universe

    def on_bar(self, symbol, bar):
        self.computeMarketState(symbol)


    def computeMarketState(self, symbol: str):
        marketState = self.state['market_state'][symbol]
        history = self.history[symbol]
        IRSI = history['RSI_14']

        marketState = 0
        if (IRSI.iloc[-1] < 30):
            marketState += 2
        elif (IRSI.iloc[-1] > 70):
            marketState -= 2
        else:
            if (IRSI.iloc[-1] < 50):
                marketState += 1
            elif (IRSI.iloc[-1] > 50):
                marketState -= 1

        # take no action if Market Has no Volume based on the Volume Quantile > 0.75
        if (history['volume'].iloc[-1] < round(history['volume'].quantile(0.75), 2)):
            marketState = 0
            pass
        else:
            if (marketState > 0):
                marketState += 1
            elif (marketState < 0):
                marketState -= 1
        marketState = np.minimum(np.maximum(marketState, -5), 5)
        self.state['market_state'][symbol] = marketState
        return marketState

    def generateInsights(self, symbol: str):
        # Compute Market State
        self.computeMarketState(symbol)

        history = self.history[symbol].loc[symbol]
        latestBar = history.iloc[-1]
        previousBar = history.iloc[-2]
        latestIATR = latestBar['ATRr_14']
        marketState = self.state['market_state'][symbol]
        baseConfidence = self.baseConfidence
        # marketState = -1

        # Do not trade if market state is 0
        if (marketState == 0):
            return

            # TEST
        # if (len(self.insights) < 1):
        #     if (marketState > 0):
        #         print(f"Insight - {symbol}: TEST: Long")
        #         TP = self.tools.dynamic_round(
        #             (latestBar.close + (latestIATR*10)), symbol)
        #         SL = self.tools.dynamic_round(
        #             (latestBar.close - (latestIATR*1.5)), symbol)
        #         ENTRY = latestBar.close
        #         # ENTRY = previousBar.high if (abs(
        #         #     previousBar.high - latestBar.close) < latestIATR) else dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
        #         self.add_insight(Insight(IOrderSide.BUY, symbol,
        #                              StrategyTypes.TEST, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), 'HRVCM', 2, 3))
        #     else:
        #         print(f"Insight - {symbol}: TEST: Short")
        #         TP = self.tools.dynamic_round(
        #             (latestBar.close - (latestIATR*10)), symbol)
        #         SL = self.tools.dynamic_round(
        #             (latestBar.close + (latestIATR*1.5)), symbol)
        #         ENTRY = latestBar.close
        #         # ENTRY = previousBar.low if (abs(
        #         #     previousBar.low - latestBar.close) < latestIATR) else dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
        #         self.add_insight(Insight(IOrderSide.SELL, symbol,
        #                              StrategyTypes.TEST, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), 'HRVCM', 2, 3))

        if (latestBar['RSI_14'] < 30 and previousBar['RSI_14'] > 30 and marketState > 0):
            # print(f"Insight - {symbol}: Long RSI: {latestBar['RSI_14']}")
            TP = self.tools.dynamic_round(
                (latestBar.close + (latestIATR*6 * abs(marketState))), symbol)
            SL = self.tools.dynamic_round(
                (latestBar.close - (latestIATR*1.5)), symbol)
            ENTRY = previousBar.high if (abs(
                previousBar.high - latestBar.close) < latestIATR) else self.tools.dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
            # time to live unfilled
            TTLUF = self.tools.calculateTimeToLive(
                latestBar['close'], ENTRY, latestIATR, 5)
            # time to live till take profit
            TTLF = self.tools.calculateTimeToLive(TP, ENTRY, latestIATR, 5)

            self.add_insight(Insight(IOrderSide.BUY, symbol,
                                     "RSI_OS", self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))

        if (latestBar['RSI_14'] > 70 and previousBar['RSI_14'] < 70 and marketState < 0):
            # print(f"Insight - {symbol}: Short RSI: {latestBar['RSI_14']}")
            TP = self.tools.dynamic_round(
                (latestBar.close - (latestIATR*6 * abs(marketState))), symbol)
            SL = self.tools.dynamic_round(
                (latestBar.close + (latestIATR*1.5)), symbol)
            ENTRY = previousBar.low if (abs(
                previousBar.low - latestBar.close) < latestIATR) else self.tools.dynamic_round((latestBar.open-(.2*latestIATR)), symbol)
            # time to live unfilled
            TTLUF = self.tools.calculateTimeToLive(
                latestBar['close'], ENTRY, latestIATR, 5)
            # time to live till take profit
            TTLF = self.tools.calculateTimeToLive(TP, ENTRY, latestIATR, 5)

            self.add_insight(Insight(IOrderSide.SELL, symbol,
                                     "RSI_OB", self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))

        return

    def executeInsight(self, insight):
        RISK = self.execution_risk
        RewardRiskRatio = self.minRewardRiskRatio

        history = self.history[insight.symbol].loc[insight.symbol]
        latestBar = history.iloc[-1]

        orders = self.orders
        match insight.state:
            case InsightState.NEW:
                try:
                    if (insight.hasExpired()):
                        self.insights[insight.INSIGHT_ID].updateState(
                            InsightState.EXPIRED, f"Expired: Before Execution")
                        return
                    # Not shortable
                    if (insight.side == IOrderSide.SELL and not self.assets[insight.symbol]['shortable']):
                        self.insights[insight.INSIGHT_ID].updateState(
                            InsightState.REJECTED, f"Short not allowed")
                        return

                    # Get price from latest bar if limit price is not set
                    self.insights[insight.INSIGHT_ID].update_limit_price(self.history[insight.symbol].loc[insight.symbol].iloc[-1].close if (
                        (insight.type == 'MARKET') or np.isnan(insight.limit_price)) else insight.limit_price)

                    RR = self.insights[insight.INSIGHT_ID].getPnLRatio()

                    if RR < RewardRiskRatio:
                        self.insights[insight.INSIGHT_ID].updateState(
                            InsightState.REJECTED, f"Low RR: {RR}")
                        return

                    if (insight.quantity == None):

                        diluted_account_margin_size = self.account['buying_power'] * (
                            insight.confidence)
                        account_size_at_risk = self.account['cash'] * (
                            insight.confidence*RISK)

                        riskPerShare = abs(
                            self.insights[insight.INSIGHT_ID].limit_price - insight.SL)
                        size_can_buy = (
                            diluted_account_margin_size)/self.insights[insight.INSIGHT_ID].limit_price
                        size_should_buy = account_size_at_risk/riskPerShare

                        min_order_size = self.assets[insight.symbol]['min_order_size']
                        if (size_should_buy < min_order_size):
                            self.insights[insight.INSIGHT_ID].updateState(
                                InsightState.REJECTED, f"Low funds at Risk: {account_size_at_risk:^10}")
                            return

                        # np.round(diluted_account_size/price, 2)
                        self.insights[insight.INSIGHT_ID].quantity = round(
                            min(size_should_buy, size_can_buy), len(str(min_order_size).split('.')[1]))

                        # continue
                        if (self.insights[insight.INSIGHT_ID].quantity >= 1):
                            # Cant but fractional shares on limit orders with alpaca so round down
                            self.insights[insight.INSIGHT_ID].quantity = np.floor(
                                self.insights[insight.INSIGHT_ID].quantity)
                        else:
                            pass
                            # self.insights[insight.INSIGHT_ID].type = 'MARKET'

                        if self.insights[insight.INSIGHT_ID].type == 'MARKET':
                            pass
                        else:
                            pass
                            # self.insights[insight.INSIGHT_ID].updateState(InsightState.CANCELED)

                    if (self.positions.get((insight.symbol)) != None):
                        # Check if there is a position open in the opposite direction
                        holding = self.positions[insight.symbol]
                        # Close position if holding is in the opposite direction of insight
                        if (holding != None or len(holding) != 0):
                            if (holding['side'] != insight.side):
                                # Close all insighs in the opposite direction
                                for x, otherInsight in self.insights.items():
                                    match otherInsight.state:
                                        case InsightState.FILLED:
                                            if (otherInsight.side != insight.side and otherInsight.symbol == insight.symbol):
                                                # Indecate that the market has changed
                                                self.insights[x].marketChanged = True
                        else:
                            # TODO: Check if the holding is in the same direction as the new insight and if the insight is in profit, move the SL to break even.
                            pass

                            # self.close_position(
                            #     insight.symbol, holding['qty'])

                    order = self.submit_order(insight)

                    if order:
                        self.insights[insight.INSIGHT_ID].updateOrderID(
                            order['order_id'])
                        self.insights[insight.INSIGHT_ID].updateState(
                            InsightState.EXECUTED, f"Order ID: {order['order_id']}")
                    else:
                        self.insights[insight.INSIGHT_ID].updateState(
                            InsightState.REJECTED, f"Failed to submit order")

                except BaseException as e:
                    # print(f"Error: {e}")
                    self.insights[insight.INSIGHT_ID].updateState(
                        InsightState.REJECTED, f"Error: {e}")
                    return
                    # raise e

            case InsightState.EXECUTED:
                # Check if filled or not or should be expired or not
                self.insights[insight.INSIGHT_ID].hasExpired(True)
                # self.insights[insight.INSIGHT_ID].updateState(
                #     InsightState.CANCELED, f"Expired {symbol}: After Execution")

            case InsightState.FILLED:
                shouldClosePosition = False
                cause = None
                # Check if the trade insight is exhausted and needs to be closed
                if (self.insights[insight.INSIGHT_ID].hasExhaustedTTL()):
                    shouldClosePosition = True
                    cause = "Exhausted TTL"

                # Check if market has changed
                if (insight.marketChanged):
                    shouldClosePosition = True
                    cause = "Market Changed"
                    # if (self.broker.close_position(insight.symbol, percent=100)):
                    #     self.insights[insight.INSIGHT_ID].updateState(InsightState.CLOSED, f"Exhausted TTL")

                # TODO: Since Alpaca does not support stop loss for crypto, we need to manage it manually
                if ((insight.side == IOrderSide.BUY) and (insight.SL > latestBar.low)) or ((insight.side == IOrderSide.SELL) and (insight.SL < latestBar.high)):
                    shouldClosePosition = True
                    cause = "SL Hit"
                # TODO: Take Profit if TP [0] is hit
                if ((insight.side == IOrderSide.BUY) and (insight.TP[0] < latestBar.high)) or ((insight.side == IOrderSide.SELL) and (insight.TP[0] > latestBar.low)):
                    shouldClosePosition = True
                    cause = "TP Hit"

                if (shouldClosePosition):
                    closeOrder = None
                    try:

                        # Send a Market order to close the position manually
                        match cause:
                            case "Exhausted TTL" | "SL Hit" | "Market Changed":
                                closeOrder = self.submit_order(Insight(IOrderSide.BUY if (
                                    insight.side == IOrderSide.SELL) else IOrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                            case "TP Hit":
                                # If there is a TP 2 or 3, we need to close only a portion of the position, move the SL to break even and let the rest run until TP 2 or 3 is hit.
                                if len(insight.TP) > 1:
                                    currentTP = self.insights[insight.INSIGHT_ID].TP[0]
                                    # Close 80% of the position
                                    quantityToClose = dynamic_round(
                                        insight.quantity*0.8)
                                    closeOrder = self.submit_order(Insight(IOrderSide.BUY if (
                                        insight.side == IOrderSide.SELL) else IOrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, quantityToClose))
                                    if closeOrder:
                                        # update remaining quantity
                                        self.insights[insight.INSIGHT_ID].quantity = insight.quantity - \
                                            quantityToClose
                                        # Move SL to break even
                                        # TODO: update SL to break even
                                        self.insights[insight.INSIGHT_ID].SL = insight.limit_price
                                        self.insights[insight.INSIGHT_ID].TP.pop(
                                            0)
                                        # Reset TTL for the remaining position
                                        self.insights[insight.INSIGHT_ID].updateState(InsightState.FILLED, f"Partial TP Hit: {insight.side:^8}: {insight.limit_price} -> {currentTP} -> {
                                            latestBar.high if (insight.side == IOrderSide.BUY) else latestBar.low}, WON: ${round(insight.quantity*(insight.TP[0] - insight.limit_price), 2)}")
                                else:
                                    # Close 100% of the position
                                    closeOrder = self.submit_order(Insight(IOrderSide.BUY if (
                                        insight.side == IOrderSide.SELL) else IOrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                    except BaseException as e:
                        if e.args[0]["code"] == "insufficient_balance":
                            # '{"available":"0.119784","balance":"0.119784","code":40310000,"message":"insufficient balance for BTC (requested: 0.12, available: 0.119784)","symbol":"USD"}'
                            if e.args[0]["data"].get("balance") != None:
                                holding = float(e.args[0]["data"]["balance"])
                                if (holding > 0):
                                    # Close 100% of the position
                                    self.insights[insight.INSIGHT_ID].quantity = np.abs(
                                        holding)
                                else:
                                    self.insights[insight.INSIGHT_ID].updateState(
                                        InsightState.CANCELED, f"No funds to close position")

                    if (closeOrder):
                        self.insights[insight.INSIGHT_ID].close_order_id = closeOrder['order_id']

                return

            case InsightState.CLOSED:
                if (self.insights[insight.INSIGHT_ID].close_order_id == None):
                    self.insights[insight.INSIGHT_ID].updateState(InsightState.FILLED, f"Failed to close position {
                        insight.symbol} - {insight.side} - {insight.quantity} @ {insight.close_price} - UDA: {insight.updatedAt}")
                else:
                    del self.insights[insight.INSIGHT_ID]
                    # TODO: Save to DB?

            case InsightState.CANCELED:
                # Remove from insights if the insight is canceled
                try:
                    cancelOrder = self.broker.cancel_order(
                        order_id=insight.order_id)  # Cancel Order
                    if cancelOrder:
                        del self.insights[insight.INSIGHT_ID]
                except BaseException as e:
                    if e.args[0]["code"] == "already_filled":
                        # Order is already be canceled or filled
                        if (self.insights[insight.INSIGHT_ID].state == InsightState.FILLED):
                            # FIXME: best to get the order direcetly from the API to check if it is filled or not
                            self.insights[insight.INSIGHT_ID].updateState(
                                InsightState.FILLED, f"Already Filled")
                        else:
                            del self.insights[insight.INSIGHT_ID]
                return

            case InsightState.REJECTED:
                del self.insights[insight.INSIGHT_ID]
                return

            case InsightState.EXPIRED:
                # TODO: Make sure that the order is closed and the position is closed
                del self.insights[insight.INSIGHT_ID]
                return

            case _:
                return

    def teardown(self):
        # Close all open positions
        print("Tear Down")
        self.BROKER.close_all_positions()


if __name__ == "__main__":

    # Live broker
    # broker = AlpacaBroker(paper=True)
    # strategy = QbitTB(broker, variables={}, resolution=TimeFrame(
    #     1, TimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.LIVE)

    # Paper Broker for backtesting
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 5, 27), end_date=datetime(2024, 5, 28)) # 1 day
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 5, 27, 14), end_date=datetime(2024, 5, 27, 16)) # 2 hours
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 7, 1, 14), end_date=datetime(2024, 7, 30, 16))  # all of may
    strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
        4, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)

    # strategy.add_events('bar')
    # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
    strategy.add_events('bar', stored=True, stored_path='data', applyTA=True,
                        start=broker.START_DATE, end=broker.END_DATE)

    strategy.run()
