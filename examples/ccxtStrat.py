from datetime import datetime
import os
from pathlib import Path

from ccxt.pro import mexc
import numpy as np
import pandas as pd
from OlympusTrader.broker.interfaces import IOrderSide, ITradeUpdateEvent
from OlympusTrader.broker.ccxt_broker import CCXTBroker
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


class CCXTTB(Strategy):
    def start(self):
        self.execution_risk = 0.08  # 4% of account per trade
        self.minRewardRiskRatio = 2.0  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.67

        # Alphas
        self.add_alphas([
            TestEntryAlpha(self, atrPeriod=14)
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
        universe = {'btc/usdt', 'eth/usdt', 'sol/usdt'}
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
                    self.insights[insight.INSIGHT_ID].submit()
                except BaseException as e:
                    # print(f"Error: {e}")
                    self.insights[insight.INSIGHT_ID].updateState(
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

    # Paper Broker for backtesting
    # broker = PaperBroker(cash=1_000_000, start_date=datetime(
    #         2024, 7, 1), end_date=datetime(2024, 8, 23))
    # exchange = alpaca({
    #     'apiKey': os.getenv('ALPACA_API_KEY'),
    #     'secret': os.getenv('ALPACA_SECRET_KEY'),
    # })
    exchange = mexc({
        'apiKey': os.getenv('MEXC_API_KEY'),
        'secret': os.getenv('MEXC_SECRET_KEY'),
        'enableRateLimit': True,
        "options": {
            'adjustForTimeDifference': True,
            'recvWindow': 50000,
            # "verbose": True
        },

    })

    broker = CCXTBroker(exchange=exchange, paper=False)
    # broker = CCXTBroker(exchange=exchange, paper=True)

    # Strategy
    strategy = CCXTTB(broker, variables={}, resolution=ITimeFrame(
        5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)

    # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
    strategy.add_events('bar')

    strategy.run()
