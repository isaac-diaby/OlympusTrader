import time
import pandas_ta as ta
import pandas as pd
from datetime import datetime, timedelta
from OlympusTrader.broker.interfaces import OrderSide
from OlympusTrader.broker.paper_broker import PaperBroker
from OlympusTrader.utils.insight import Insight, StrategyTypes, InsightState, StrategyDependantConfirmation
from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
from OlympusTrader.utils.interfaces import IStrategyMode
from OlympusTrader.utils.tools import dynamic_round
from OlympusTrader import AlpacaBroker, Strategy
import numpy as np

import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class QbitTB(Strategy):

    def start(self):
        state = self.state
        # Technical Indicators Params
        state["technical_indicators"] = {
            'IATR': {'period': 14},
            'IRSI': {'period': 14},
        }
        state['TaStrategy'] = ta.Strategy(
            name=f"TAVLM23",
            description="simple RSI OB/OS",
            ta=[
                {"kind": 'atr', "length": 14},
                {"kind": 'rsi', "length": 14, "scalar": 10},
            ]

        )
        state['warm_up'] = 14
        # 4% of account per trade
        state['execution_risk'] = 0.04
        # 2:1 Reward to Risk Ratio minimum
        state['RewardRiskRatio'] = 2.0
        state['baseConfidence'] = 0.1

    def init(self, asset):
        state = self.state
        # inital market state
        if (state.get('market_state') == None):
            state['market_state'] = {}
        state['market_state'][asset['symbol']] = 0

        # load warm up history
        if (state.get('history') == None):
            state['history'] = {}

        state['history'][asset['symbol']] = self.broker.get_history(
            asset, (datetime.now() - timedelta(minutes=125)), datetime.now(), self.resolution)

    def universe(self):
        universe = {'TSLA'}
        return universe

    def on_bar(self, symbol, bar):
        self.state['history'][symbol] = pd.concat(
            [self.state['history'][symbol],  bar])

        # Needs to be warm up
        if (len(self.state['history'][symbol]) < self.state['warm_up']):
            return
        # During back testing we need to update the history with the latest bar
        self.state['history'][symbol] = self.state['history'][symbol].loc[~self.state['history']
                                                                          [symbol].index.duplicated(keep='first')]

        self.state['history'][symbol].ta.strategy(self.state['TaStrategy'])

        # Compute Market State
        self.computeMarketState(symbol)

        # Execute Orders If there should be any
        self.generateInsights(symbol)  # self.insights[symbol]



    def computeMarketState(self, symbol: str):
        marketState = self.state['market_state'][symbol]
        history = self.state['history'][symbol]
        IRSI = history['RSI_14']

        marketState = 0
        if (IRSI.iloc[-1] < 30):
            marketState += 2
        elif (IRSI.iloc[-1] > 70):
            marketState -= 2

        # take no action if Market Has no Volume based on the Volume Quantile > 0.75
        if (history['volume'].iloc[-1] < round(history['volume'].quantile(0.75), 2)):
            marketState = 0
        else:
            if (marketState > 0):
                marketState += 1
            elif (marketState < 0):
                marketState -= 1
        marketState = np.minimum(np.maximum(marketState, -5), 5)
        self.state['market_state'][symbol] = marketState
        return marketState

    def generateInsights(self, symbol: str):
        history = self.state['history'][symbol].loc[symbol]
        latestBar = history.iloc[-1]
        previousBar = history.iloc[-2]
        latestIATR = latestBar['ATRr_14']
        marketState = self.state['market_state'][symbol]
        baseConfidence = self.state['baseConfidence']
        # marketState = -1

        # Do not trade if market state is 0
        if (marketState == 0):
            return

        # TEST
        # if (len(self.insights[symbol]) == 0):
        #     TP = self.tools.dynamic_round(
        #         (latestBar.close + (latestIATR*10)), symbol)
        #     SL = self.tools.dynamic_round(
        #         (latestBar.close - (latestIATR*1.5)), symbol)
        #     ENTRY = None
        #     # ENTRY = previousBar.high if (abs(
        #     #     previousBar.high - latestBar.close) < latestIATR) else dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
        #     self.add_insight(Insight(OrderSide.BUY, symbol,
        #                              StrategyTypes.TEST, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), 'HRVCM', 2, 3))

        # TODO: movethis into strategy tools
        def calculateTimeToLive(price, entry, ATR, additional=2):
            """Calculate the time to live for a given price and entry based on the ATR"""
            return ((np.abs(price - entry)) / ATR)+2

        if (latestBar['RSI_14'] < 30):
            # print(f"Insight - {symbol}: Long RSI: {latestBar['RSI_14']}")
            TP = self.tools.dynamic_round(
                (latestBar.close + (latestIATR*3.5)), symbol)
            SL = self.tools.dynamic_round(
                (latestBar.close - (latestIATR*1.5)), symbol)
            ENTRY = previousBar.high if (abs(
                previousBar.high - latestBar.close) < latestIATR) else self.tools.dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
            # time to live unfilled
            TTLUF = calculateTimeToLive(latestBar['close'], ENTRY, latestIATR)
            # time to live till take profit
            TTLF = calculateTimeToLive(TP, ENTRY, latestIATR)

            self.add_insight(Insight(OrderSide.BUY, symbol,
                                     StrategyTypes.RSI, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))

        if (latestBar['RSI_14'] > 70):
            # print(f"Insight - {symbol}: Short RSI: {latestBar['RSI_14']}")
            TP = self.tools.dynamic_round(
                (latestBar.close - (latestIATR*3.5)), symbol)
            SL = self.tools.dynamic_round(
                (latestBar.close + (latestIATR*1.5)), symbol)
            ENTRY = previousBar.low if (abs(
                previousBar.low - latestBar.close) < latestIATR) else self.tools.dynamic_round((latestBar.open-(.2*latestIATR)), symbol)
            # time to live unfilled
            TTLUF = calculateTimeToLive(latestBar['close'], ENTRY, latestIATR)
            # time to live till take profit
            TTLF = calculateTimeToLive(TP, ENTRY, latestIATR)
            self.add_insight(Insight(OrderSide.SELL, symbol,
                                     StrategyTypes.RSI, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))

        return

    def executeInsight(self, symbol: str):
        RISK = self.state['execution_risk']
        RewardRiskRatio = self.state['RewardRiskRatio']

        history = self.state['history'][symbol].loc[symbol]
        latestBar = history.iloc[-1]

        orders = self.orders
        for i, insight in enumerate(self.insights[symbol]):
            match insight.state:
                case InsightState.NEW:
                    try:
                        if (insight.hasExpired()):
                            self.insights[symbol][i].updateState(
                                InsightState.EXPIRED, f"Expired: Before Execution")
                            continue
                        # Not shortable
                        if (insight.side == OrderSide.SELL and not self.assets[symbol]['shortable']):
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Short not allowed")
                            continue

                        # Get price from latest bar if limit price is not set
                        self.insights[symbol][i].update_limit_price(self.state['history'][symbol].loc[symbol].iloc[-1].close if (
                            (insight.type == 'MARKET') or np.isnan(insight.limit_price)) else insight.limit_price)

                        RR = self.insights[symbol][i].getPnLRatio()

                        if RR < RewardRiskRatio:
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Low RR: {RR}")
                            continue

                        if (insight.quantity == None):

                            diluted_account_margin_size = self.account['buying_power'] * (
                                insight.confidence)
                            account_size_at_risk = self.account['cash'] * (
                                insight.confidence*RISK)

                            riskPerShare = abs(
                                self.insights[symbol][i].limit_price - insight.SL)
                            size_can_buy = (
                                diluted_account_margin_size)/self.insights[symbol][i].limit_price
                            size_should_buy = account_size_at_risk/riskPerShare
                            if (size_should_buy < 0):
                                self.insights[symbol][i].updateState(
                                    InsightState.REJECTED, f"Low funds at Risk: {account_size_at_risk:^10}")
                                continue

                            # np.round(diluted_account_size/price, 2)
                            self.insights[symbol][i].quantity = np.floor(
                                min(size_should_buy, size_can_buy)*1000)/1000

                            # continue
                            if (self.insights[symbol][i].quantity >= 1):
                                # Cant but fractional shares on limit orders with alpaca so round down
                                self.insights[symbol][i].quantity = np.floor(
                                    self.insights[symbol][i].quantity)
                            else:
                                pass
                                # self.insights[symbol][i].type = 'MARKET'

                            if self.insights[symbol][i].type == 'MARKET':
                                pass
                            else:
                                pass
                                # self.insights[symbol][i].updateState(InsightState.CANCELED)

                        # Print Insight Before Submitting Order
                        print(self.insights[symbol][i])

                        if (self.positions.get((insight.symbol)) != None):
                            # Check if there is a position open in the opposite direction
                            holding = self.positions[insight.symbol]
                            # Close position if holding is in the opposite direction of insight
                            if (holding != None or len(holding) != 0):
                                if (holding['side'] != insight.side):
                                    # Close all insighs in the opposite direction
                                    for x, otherInsight in enumerate(self.insights[symbol]):
                                        match otherInsight.state:
                                            case InsightState.FILLED:
                                                if (otherInsight.side != insight.side):
                                                    # Indecate that the market has changed
                                                    self.insights[symbol][x].marketChanged = True
                            else:
                                # TODO: Check if the holding is in the same direction as the new insight and if the insight is in profit, move the SL to break even.
                                pass

                                # self.close_position(
                                #     insight.symbol, holding['qty'])

                        order = self.submit_order(insight)

                        if order:
                            self.insights[symbol][i].updateOrderID(
                                order['order_id'])
                            self.insights[symbol][i].updateState(
                                InsightState.EXECUTED, f"Order ID: {order['order_id']}")
                        else:
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Failed to submit order")

                    except BaseException as e:
                        # print(f"Error: {e}")
                        self.insights[symbol][i].updateState(
                            InsightState.REJECTED, f"Error: {e}")
                        continue
                        # raise e

                case InsightState.EXECUTED:
                    print(f"Insight Executed: {str(insight)}")
                    # Check if filled or not or should be expired or not
                    self.insights[symbol][i].hasExpired(True)
                    # self.insights[symbol][i].updateState(
                    #     InsightState.CANCELED, f"Expired {symbol}: After Execution")

                case InsightState.FILLED:
                    print(insight)
                    shouldClosePosition = False
                    cause = None
                    # Check if the trade insight is exhausted and needs to be closed
                    if (self.insights[symbol][i].hasExhaustedTTL()):
                        shouldClosePosition = True
                        cause = "Exhausted TTL"

                    # Check if market has changed
                    if (insight.marketChanged):
                        shouldClosePosition = True
                        cause = "Market Changed"
                        # if (self.broker.close_position(insight.symbol, percent=100)):
                        #     self.insights[symbol][i].updateState(InsightState.CLOSED, f"Exhausted TTL")

                    # TODO: Since Alpaca does not support stop loss for crypto, we need to manage it manually
                    if ((insight.side == OrderSide.BUY) and (insight.SL > latestBar.low)) or ((insight.side == OrderSide.SELL) and (insight.SL < latestBar.high)):
                        shouldClosePosition = True
                        cause = "SL Hit"
                    # TODO: Take Profit if TP [0] is hit
                    if ((insight.side == OrderSide.BUY) and (insight.TP[0] < latestBar.high)) or ((insight.side == OrderSide.SELL) and (insight.TP[0] > latestBar.low)):
                        shouldClosePosition = True
                        cause = "TP Hit"

                    if (shouldClosePosition):
                        closeOrder = None
                        try:

                            # Send a Market order to close the position manually
                            match cause:
                                case "Exhausted TTL" | "SL Hit" | "Market Changed":
                                    closeOrder = self.submit_order(Insight(OrderSide.BUY if (
                                        insight.side == OrderSide.SELL) else OrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                                case "TP Hit":
                                    # If there is a TP 2 or 3, we need to close only a portion of the position, move the SL to break even and let the rest run until TP 2 or 3 is hit.
                                    if len(insight.TP) > 1:
                                        currentTP = self.insights[symbol][i].TP[0]
                                        # Close 80% of the position
                                        quantityToClose = dynamic_round(
                                            insight.quantity*0.8)
                                        closeOrder = self.submit_order(Insight(OrderSide.BUY if (
                                            insight.side == OrderSide.SELL) else OrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, quantityToClose))
                                        if closeOrder:
                                            # update remaining quantity
                                            self.insights[symbol][i].quantity = insight.quantity - \
                                                quantityToClose
                                            # Move SL to break even
                                            # TODO: update SL to break even
                                            self.insights[symbol][i].SL = insight.limit_price
                                            self.insights[symbol][i].TP.pop(0)
                                            # Reset TTL for the remaining position
                                            self.insights[symbol][i].updateState(InsightState.FILLED, f"Partial TP Hit: {insight.side:^8}: {insight.limit_price} -> {currentTP} -> {
                                                                                 latestBar.high if (insight.side == OrderSide.BUY) else latestBar.low}, WON: ${round(insight.quantity*(insight.TP[0] - insight.limit_price), 2)}")
                                    else:
                                        # Close 100% of the position
                                        closeOrder = self.submit_order(Insight(OrderSide.BUY if (
                                            insight.side == OrderSide.SELL) else OrderSide.SELL, insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                        except BaseException as e:
                            if e.args[0]["code"] == "insufficient_balance":
                                # '{"available":"0.119784","balance":"0.119784","code":40310000,"message":"insufficient balance for BTC (requested: 0.12, available: 0.119784)","symbol":"USD"}'
                                holding = float(e.args[0]["data"]["balance"])
                                if (holding > 0):
                                    # Close 100% of the position
                                    self.insights[symbol][i].quantity = np.abs(
                                        holding)
                                else:
                                    self.insights[symbol][i].updateState(
                                        InsightState.CANCELED, f"No funds to close position")

                        if (closeOrder):
                            self.insights[symbol][i].close_order_id = closeOrder['order_id']

                    continue
                case InsightState.CLOSED:

                    print(insight)
                    if (self.insights[symbol][i].close_order_id == None):
                        self.insights[symbol][i].updateState(InsightState.FILLED, f"Failed to close position {
                                                             symbol} - {insight.side} - {insight.quantity} @ {insight.close_price} - UDA: {insight.updatedAt}")
                    else:
                        del self.insights[symbol][i]
                      # TODO: Save to DB?

                case InsightState.CANCELED:
                    # Remove from insights if the insight is canceled
                    print(insight)
                    try:
                        cancelOrder = self.broker.close_order(
                            order_id=insight.order_id)  # Cancel Order

                        del self.insights[symbol][i]
                    except BaseException as e:
                        if e.args[0]["code"] == "already_filled":
                            # Order is already be canceled or filled
                            if (self.insights[symbol][i].state == InsightState.FILLED):
                                # FIXME: best to get the order direcetly from the API to check if it is filled or not
                                self.insights[symbol][i].updateState(
                                    InsightState.FILLED, f"Already Filled")
                            else:
                                del self.insights[symbol][i]
                    continue

                case InsightState.REJECTED:
                    print(insight)
                    del self.insights[symbol][i]
                    continue

                case InsightState.EXPIRED:
                    print(insight)
                    # TODO: Make sure that the order is closed and the position is closed
                    del self.insights[symbol][i]
                    continue

                case _:
                    continue

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
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 5, 27), end_date=datetime(2024, 5, 28))
    strategy = QbitTB(broker, variables={}, resolution=TimeFrame(
        1, TimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)

    strategy.add_events('bar')

    strategy.run()
