from datetime import datetime
import pandas as pd

from OlympusTrader.broker.alpaca_broker import AlpacaBroker
from OlympusTrader.strategy.strategy import Strategy
from OlympusTrader.insight.insight import Insight, InsightState
from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit
# from OlympusTrader.utils.tools import dynamic_round

# Alphas
from OlympusTrader.alpha.rsi_divergance_alpha import RSIDiverganceAlpha
from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha
# from OlympusTrader.alpha.test_entry import TestEntryAlpha

# Executors
from OlympusTrader.insight.executors.new.cancelAllOppositeSide import CancelAllOppositeSidetExecutor
from OlympusTrader.insight.executors.new.dynamicQuantityToRisk import DynamicQuantityToRiskExecutor
from OlympusTrader.insight.executors.new.marketOrderEntryPrice import MarketOrderEntryPriceExecutor
from OlympusTrader.insight.executors.new.minimumRiskToReward import MinimumRiskToRewardExecutor
from OlympusTrader.insight.executors.new.rejectExpiredInsight import RejectExpiredInsightExecutor
from OlympusTrader.insight.executors.filled.basicStopLoss import BasicStopLossExecutor
from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
from OlympusTrader.insight.executors.filled.closeExhaustedInsight import CloseExhaustedInsightExecutor
from OlympusTrader.insight.executors.filled.closeMarketChanged import CloseMarketChangedExecutor
from OlympusTrader.insight.executors.canceled.defaultOnCancelled import DefaultOnCancelledExecutor
from OlympusTrader.insight.executors.rejected.defaultOnReject import DefaultOnRejectExecutor
from OlympusTrader.insight.executors.closed.defaultOnClosed import DefaultOnClosedExecutor


import warnings

from v2_childInsight import v2_childInsight
warnings.simplefilter(action="ignore", category=FutureWarning)


class QbitTB(Strategy):
    def start(self):
        self.add_ta([
            {"kind": 'macd', "fast": 16, "slow": 36, "signal": 9},
            {"kind": 'atr', "length": 14},
            {"kind": 'rsi', "length": 14, "scalar": 10}
        ])
        self.warm_up = 36
        self.execution_risk = 0.02  # 2% of account per trade
        self.minRewardRiskRatio = 2.0  # 2:1 Reward to Risk Ratio minimum
        self.baseConfidence = 0.1

        # Alphas
        self.add_alphas([
            RSIDiverganceAlpha(self, local_window=36, divergance_window=50,
                               atrPeriod=14, rsiPeriod=14, baseConfidenceModifierField='market_state'),
            EMAPriceCrossoverAlpha(
                self, atrPeriod=14, emaPeriod=9, baseConfidenceModifierField='market_state'),
            # TestEntryAlpha(self)
        ])
        # New Executors
        self.add_executors([
            RejectExpiredInsightExecutor(self),
            MarketOrderEntryPriceExecutor(self),
            MinimumRiskToRewardExecutor(self, self.minRewardRiskRatio),
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

        self.add_events('bar')

    def init(self, asset):
        state = self.state
        # inital market state
        if (state.get('market_state') == None):
            state['market_state'] = {}
        state['market_state'][asset['symbol']] = 0

        # load warm up history

        self.history[asset['symbol']] = pd.concat([self.history[asset['symbol']], self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(),  ((self.warm_up*-4))), datetime.now(), self.resolution)])

    def universe(self):
        # universe = {'AAVE/USD', 'BAT/USD', 'BCH/USD', 'BTC/USD', 'ETH/USD', 'GRT/USD', 'LINK/USD', 'LTC/USD',
        #             'MKR/USD', 'UNI/USD', 'CRV/USD', 'AVAX/USD'}
        # universe = {'TSLA', 'AAPL', 'JPM', 'MSFT', 'SPY', 'NDAQ',
        #             'IHG', 'NVDA', 'TRIP', 'AMZN', 'GOOGL', 'NFLX', }

        universe: set[str] = {'TSLA', 'AAPL', 'JPM', 'MSFT', 'SPY', 'NDAQ',
                              'IHG', 'NVDA', 'TRIP', 'AMZN', 'GOOGL', 'NFLX', 'AAVE/USD', 'BAT/USD', 'BCH/USD', 'BTC/USD', 'ETH/USD', 'GRT/USD', 'LINK/USD', 'LTC/USD',
                              'MKR/USD', 'UNI/USD', 'CRV/USD', 'AVAX/USD'}

        return universe

    def on_bar(self, symbol, bar):
        self.computeMarketState(symbol)
        return

    def generateInsights(self, symbol: str):
        pass

    def executeInsight(self, insight: Insight):
        match insight.state:
            case InsightState.NEW:
                try:
                    # Submit Insight
                    self.insights[insight.INSIGHT_ID].submit()
                except BaseException as e:
                    self.insights[insight.INSIGHT_ID].updateState(
                        InsightState.REJECTED, f"Error: {e}")
                    return

    def computeMarketState(self, symbol: str):
        marketState = self.state['market_state'][symbol]
        history = self.history[symbol]
        IMACD = history[['MACD_16_36_9', 'MACDh_16_36_9', 'MACDs_16_36_9']]
        IRSI = history['RSI_14']

        marketState = 0
        # MACD Trend
        if ((IMACD.iloc[-1, 0] > 0)):  # MACD value and  # MACD histogram are both positive
            marketState += 3
        elif ((IMACD.iloc[-1, 0] < 0)):  # MACD value and  # MACD histogram are both positive
            marketState -= 3

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

        marketState = min(max(marketState, -5), 5)
        self.state['market_state'][symbol] = marketState
        return marketState


if __name__ == "__main__":

    # Live Broker
    broker = AlpacaBroker(paper=True)

    # Every Minute Strategy
    # strategy = QbitTB(broker, variables={}, resolution=ITimeFrame(
    #     1, ITimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.LIVE)
    strategy = v2_childInsight(broker, variables={}, resolution=ITimeFrame(
        1, ITimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.LIVE)

    strategy.run()
