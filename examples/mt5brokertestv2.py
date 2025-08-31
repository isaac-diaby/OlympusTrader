from OlympusTrader.insight.executors.closed.defaultOnClosed import DefaultOnClosedExecutor
from OlympusTrader.insight.executors.rejected.defaultOnReject import DefaultOnRejectExecutor
from OlympusTrader.insight.executors.canceled.defaultOnCancelled import DefaultOnCancelledExecutor
from OlympusTrader.insight.executors.new.rejectExpiredInsight import RejectExpiredInsightExecutor
from OlympusTrader.insight.executors.new.marketOrderEntryPrice import MarketOrderEntryPriceExecutor
from OlympusTrader.insight.executors.new.dynamicQuantityToRisk import DynamicQuantityToRiskExecutor
from OlympusTrader.insight.executors.new.cancelAllOppositeSide import CancelAllOppositeSidetExecutor
from OlympusTrader.insight.executors.filled.closeMarketChanged import CloseMarketChangedExecutor
from OlympusTrader.insight.executors.filled.closeExhaustedInsight import CloseExhaustedInsightExecutor
from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
from OlympusTrader.insight.executors.filled.basicStopLoss import BasicStopLossExecutor
from OlympusTrader.alpha.test_entry import TestEntryAlpha
from OlympusTrader.strategy.strategy import Strategy
import os
import pandas as pd
from datetime import datetime
from OlympusTrader.broker.mt5_broker import Mt5Broker
from OlympusTrader.broker.paper_broker import PaperBroker
from OlympusTrader.insight.insight import Insight, InsightState
from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit
from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader import Strategy

import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class MT5_test(Strategy):
    def start(self):
        self.execution_risk = 0.08  # 4% of account per trade
        self.minRewardRiskRatio = 2.0  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.67

        # Alphas
        self.add_alphas([
            TestEntryAlpha(self, atrPeriod=14, limitEntries=True, maxSpawn=4)
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

        # load warm up history
        self.history[asset['symbol']] = pd.concat([self.history[asset['symbol']], self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(),  self.warm_up*-3), datetime.now(), self.resolution)])

    def universe(self):
        # universe = {'aapl', 'goog', 'amzn', 'msft', 'tsla'}
        # universe = {'btc/usd'}
        # universe = {'btc/usd', 'ETHUSD'}
        universe = {'btcusd'}
        # universe = {'btc/usd', 'ETHUSD', "xrpusd", "uniusd"}
        # universe = {'gbp/usd'}
        # universe = {'btc/usd', 'gbp/usd'}
        # universe = {'btc/usdt', 'eth/usdt', 'sol/usdt'}
        # universe = {'btc-usd','eth-usd'}
        return universe

    def on_bar(self, symbol, bar):
        pass

    def generateInsights(self, symbol: str):
        pass

    def executeInsight(self, insight: Insight):
        match insight.state:
            case InsightState.NEW:
                try:
                    insight.submit()
                except BaseException as e:
                    # print(f"Error: {e}")
                    insight.updateState(
                        InsightState.REJECTED, f"Error: {e}")
                    return
            # case InsightState.EXECUTED:
            #     return
            # case InsightState.FILLED:
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
    live = True

    tf = ITimeFrame(1, ITimeFrameUnit.Minute)
  
    if live:
        broker = Mt5Broker(paper=False)
        # broker = CCXTBroker(exchange=exchange, paper=True)

        # Strategy
        strategy = MT5_test(broker, variables={}, resolution=tf, verbose=0, ui=True, mode=IStrategyMode.LIVE)

        # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
        strategy.add_events('bar')
    else:
        broker = PaperBroker(cash=100_000, start_date=datetime(
            2024, 10, 19), end_date=datetime(2024, 10, 20))  # all
        
        strategy = MT5_test(broker, variables={}, resolution=tf, verbose=0, ui=False, mode=IStrategyMode.BACKTEST)

        # On windows the to_hdf method does not work, so we cant use the stored_path and stored parameters
        # strategy.add_events('bar', stored=True, stored_path='data', applyTA=True,
        #                     start=broker.START_DATE, end=broker.END_DATE)
        strategy.add_events('bar', stored=False, stored_path=None, applyTA=True,
                            start=broker.START_DATE, end=broker.END_DATE)
    strategy.run()

