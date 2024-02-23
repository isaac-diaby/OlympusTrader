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

        # load warm up history
        if (state.get('history') == None):
            state['history'] = {}

        state['history'][asset['symbol']] = self.broker.get_history(
            asset, (datetime.now() - timedelta(days=3)), datetime.now(), self.resolution)

        self.addBar_events(asset)

    def universe(self):
        # universe = { }
        # universe = {'BTC/USD', 'ETH/USD' }
        universe = {'TSLA', 'AAPL', 'JPM', 'MSFT',
                    'SPY', 'NDAQ', 'IHG', 'NVDA', 'TRIP'}
        # universe = {'TSLA', 'AAPL', 'JPM', 'MSFT',
        #             'SPY', 'NDAQ', 'IHG', 'TRIP', 'BTC/USD', 'ETH/USD'}
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
            if (len(self.insights[symbol]) > 0):
                self.executeOrder(symbol)
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
        insights = self.insights[symbol] = []
        baseConfidence = 0.1
        # marketState = -1

        # Do not trade if market state is 0
        if (marketState == 0):
            return

        # TEST
        # if (len(self.insights[symbol]) == 0):
        #     TP = round((latestBar.close + (latestIATR*3)), 2)
        #     SL = round((latestBar.close - (latestIATR*1.5)), 2)
        #     ENTRY = previousBar.high if (abs(
        #         previousBar.high - latestBar.close) < latestIATR) else round((latestBar.open+(.2*latestIATR)), 2)
        #     self.insights[symbol].append(Insight('long', symbol,
        #                                          StrategyTypes.RSI_DIVERGANCE, self.resolution, None, ENTRY, [TP], SL, baseConfidence*abs(marketState), 'LRVCM'))

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

    def executeOrder(self, symbol: str):
        RISK = self.state['execution_risk']
        RewardRiskRatio = self.state['RewardRiskRatio']

        orders = self.orders
        for i, insight in enumerate(self.insights[symbol]):
            match insight.state:
                case InsightState.NEW:
                    try:
                        if (insight.hasExpired()):
                            continue

                        price = self.state['history'][symbol].loc[symbol].iloc[-1].close if (
                            (insight.type == 'MARKET') or np.isnan(insight.limit_price)) else insight.limit_price

                        # Get current holding
                        if (self.positions.get((insight.symbol).replace('/', '')) != None):
                            holding = self.positions[(
                                insight.symbol).replace('/', '')]
                            # Close position if holding is in the opposite direction of insight
                            if (len(holding) != 0):
                                if (holding['side'] == 'long' and insight.side == 'short'):
                                    self.close_position(
                                        insight.symbol, holding['qty'])
                                elif (holding['side'] == 'short' and insight.side == 'long'):
                                    self.close_position(
                                        insight.symbol, holding['qty'])

                        RR = insight.getPnLRatio(price)
                        if RR < RewardRiskRatio:
                            self.insights[symbol][i].updateState(
                                InsightState.REJECTED, f"Low RR: {RR}")
                            continue
                        #             insight.symbol, 'buy', abs(holding.available))
                        # calculate number of shares from cash according to risk of 2 percent

                        if (insight.quantity == None):
                            diluted_account_margin_size = self.account['buying_power'] * \
                                insight.confidence
                            account_size_at_risk = self.account['cash'] * \
                                insight.confidence*RISK
                            riskPerShare = abs(price - insight.SL)
                            size_can_buy = (diluted_account_margin_size)/price
                            size_should_buy = account_size_at_risk/riskPerShare
                            if (size_should_buy < 0):
                                self.insights[symbol][i].updateState(
                                    InsightState.CANCELED, f"Low funds at Risk: {account_size_at_risk:^10}")
                                continue

                            # np.round(diluted_account_size/price, 2)
                            size = math.floor(
                                min(size_should_buy, size_can_buy)*1000)/1000

                            # continue
                            if (size >= 1):
                                # Cant but fractional shares on limit orders with alpaca so round down
                                size = math.floor(size)
                            else:
                                self.insights[symbol][i].type = 'MARKET'

                            if insight.type == 'MARKET':
                                pass
                            else:
                                pass
                                # self.insights[symbol][i].updateState(InsightState.CANCELED)

                            self.insights[symbol][i].quantity = size

                        print(
                            f"{insight.side}: {insight.symbol} at {price} with {size} shares, SL: {insight.SL} TP: {insight.TP} Ratio: {RR}, Stratey: {insight.strategyType}")

                        order = self.submit_order(insight)

                        if order:
                            self.insights[symbol][i].updateOrderID(
                                order['order_id'])
                            self.insights[symbol][i].updateState(
                                InsightState.EXECUTED, f"Order ID: {order['order_id']}")
                        else:
                            self.insights[symbol][i].updateState(
                                InsightState.CANCELED, f"Failed to submit order")

                    except Exception as e:
                        # print(f"Error: {e}")
                        self.insights[symbol][i].updateState(
                            InsightState.CANCELED, f"Error: {e}")
                        raise e
                case InsightState.EXECUTED:
                    # TODO: Check if filled or not or should be expired or not
                    if (self.insights[symbol][i].hasExpired()):
                        continue

                case InsightState.FILLED:
                    print(f"Insight Filled: {insight}")
                    # TODO: Check if the trade insight is exhausted
                    # TODO: check if the trade needs to lower risk by moving stop loss
                    pass
                case InsightState.CLOSED:
                    pass
                case InsightState.CANCELED:
                    # Remove from insights if the insight is canceled
                    print(f"Insight Canceled: {insight}")
                    # TODO: Save to DB?
                    del self.insights[symbol][i]

                case InsightState.REJECTED:
                    print(f"Insight Rejected: {insight}")
                    del self.insights[symbol][i]

                case InsightState.EXPIRED:
                    print(f"Insight Expired: {insight}")
                    del self.insights[symbol][i]

                case _:
                    pass

    def teardown(self):
        # Close all open positions
        # self.BROKER.close_all_positions()
        print("Tear Down")
        pass


if __name__ == "__main__":
    broker = AlpacaBroker(paper=True)
    strategy = QbitTB(broker, {}, resolution=TimeFrame(
        1, TimeFrameUnit.Minute))
    # strategy = QbitTB(broker, resolution=TimeFrame(5, TimeFrameUnit.Minute))

    strategy.run()

    # print(strategy.assets)
    # print(strategy.state['history'])
