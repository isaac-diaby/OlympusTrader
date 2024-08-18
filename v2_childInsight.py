from datetime import datetime

import pandas as pd
import OlympusTrader

from OlympusTrader.insight.executors.filled.basicStopLoss import BasicStopLossExecutor
from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
from OlympusTrader.insight.executors.new.cancelAllOppositeSide import CancelAllOppositeSidetExecutor
from OlympusTrader.insight.executors.new.dynamicQuantityToRisk import DynamicQuantityToRiskExecutor
from OlympusTrader.insight.executors.new.marketOrderEntryPrice import MarketOrderEntryPriceExecutor
from OlympusTrader.insight.executors.new.minimumRiskToReward import MinimumRiskToRewardExecutor
from OlympusTrader.insight.executors.new.rejectExpiredInsight import RejectExpiredInsightExecutor
from OlympusTrader.insight.executors.canceled.defaultOnCancelled import DefaultOnCancelledExecutor
from OlympusTrader.insight.executors.rejected.defaultOnReject import DefaultOnRejectExecutor
from OlympusTrader.insight.executors.closed.defaultOnClosed import DefaultOnClosedExecutor


class stackDCA(OlympusTrader.BaseAlpha):
    """
    ### Simple VWAP Crossover Alpha with DCA 
    space the limit orders 1% apart for now the symetrical stack ......1,1,1,1,1,1   

    :param strategy: Strategy instance
    :param atrPeriod: ATR period
    :param vwapPeriod: VWAP period
    :param baseConfidenceModifierField: Field to modify base confidence

    This is a test for the new child insight feature in OlympusTrader
    """

    atrColumn: str
    vwapColumn: str
    superTrendColumn: str
    superTrenddirColumn: str
    superTrendlongColumn: str
    superTrendshortColumn: str

    def __init__(self, strategy, atrPeriod=5, stPeriod=14, stMPeriod: float = 3.0, vwapPeriod=14, baseConfidenceModifierField=None):
        super().__init__(strategy, "SUPERT_STACK", "0.2", baseConfidenceModifierField)
        self.TA = [
            {"kind": 'atr', "length": atrPeriod},
            # {"kind": 'vwap', "length": vwapPeriod}
            {"kind": 'supertrend', "length": stPeriod, "multiplier": stMPeriod}
        
        ]
        self.STRATEGY.warm_up = max(atrPeriod, stPeriod)
        self.atrColumn = f"ATRr_{atrPeriod}"
        # self.vwapColumn = f"VWAP_{vwapPeriod}"
        self.superTrendColumn = f"SUPERT_{stPeriod}_{stMPeriod}"
        self.superTrenddirColumn = f"SUPERTd_{stPeriod}_{stMPeriod}"
        self.superTrendlongColumn = f"SUPERTl_{stPeriod}_{stMPeriod}"
        self.superTrendshortColumn = f"SUPERTs_{stPeriod}_{stMPeriod}"


    def start(self):
        pass

    def init(self, asset):
        state = self.STRATEGY.state
        state[asset["symbol"]] = {"intrade": False}
        pass

    def generateInsights(self, symbol):
        if len(self.STRATEGY.insights) != 0:
            return self.returnResults()

        self.STRATEGY.state[symbol]["intrade"] = False
        try:
            latestBar = self.get_latest_bar(symbol)
            
            previousBar = self.get_previos_bar(symbol)
            latestIATR = latestBar[self.atrColumn]
            baseConfidence = round(self.STRATEGY.baseConfidence * 6.7, 2)

            # Modify Confidence based on baseConfidenceModifierField
            if (self.baseConfidenceModifierField):
                baseConfidence *= abs(self.get_baseConfidenceModifier(symbol))
            if baseConfidence <= 0:
                return self.returnResults(message="Base Confidence is 0.")
            

            # if latestBar['close'] > latestBar[self.vwapColumn] and previousBar['close'] < previousBar[self.vwapColumn]:
            if latestBar[self.superTrenddirColumn] == 1 and previousBar[self.superTrenddirColumn] == -1:
                # Buy Signal - VWAP Crossover
                print(f"Latest Bar: {latestBar}")

                desiredQuantity = 8
                TP = [self.STRATEGY.tools.dynamic_round(latestBar['close'] + latestIATR*3, symbol), self.STRATEGY.tools.dynamic_round(latestBar['close'] + latestIATR*4, symbol)]
                SL = self.STRATEGY.tools.dynamic_round(latestBar['close'] * (1- (0.01*(desiredQuantity+2))) - latestIATR*3, symbol)

                insight = OlympusTrader.Insight(
                    symbol=symbol,
                    side=OlympusTrader.IOrderSide.BUY,
                    strategyType=self.NAME,
                    tf=self.STRATEGY.resolution,
                    quantity=1,
                    limit_price=None,  # Market order - latestBar['close'],
                    SL=SL,
                    TP=TP,
                    executionDepends=[
                        OlympusTrader.StrategyDependantConfirmation.UPSTATE],
                    confidence=baseConfidence,
                    periodUnfilled=None,
                    periodTillTp=None,
                )

                # Add first child at Super trend
                insight.addChildInsight(
                    side=OlympusTrader.IOrderSide.BUY,
                    quantity=1,
                    limit_price=latestBar[self.superTrendColumn],
                    SL=SL,
                    TP=TP,
                    executionDepends=[
                        OlympusTrader.StrategyDependantConfirmation.UPSTATE],
                )

                for i in range(1, desiredQuantity):
                    # Every 1% below the VWAP
                    entry = self.STRATEGY.tools.dynamic_round(latestBar[self.superTrendColumn] * (1 - (0.01*i)), symbol)
                    childInsight = insight.addChildInsight(
                        side=OlympusTrader.IOrderSide.BUY,
                        quantity=1,
                        limit_price=entry,
                        SL=SL,
                        TP=TP,
                        executionDepends=[
                            OlympusTrader.StrategyDependantConfirmation.UPSTATE],
                    )

                self.STRATEGY.state[symbol]["intrade"] = True

                return self.returnResults(insight)

            return self.returnResults()
        except Exception as e:
            return self.returnResults(success=False, message=str(e))

        pass


