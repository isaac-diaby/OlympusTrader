from datetime import datetime

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


class  TestOrderUpdate(Strategy):
    def start(self):
        self.add_ta([
            {"kind": 'atr', "length": 14},
            ])
        self.warm_up = 14
        self.execution_risk = 0.04  # 4% of account per trade
        self.minRewardRiskRatio = 1.2  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.1
        # New Executors
        self.add_executors([
            MarketOrderEntryPriceExecutor(self),
            # DynamicQuantityToRiskExecutor(self),
        ])
       
        # Cancelled Executors
        self.add_executors([
            DefaultOnCancelledExecutor(self),
        ])
        # Filled Executors
        self.add_executors([
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

        state['last_trade'] = None
        state['test_phase'] = 0 

        # load warm up history

        self.history[asset['symbol']] = pd.concat([self.history[asset['symbol']], self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(),  self.warm_up*-3), datetime.now(), self.resolution)])

    def universe(self):
        # universe = {'aapl', 'goog', 'amzn', 'msft', 'tsla'}
        universe = {'btc-usd'}
        # universe = {'btc-usd','eth-usd'}
        return universe

    def on_bar(self, symbol, bar):
        pass

    def generateInsights(self, symbol: str):
        latest = self.history[symbol].iloc[-1]
        step =  latest["ATRr_14"] if not np.isnan(latest["ATRr_14"])  else np.abs(latest['close'] - latest['open'])


        if self.state['last_trade'] == None:
            if self.state['test_phase'] == 0:
                insight = Insight(
                    side=IOrderSide.BUY,
                    symbol=symbol,
                    strategyType="TestOrderUpdate-0",
                    tf=self.resolution,
                    confidence=0.1,
                    quantity=0.5,
                    limit_price=latest['close'],
                    SL=latest['close'] - step,
                    TP=[latest['close'] + step],
                    periodUnfilled=None, 
                )
                # Check update TP
                print("Updating TP")
                insight.updateTakeProfit([latest['close'] + (step*2)])
                print(f"Insight: {insight}")

                self.state['last_trade'] = insight.INSIGHT_ID
                self.add_insight(insight)

            if self.state['test_phase'] == 1:
                insight = Insight(
                    side=IOrderSide.BUY,
                    symbol=symbol,
                    strategyType="TestOrderUpdate-1",
                    tf=self.resolution,
                    confidence=0.1,
                    quantity=0.5,
                    limit_price=latest['close'],
                    SL=latest['close'] - step,
                    TP=[latest['close'] + step]
                )
                # Check update SL
                print("Updating SL")
                insight.updateStopLoss(latest['close'] - (step*2))
                print(f"Insight: {insight}")

                self.state['last_trade'] = insight.INSIGHT_ID
                self.add_insight(insight)




        pass


    def executeInsight(self, insight: Insight):
        # print(f"Executing Insight: {insight.INSIGHT_ID} - {insight.state}")
        match insight.state:
            case InsightState.NEW:
                try:
                    insight.submit()
                except BaseException as e:
                    print(f"Error: {e}")
                    return
            # case InsightState.EXECUTED:
            #     return
            case InsightState.FILLED:

                if self.state['test_phase'] == 0:
                    insight.updateTakeProfit([insight.limit_price + (insight.TP[0] - insight.limit_price)])
                    return
                if self.state['test_phase'] == 1:
                    insight.updateStopLoss(insight.SL - (insight.SL - insight.limit_price))
                    return
                return
            case InsightState.CLOSED:
                self.state['last_trade'] = None
                self.state['test_phase'] += 1
                return
            case InsightState.CANCELED:
                self.state['last_trade'] = None
                self.state['test_phase'] += 1
                return
            case InsightState.REJECTED:
                return
            # case _:
            #     return

if __name__ == "__main__":

    # Live Paper Broker for backtesting
    # broker = PaperBroker(cash=100_000, mode=IStrategyMode.LIVE, feedDelay=60*8) # 8 hours
    # strategy = TestOrderUpdate(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)
    
    broker = PaperBroker(cash=100_000, start_date=datetime(
            2025, 5, 17), end_date=datetime(2025, 5,18), verbose=1, leverage=1.0)
    strategy = TestOrderUpdate(broker, variables={}, resolution=ITimeFrame(
        5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.BACKTEST)


    # Strategy live paper trading on the paper broker 
    # 1 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)
    # 5 Minute
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     5, ITimeFrameUnit.Minute), verbose=0, ui=False, mode=IStrategyMode.LIVE)
    # 1 Hour
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.LIVE)
    # 4 Hours
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     4, ITimeFrameUnit.Hour), verbose=0, ui=False, mode=IStrategyMode.LIVE)
    

   
    # Feeds into a IMarketDataStream TypedDict that lets you save the data to a file or load it from a file
    strategy.add_events('bar', stored=True, stored_path='data',
                        start=broker.START_DATE, end=broker.END_DATE, applyTA=True)

    strategy.run()
