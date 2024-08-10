from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from OlympusTrader.broker.interfaces import IOrderSide, ITradeUpdateEvent
from OlympusTrader.broker.paper_broker import PaperBroker
from OlympusTrader.insight.executors.closed.defaultOnClosed import DefaultOnClosedExecutor
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


class QbitTB(Strategy):
    def start(self):
        self.add_ta([
            {"kind": 'macd', "fast": 16, "slow": 36, "signal": 9},
            {"kind": 'atr', "length": 14},
            {"kind": 'rsi', "length": 14, "scalar": 10}
            ])
        self.warm_up = 36
        self.execution_risk = 0.04  # 4% of account per trade
        self.minRewardRiskRatio = 2.0  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.1

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
    #     2024, 7, 27), end_date=datetime(2024, 7, 28)) # 1 day
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 5, 27, 14), end_date=datetime(2024, 5, 27, 16)) # 2 hours
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 5, 1, 14), end_date=datetime(2024, 5, 30, 16))  # all of may
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 5, 4, minute=30), end_date=datetime(2024, 5, 30, 16))  # all of may
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #         2024, 8, 2), end_date=datetime(2024, 8, 5))
    broker = PaperBroker(cash=1_000_000, start_date=datetime(
            2024, 7, 1), end_date=datetime(2024, 8, 6))
    # Strategy
    # 1 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    # 5 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    # 1 Hour
    strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
        1, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    # 4 Hours
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     4, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)
    
    # live paper trading on the paper broker 
    # broker = PaperBroker(cash=1_000_000, mode=IStrategyMode.LIVE, feedDelay=60*8) # 8 hours
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)

    strategy.add_alphas([
        RSIDiverganceAlpha(strategy, local_window=36, divergance_window=50, atrPeriod=14, rsiPeriod=14, baseConfidenceModifierField='market_state'),
        EMAPriceCrossoverAlpha(strategy, atrPeriod=14, emaPeriod=9, baseConfidenceModifierField='market_state'),
        # TestEntryAlpha(strategy, atrPeriod=14)
    ])
    # New Executors
    strategy.add_executors([
        RejectExpiredInsightExecutor(strategy),
        MarketOrderEntryPriceExecutor(strategy),
        MinimumRiskToRewardExecutor(strategy),
        DynamicQuantityToRiskExecutor(strategy),
        CancelAllOppositeSidetExecutor(strategy)
    ])
    # Executed Executors
    RejectExpiredExecutedExecutor = RejectExpiredInsightExecutor(strategy)
    RejectExpiredExecutedExecutor._override_state(InsightState.EXECUTED)
    strategy.add_executors([
        RejectExpiredExecutedExecutor,
    ])
    # Cancelled Executors
    strategy.add_executors([
        DefaultOnCancelledExecutor(strategy),
    ])
    # Filled Executors
    strategy.add_executors([
        CloseExhaustedInsightExecutor(strategy),
        CloseMarketChangedExecutor(strategy),
        BasicStopLossExecutor(strategy),
        BasicTakeProfitExecutor(strategy)
    ])
    # Closed Executors
    strategy.add_executors([
        DefaultOnClosedExecutor(strategy),
    ])
    # Rejected Executors
    strategy.add_executors([
        DefaultOnRejectExecutor(strategy)
    ])

    # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
    strategy.add_events('bar', stored=True, stored_path='data', applyTA=True,
                        start=broker.START_DATE, end=broker.END_DATE)

    strategy.run()
    if (strategy.MODE == IStrategyMode.BACKTEST):
        print(strategy.BACKTESTING_RESULTS)
        # get the first asset in the strategy and plot the backtesting results
        symbol = list(strategy.assets.keys())[0]
        print(f"Symbol: {symbol}")

        save_path = Path(f"backtests/{strategy.STRATEGY_ID}")
        save_path.mkdir(parents=True, exist_ok=True)
        
        if (strategy.BACKTESTING_RESULTS.get(symbol)):
            strategy.BACKTESTING_RESULTS[symbol].save(f"backtests/{strategy.STRATEGY_ID}/{symbol}-{strategy.resolution}-backtest")
            strategy.BACKTESTING_RESULTS[symbol].plot().show()
        else:
            save_path.rmdir()
            print("No backtesting results found")