class v2_childInsight(OlympusTrader.Strategy):
    def start(self):
        self.execution_risk = 0.03
        self.minRewardRiskRatio = 1.5

        self.add_alpha(stackDCA(self, atrPeriod=5, vwapPeriod=14))
        # New Executors
        self.add_executors([
            RejectExpiredInsightExecutor(self),
            MarketOrderEntryPriceExecutor(self),
            # MinimumRiskToRewardExecutor(self, self.minRewardRiskRatio),
            DynamicQuantityToRiskExecutor(self),
            CancelAllOppositeSidetExecutor(self)
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
        # Warm up the strategy with historical data
        self.history[asset['symbol']] = pd.concat([self.history[asset['symbol']], self.broker.get_history(
            asset, self.resolution.add_time_increment(datetime.now(),  self.warm_up*-3), datetime.now(), self.resolution)])

    def universe(self):
        return {'TSLA', 'AAPL', 'JPM', 'MSFT', 'SPY', 'NDAQ',
                              'IHG', 'NVDA', 'TRIP', 'AMZN', 'GOOGL', 'NFLX', 'AAVE/USD', 'BAT/USD', 'BCH/USD', 'BTC/USD', 'ETH/USD', 'GRT/USD', 'LINK/USD', 'LTC/USD',
                              'MKR/USD', 'UNI/USD', 'CRV/USD', 'AVAX/USD'}
        # return {'btc-usd'}

    def on_bar(self, symbol, bar):
        pass
    def generateInsights(self, symbol: str):
        pass

    def executeInsight(self, insight):
        match insight.state:
            case OlympusTrader.InsightState.NEW:
                try:
                    self.insights[insight.INSIGHT_ID].submit()
                except BaseException as e:
                    # print(f"Error: {e}")
                    self.insights[insight.INSIGHT_ID].updateState(
                        OlympusTrader.InsightState.REJECTED, f"Error: {e}")
                    return


if __name__ == "__main__":
    # Paper Broker for backtesting
    broker = OlympusTrader.PaperBroker(cash=1_000_000, start_date=datetime(
        2024, 8, 12), end_date=datetime(2024, 8, 18), leverage=100)
    strategy = v2_childInsight(broker, variables={}, resolution=OlympusTrader.ITimeFrame(
        5, OlympusTrader.ITimeFrameUnit.Minute), verbose=0, ui=False, mode=OlympusTrader.IStrategyMode.BACKTEST)
    # broker = OlympusTrader.PaperBroker(cash=1_000_000, start_date=datetime(
    #     2024, 7, 1), end_date=datetime(2024, 8, 16), leverage=100)
    # strategy = v2_childInsight(broker, variables={}, resolution=OlympusTrader.ITimeFrame(
    #     1, OlympusTrader.ITimeFrameUnit.Hour), verbose=0, ui=False, mode=OlympusTrader.IStrategyMode.BACKTEST)

    strategy.add_events('bar', stored=True, stored_path='data', applyTA=True)

    strategy.run()
