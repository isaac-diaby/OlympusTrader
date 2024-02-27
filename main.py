import pandas_ta as ta
import pandas as pd
from datetime import datetime, timedelta
from OlympusTrader.utils.insight import Insight, StrategyTypes, InsightState, StrategyDependantConfirmation
from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
from OlympusTrader import AlpacaBroker, Strategy
import math
import numpy as np
import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class QbitTB(Strategy):

    def init(self, asset):
        state = self.state
        # Technical Indicators Params
        state["technical_indicators"] = {
            'IATR': {'period': 14},
            'IRSI': {'period': 14},
            'IMACD': {'short_period': 16, 'long_period': 32, 'signal_period': 9},
            'IVWMA': None,
            'ISMA': None,
            'IEMA': None,
            'IBBANDS': None,
            'IVP': None,
            'IPVO': None,
        }
        state['warm_up'] = 200
        # set window sizes
        state['local_window'] = 1
        state['divergance_window'] = 50
        # inital market state
        if (state.get('market_state') == None):
            state['market_state'] = {}
        state['market_state'][asset['symbol']] = 0
        # 4% of account per trade
        state['execution_risk'] = 0.04
        # 2:1 Reward to Risk Ratio minimum
        state['RewardRiskRatio'] = 2.0
        state['baseConfidence'] = 0.1

        # load warm up history
        if (state.get('history') == None):
            state['history'] = {}

        state['history'][asset['symbol']] = self.broker.get_history(
            asset, (datetime.now() - timedelta(days=3)), datetime.now(), self.resolution)

        self.addBar_events(asset)

    def universe(self):
        # universe = { }

        # universe = {'BTC/USD', 'ETH/USD', 'LINK/USD' }

        # universe = {'TSLA', 'AAPL', 'JPM', 'MSFT', 'SPY', 'NDAQ', 'IHG', 'NVDA', 'TRIP'}

        universe = {'TSLA', 'AAPL', 'JPM', 'MSFT', 'SPY', 'NDAQ',
                    'IHG', 'NVDA', 'TRIP', 'BTC/USD', 'ETH/USD', 'LINK/USD'}

        return universe

    def on_bar(self, symbol, bar):
        self.state['history'][symbol] = pd.concat(
            [self.state['history'][symbol],  bar])

        # Needs to be warm up
        if (len(self.state['history'][symbol]) < self.state['warm_up']):
            return
        # print(f'Bar: {bar}')
        # Technical Indicators Config params
        TaConfig = self.state["technical_indicators"]
        # Compute Technical Indicators
        TaStrategy = ta.Strategy(
            name=f"TAVLM23-{symbol}",
            description="Using TA, Volume/Momentum Spikes and Dominating Price action to place low risk positions from extened price movement.",
            ta=[
                {"kind": 'atr', "length": 14},  # , "col_names": ('IATR',)},
                # , "col_names": ('IMACD', 'IMACDh', 'IMACDs')},
                {"kind": 'macd', "fast": 16, "slow": 36, "signal": 9},
                {"kind": 'vwma', "length": 20},  # "col_name": ('IVWMA',)},
                # {"kind": 'vwap', "length": 20, "col_name": ('IVWAP',)},
                # , "col_names": ('IBASELINE',)},
                {"kind": 'sma', "length": 200},
                # , "col_names": ('IBBL', 'IBBM', 'IBBU', 'IBBB', 'IBBP')},
                {"kind": 'bbands', "length": 16, "std": 2},
                {"kind": 'ema', "length": 9},  # , "col_names": ('IEMA',)},
                # , "col_name": ('IRSI',)},
                {"kind": 'rsi', "length": 14, "scalar": 10},
                {"kind": 'mfi', "length": 14},  # , "col_names": ('IMFI',)},
                # , "col_names": ('IPVO', 'IPVOh', 'IPVOs')},
                {"kind": 'pvo', "fast": 9, "slow": 50, "signal": 9},
                {"kind": 'vp', "width": 14},  # , "col_names": ('IVP',)},
                # , "col_names": ('IVOL',)},
                {'kind': 'sma', 'close': 'volume', 'length': 32},
            ]

        )

        # self.state['history'][symbol] =
        self.state['history'][symbol].ta.strategy(TaStrategy)
        # print(f"History: {self.state['history'][symbol]}")

        # print(f"History: {self.state['history'][symbol].tail(3)}")
        # print("History",  self.state['history'].loc[[symbol]].columns)
        # History Index(['close', 'high', 'low', 'open', 'volume', 'ATRr_14', 'MACD_16_36_9',
        #     'MACDh_16_36_9', 'MACDs_16_36_9', 'VWMA_20', 'SMA_200', 'BBL_16_2.0',
        #     'BBM_16_2.0', 'BBU_16_2.0', 'BBB_16_2.0', 'BBP_16_2.0', 'EMA_9',
        #     'RSI_14', 'MFI_14', 'PVO_9_50_9', 'PVOh_9_50_9', 'PVOs_9_50_9',
        #     'low_close', 'mean_close', 'high_close', 'pos_volume', 'neg_volume',
        #     'total_volume', 'SMA_32'],
        #     dtype='object')

        try:
            # Compute Local Points of Control
            self.computeLocalPointsOfControl(symbol)
            # Compute RSI Divergance
            self.computeRSIDivergance(symbol)
            # Compute Market State
            self.computeMarketState(symbol)

            # Execute Orders If there should be any
            self.generateInsights(symbol)  # self.insights[symbol]
        except Exception as e:
            print(f"Error: {e}")
            raise e

    def computeLocalPointsOfControl(self, symbol: str):
        window = self.state['local_window']
        history = self.state['history'][symbol]
        viewColumn = 'close'
        history.loc[[symbol], ['local_max_poc']] = history[viewColumn][(
            history[viewColumn].shift(window) < history[viewColumn]) & (history[viewColumn].shift(-window) < history[viewColumn]
                                                                        )]
        history.loc[[symbol], ['local_min_poc']] = history[viewColumn][(
            history[viewColumn].shift(window) > history[viewColumn]) & (history[viewColumn].shift(-window) > history[viewColumn]
                                                                        )]
        return history

    def computeRSIDivergance(self, symbol: str):
        window = self.state['divergance_window']
        # remove first 14 rows for RSI Warmup
        history = self.state['history'][symbol]
        IRSI = history['RSI_14']

        # Long Divergance - RSI is Increasing while price is Decreasing
        self.state['history'][symbol].loc[:, 'RSI_Divergance_Long'] = np.nan
        # only use local lows of point of control for reversal
        longPivot = history['local_min_poc'].dropna()
        lowerLowsPivots = longPivot.loc[longPivot.shift(1) > longPivot]

        for index, price in lowerLowsPivots[-1:-window:-1].items():
            _, *previousLocalPoC = longPivot.loc[index: (index[0], index[1]-timedelta(
                minutes=self.state['divergance_window'])): -1].items()
            if (len(previousLocalPoC) == 0):
                continue
            lastLowIndex, lastPrice = previousLocalPoC[0]
            if (IRSI.loc[lastLowIndex] < IRSI.loc[index]):
                #    print(f"Long Divergance PIVOT at Index: {index} - From Index: {lastLowIndex}: {lastPrice:10} -> {price} - From RSI: {IRSI.iloc[lastLowIndex-IRSI_period]} -> {IRSI.iloc[index-IRSI_period]:10}")
                # the difference between the two points of control / the price difference for ATR use
                self.state['history'][symbol].loc[index, [
                    'RSI_Divergance_Long']] = lastPrice-price

        # Bearish divergence - RSI is Decreasing while price is Increasing
        self.state['history'][symbol].loc[:, 'RSI_Divergance_Short'] = np.nan
        # only use local maximas of point of control for reversal
        shortPivot = history['local_max_poc'].dropna()
        higherHighsPivots = shortPivot.loc[shortPivot.shift(1) < shortPivot]

        for index, price in higherHighsPivots[-1:-window:-1].items():
            _, *previousLocalPoC = shortPivot.loc[index: (index[0], index[1]-timedelta(
                minutes=self.state['divergance_window'])): -1].items()
            if (len(previousLocalPoC) == 0):
                continue
            lastHighIndex, lastPrice = previousLocalPoC[0]
            if (IRSI.loc[lastHighIndex] > IRSI.loc[index]):
                # print(f"Short Divergance PIVOT at Index: {index} - From Index: {lastHighIndex}: {lastPrice:10} -> {price} - From RSI: {IRSI.iloc[lastHighIndex-IRSI_period]} -> {IRSI.iloc[index-IRSI_period]:10}")
                self.state['history'][symbol].loc[index, [
                    'RSI_Divergance_Short']] = price-lastPrice

        return history

    def computeMarketState(self, symbol: str):
        marketState = self.state['market_state'][symbol]
        history = self.state['history'][symbol]
        IMACD = history[['MACD_16_36_9', 'MACDh_16_36_9', 'MACDs_16_36_9']]
        IRSI = history['RSI_14']
        # print(f"MACD: {IMACD.iloc[-1]}, {IMACD.iloc[-1, 0]}, {IMACD.iloc[-1, 1]}, {IMACD.iloc[-1, 2]}")
        # print(f"RSI: {IRSI.iloc[-1]}")
        marketState = 0
        if ((IMACD.iloc[-1, 0] > 0)):  # MACD value and  # MACD histogram are both positive
            marketState += 3
        elif ((IMACD.iloc[-1, 0] < 0)):  # MACD value and  # MACD histogram are both positive
            marketState -= 3
        # if ((IMACD.iloc[-1, 0] > 0) and (IMACD.iloc[-1, 2] < 0)):  # MACD value and  # MACD histogram are both positive
        #     marketState += 3
        # elif ((IMACD.iloc[-1, 0] < 0) and (IMACD.iloc[-1, 2] > 0)): # MACD value and  # MACD histogram are both positive
        #     marketState -= 3
        if (IRSI.iloc[-1] < 30):
            marketState += 2
        elif (IRSI.iloc[-1] > 70):
            marketState -= 2

        # take no action if Market Has no Volume based on the Volume Quantile > 0.7
        if (history['volume'].iloc[-1] < round(history['volume'].quantile(0.7), 2)):
            marketState = 0

        # print(f"{symbol} Market State: {marketState}, MACD: {IMACD.iloc[-1, 0]}, RSI: {IRSI.iloc[-1]}")
        marketState = min(max(marketState, -5), 5)
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
        #     TP = round((latestBar.close + (latestIATR*20)), 2)
        #     SL = round((latestBar.close - (latestIATR*1.5)), 2)
        #     ENTRY = None
        #     # ENTRY = previousBar.high if (abs(
        #     #     previousBar.high - latestBar.close) < latestIATR) else round((latestBar.open+(.2*latestIATR)), 2)
        #     self.insights[symbol].append(Insight('long', symbol,
        #                                          StrategyTypes.TEST, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), 'HRVCM', 2, 3))

        # RSA Divergance Long
        if (not np.isnan(latestBar['RSI_Divergance_Long']) and marketState < 0):
            # print(f"Insight - {symbol}: Long Divergance: {latestBar['RSI_Divergance_Long']}")
            TP = round((latestBar.close + (latestIATR*3.5)), 2)
            SL = round((latestBar.close - (latestIATR*1.5)), 2)
            ENTRY = previousBar.high if (abs(
                previousBar.high - latestBar.close) < latestIATR) else round((latestBar.open+(.2*latestIATR)), 2)

            self.insights[symbol].append(Insight('long', symbol,
                                                 StrategyTypes.RSI_DIVERGANCE, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM]))
        # RSA Divergance Short
        if (not np.isnan(latestBar['RSI_Divergance_Short']) and marketState > 0):
            # print(f"Insight - {symbol}: Short Divergance: {latestBar['RSI_Divergance_Short']}")
            TP = round((latestBar.close - (latestIATR*3.5)), 2)
            SL = round((latestBar.close + (latestIATR*1.5)), 2)
            ENTRY = previousBar.low if (abs(
                previousBar.low - latestBar.close) < latestIATR) else round((latestBar.open+(.2*latestIATR)), 2)

            self.insights[symbol].append(Insight('short', symbol,
                                                 StrategyTypes.RSI_DIVERGANCE, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.LRVCM]))

        # EMA Crossover Long
        if ((latestBar['EMA_9'] < latestBar['close']) and (latestBar['EMA_9'] > previousBar['close']) and (abs(latestBar['EMA_9'] - latestBar['close']) < latestBar['ATRr_14']) and marketState > 2):
            # print(
            #     f"Insight - {symbol}: Long EMA Crossover: EMA:{latestBar['EMA_9']} < {latestBar['close']}")
            TP = round(max(latestBar['BBU_16_2.0'],
                       (latestBar['high']+(latestIATR*3.5))), 2)
            SL = round(
                max(previousBar['low']-(.2*latestIATR), latestBar['EMA_9']-latestIATR*1.5), 2)
            ENTRY = None  # TODO: ADD Price instead of  Market Order

            self.insights[symbol].append(Insight('long', symbol,
                                                 StrategyTypes.EMA_CROSSOVER, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.HRVCM]))
        # EMA Crossover Short
        if ((latestBar['EMA_9'] > latestBar['close']) and (latestBar['EMA_9'] < previousBar['close']) and (abs(latestBar['close'] - latestBar['EMA_9']) < latestBar['ATRr_14']) and marketState < -2):
            # print(
            #     f"Insight - {symbol}: Short EMA Crossover: EMA:{latestBar['EMA_9']} > {latestBar['close']}")
            TP = round(min(latestBar['BBL_16_2.0'],
                       (latestBar['low']-(latestIATR*3.5))), 2)
            SL = round(min(previousBar['high'] +
                       (.2*latestIATR),  latestBar['EMA_9']+latestIATR*1.5), 2)
            ENTRY = None  # TODO: ADD Price instead of  Market Order

            self.insights[symbol].append(Insight('short', symbol,
                                                 StrategyTypes.EMA_CROSSOVER, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), [StrategyDependantConfirmation.HRVCM]))

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

                        self.insights[symbol][i].limit_price = self.state['history'][symbol].loc[symbol].iloc[-1].close if (
                            (insight.type == 'MARKET') or np.isnan(insight.limit_price)) else insight.limit_price

                        # Get current holding
                        if (self.positions.get((insight.symbol).replace('/', '')) != None):
                            holding = self.positions[(
                                insight.symbol).replace('/', '')]
                            # Close position if holding is in the opposite direction of insight
                            if (len(holding) != 0):
                                if (holding['side'] != insight.side):
                                    self.close_position(
                                        insight.symbol, holding['qty'])

                        RR = self.insights[symbol][i].getPnLRatio()
                        if RR < RewardRiskRatio:
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Low RR: {RR}")
                            continue
                        #             insight.symbol, 'buy', abs(holding.available))
                        # calculate number of shares from cash according to risk of 2 percent

                        if (insight.quantity == None):
                            if (self.assets[symbol]['asset_type'] == 'stock'):
                                diluted_account_margin_size = self.account['buying_power'] * \
                                    insight.confidence
                                account_size_at_risk = self.account['cash'] * (
                                    insight.confidence*RISK)
                            if (self.assets[symbol]['asset_type'] == 'crypto'):
                                diluted_account_margin_size = self.account['cash'] * (
                                    insight.confidence)
                                account_size_at_risk = self.account['cash'] * (
                                    insight.confidence*RISK)

                            if (diluted_account_margin_size > 200000):
                                # Max 200k per trade Alapaca
                                diluted_account_margin_size = 200000

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
                            self.insights[symbol][i].quantity = math.floor(
                                min(size_should_buy, size_can_buy)*1000)/1000

                            # continue
                            if (self.insights[symbol][i].quantity >= 1):
                                # Cant but fractional shares on limit orders with alpaca so round down
                                self.insights[symbol][i].quantity = math.floor(
                                    self.insights[symbol][i].quantity)
                            else:
                                self.insights[symbol][i].type = 'MARKET'

                            if self.insights[symbol][i].type == 'MARKET':
                                pass
                            else:
                                pass
                                # self.insights[symbol][i].updateState(InsightState.CANCELED)

                        # Print Insight Before Submitting Order
                        print(self.insights[symbol][i])

                        order = self.submit_order(insight)

                        if order:
                            self.insights[symbol][i].updateOrderID(
                                order['order_id'])
                            self.insights[symbol][i].updateState(
                                InsightState.EXECUTED, f"Order ID: {order['order_id']}")
                        else:
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Failed to submit order")

                    except Exception as e:
                        # print(f"Error: {e}")
                        self.insights[symbol][i].updateState(
                            InsightState.REJECTED, f"Error: {e}")
                        raise e
                case InsightState.EXECUTED:
                    print(f"Insight Executed: {str(insight)}")
                    # Check if filled or not or should be expired or not
                    if (self.insights[symbol][i].hasExpired(True)):
                        pass
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
                        # if (self.broker.close_position(insight.symbol, percent=100)):
                        #     self.insights[symbol][i].updateState(InsightState.CLOSED, f"Exhausted TTL")

                    # TODO: Since Alpaca does not support stop loss for crypto, we need to manage it manually
                    if ((insight.side == 'long') and (insight.SL > latestBar.low)) or ((insight.side == 'short') and (insight.SL < latestBar.high)):
                        shouldClosePosition = True
                        cause = "SL Hit"
                    # TODO: Take Profit if TP [0] is hit
                    if ((insight.side == 'long') and (insight.TP[0] < latestBar.high)) or ((insight.side == 'short') and (insight.TP[0] > latestBar.low)):
                        shouldClosePosition = True
                        cause = "TP Hit"

                    if (shouldClosePosition):
                        # Send a Market order to close the position manually
                        match cause:
                            case "Exhausted TTL" | "SL Hit":
                                closeOrder = self.submit_order(Insight('long' if (
                                    insight.side == 'short') else 'short', insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                            case "TP Hit":
                                # If there is a TP 2 or 3, we need to close only a portion of the position, move the SL to break even and let the rest run until TP 2 or 3 is hit.
                                if len(insight.TP) > 1:
                                    currentTP = self.insights[symbol][i].TP[0]
                                    # Close 80% of the position
                                    quantityToClose = round(
                                        insight.quantity*0.8, 2)
                                    closeOrder = self.submit_order(Insight('long' if (
                                        insight.side == 'short') else 'short', insight.symbol, StrategyTypes.MANUAL, self.resolution, quantityToClose))
                                    if closeOrder:
                                        # update remaining quantity
                                        self.insights[symbol][i].quantity = insight.quantity - \
                                            quantityToClose
                                        # Move SL to break even
                                        self.insights[symbol][i].SL = insight.limit_price
                                        self.insights[symbol][i].TP.pop(0)
                                        # Reset TTL for the remaining position
                                        self.insights[symbol][i].updateState(InsightState.FILLED, f"Partial TP Hit: {insight.side:^8}: {insight.limit_price} -> {currentTP} -> {latestBar.high if (insight.side == 'long') else latestBar.low}, WON: ${round(insight.quantity*(insight.TP[0] - insight.limit_price), 2)}")
                                else:
                                    # Close 100% of the position
                                    closeOrder = self.submit_order(Insight('long' if (insight.side == 'short') else 'short', insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))
                        if (closeOrder):
                            self.insights[symbol][i].close_order_id = closeOrder['order_id']
                        # match self.assets[symbol]['asset_type']:
                        #     case 'stock':
                        #         closeOrder = self.broker.close_position(insight.symbol, qty=insight.quantity)
                        #     case 'crypto':
                        #         # Send a Market order to close the position manually
                        #         closeOrder = self.submit_order(Insight('long' if (insight.side == 'short') else 'short', insight.symbol, StrategyTypes.MANUAL, self.resolution, insight.quantity))

                        # if (closeOrder):
                        #     self.insights[symbol][i].updateState(InsightState.CLOSED, f"{cause}: {insight.side:^8}: {insight.limit_price} -> {insight.TP[0]} -> {latestBar.high  if (insight.side == 'long') else latestBar.low}, WON: ${insight.quantity*(insight.TP[0] - insight.limit_price)}")

                    # TODO: check if the trade needs to lower risk by moving stop loss
                    pass
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
                    cancelOrder = self.broker.close_order(
                        order_id=insight.order_id)  # Cancel Order
                    if cancelOrder:
                        del self.insights[symbol][i]

                case InsightState.REJECTED:
                    print(insight)
                    del self.insights[symbol][i]

                case InsightState.EXPIRED:
                    print(insight)
                    # TODO: Make sure that the order is closed and the position is closed
                    del self.insights[symbol][i]

                case _:
                    pass

    def teardown(self):
        # Close all open positions
        print("Tear Down")
        self.BROKER.close_all_positions()
        pass


if __name__ == "__main__":
    broker = AlpacaBroker(paper=True)
    strategy = QbitTB(broker, {}, resolution=TimeFrame(
        1, TimeFrameUnit.Minute))
    # strategy = QbitTB(broker, resolution=TimeFrame(5, TimeFrameUnit.Minute))

    strategy.run()

    # print(strategy.assets)
    # print(strategy.state['history'])
