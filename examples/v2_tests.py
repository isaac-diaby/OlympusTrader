from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from OlympusTrader.broker.interfaces import IOrderSide, ITradeUpdateEvent
from OlympusTrader.broker.paper_broker import PaperBroker
from OlympusTrader.strategy.strategy import Strategy
from OlympusTrader.insight.insight import Insight, InsightState, StrategyTypes
from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit
from OlympusTrader.utils.tools import dynamic_round

from OlympusTrader.alpha.rsi_divergance_alpha import RSIDiverganceAlpha
from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha
from OlympusTrader.alpha.test_entry import TestEntryAlpha

from OlympusTrader.insight.executors.filled.basicStopLoss import BasicStopLossExecutor
from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
from OlympusTrader.insight.executors.filled.closeExhaustedInsight import CloseExhaustedInsightExecutor
from OlympusTrader.insight.executors.filled.closeMarketChanged import CloseMarketChangedExecutor
from OlympusTrader.insight.executors.new.cancelAllOppositeSide import CancelAllOppositeSidetExecutor
from OlympusTrader.insight.executors.new.dynamicQuantityToRisk import DynamicQuantityToRiskExecutor
from OlympusTrader.insight.executors.new.marketOrderEntryPrice import MarketOrderEntryPriceExecutor
from OlympusTrader.insight.executors.new.minimumRiskToReward import MinimumRiskToRewardExecutor
from OlympusTrader.insight.executors.new.rejectExpiredInsight import RejectExpiredInsightExecutor
from OlympusTrader.insight.executors.canceled.defaultOnCancelled import DefaultOnCancelledExecutor
from OlympusTrader.insight.executors.rejected.defaultOnReject import DefaultOnRejectExecutor
from OlympusTrader.insight.executors.closed.defaultOnClosed import DefaultOnClosedExecutor


class V2_test(Strategy):
    def start(self):
        self.add_ta([
            {"kind": 'macd', "fast": 16, "slow": 36, "signal": 9},
            {"kind": 'atr', "length": 14},
            {"kind": 'rsi', "length": 14, "scalar": 10}
            ])
        self.warm_up = 36
        self.execution_risk = 0.08  # 4% of account per trade
        self.minRewardRiskRatio = 2.0  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.67

        # Alphas
        self.add_alphas([
        RSIDiverganceAlpha(self, local_window=36, divergance_window=50, atrPeriod=14, rsiPeriod=14, baseConfidenceModifierField='market_state'),
        EMAPriceCrossoverAlpha(self, atrPeriod=14, emaPeriod=9, baseConfidenceModifierField='market_state'),
        # TestEntryAlpha(self, atrPeriod=14)
    ])
        # New Executors
        self.add_executors([
            RejectExpiredInsightExecutor(self),
            MarketOrderEntryPriceExecutor(self),
            # MinimumRiskToRewardExecutor(self, self.minRewardRiskRatio),
            DynamicQuantityToRiskExecutor(self),
            CancelAllOppositeSidetExecutor(self)
        ])
        # Executed Executors
        RejectExpiredExecutedExecutor = RejectExpiredInsightExecutor(self)
        RejectExpiredExecutedExecutor._override_state(InsightState.EXECUTED)
        self.add_executors([
            RejectExpiredExecutedExecutor,
        ])
        # Cancelled Executors
        self.add_executors([
            DefaultOnCancelledExecutor(self),
        ])
        # Filled Executors
        self.add_executors([
            CloseExhaustedInsightExecutor(self),
            CloseMarketChangedExecutor(self),
            BasicStopLossExecutor(self),
            BasicTakeProfitExecutor(self)
        ])
        # Closed Executors
        self.add_executors([
            DefaultOnClosedExecutor(self),
        ])
        # Rejected Executors
        self.add_executors([
            DefaultOnRejectExecutor(self)
        ])


    def init(self, asset):
        state = self.state

        # inital market state
        if (state.get('market_state') == None):
            state['market_state'] = {}
        state['market_state'][asset['symbol']] = 0

        # load warm up history

        self.history[asset['symbol']] = pd.concat([self.history[asset['symbol']], self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(),  self.warm_up*-3), datetime.now(), self.resolution)])

    def universe(self):
        # universe = {'aapl', 'goog', 'amzn', 'msft', 'tsla'}
        universe = {'btc-usd'}
        # universe = {'btc-usd','eth-usd'}
        return universe

    def on_bar(self, symbol, bar):
        self.computeMarketState(symbol)
        pass

    def generateInsights(self, symbol: str):
        pass
 
    def computeMarketState(self, symbol: str):
        marketState = self.state['market_state'][symbol]
        history = self.history[symbol]
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

        # take no action if Market Has no Volume based on the Volume Quantile > 0.75
        # if (history['volume'].iloc[-1] < round(history['volume'].quantile(0.75), 2)):
        #     marketState = 0

        if (marketState > 0):
            marketState += 1
        elif (marketState < 0):
            marketState -= 1

        # print(f"{symbol} Market State: {marketState}, MACD: {IMACD.iloc[-1, 0]}, RSI: {IRSI.iloc[-1]}")
        marketState = min(max(marketState, -5), 5)
        self.state['market_state'][symbol] = marketState
        return marketState

    def executeInsight(self, insight: Insight):
        match insight.state:
            case InsightState.NEW:
                try:
                    self.insights[insight.INSIGHT_ID].submit()
                except BaseException as e:
                    # print(f"Error: {e}")
                    self.insights[insight.INSIGHT_ID].updateState(
                        InsightState.REJECTED, f"Error: {e}")
                    return
            # case InsightState.EXECUTED:
            #     return
            # case InsightState.FILLED:
            #     # TODO: check if the trade needs to lower risk by moving stop loss
            #     return
            # case InsightState.CLOSED:
            #     return
            # case InsightState.CANCELED:
            #     return
            # case InsightState.REJECTED:
            #     return
            # case _:
            #     return


if __name__ == "__main__":

    # Paper Broker for backtesting
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #         2024, 7, 1), end_date=datetime(2024, 8, 23))
    
    broker = PaperBroker(cash=100_000, start_date=datetime(
            2024, 8, 16), end_date=datetime(2024, 8, 23), verbose=1, leverage=1.0)
    
    # Strategy
    # 1 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    # 5 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    # 1 Hour
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    strategy = V2_test(broker, variables={}, resolution=ITimeFrame(
        5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)

    
    # live paper trading on the paper broker 
    # broker = PaperBroker(cash=1_000_000, mode=IStrategyMode.LIVE, feedDelay=60*8) # 8 hours
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)

    # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
    strategy.add_events('bar', stored=True, stored_path='data', applyTA=True)

    strategy.run()