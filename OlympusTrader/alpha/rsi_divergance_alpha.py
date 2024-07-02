
import numpy as np

from ..broker.interfaces import IOrderSide
from ..alpha.base_alpha import BaseAlpha
from ..insight.insight import Insight, StrategyDependantConfirmation


class RSIDiverganceAlpha(BaseAlpha):
    """
    ### RSI Divergance Alpha
    This alpha model generates insights based on RSI Divergance.

    Parameters:
    - local_window: int - Local Window for Points of Control
    - divergance_window: int - Divergance Window for RSI Divergance
    - atrPeriod: int - ATR Period
    - rsiPeriod: int - RSI Period
    - baseConfidenceModifierField: str - Field to modify base confidence


    """
    local_window: int
    divergance_window: int

    atrColumn: str
    rsiColumn: str

    def __init__(self, strategy, local_window=1, divergance_window=50, atrPeriod=14, rsiPeriod=14, baseConfidenceModifierField=None):
        super().__init__(strategy, "RSI_DIVERGANCE", "0.1", baseConfidenceModifierField)
        self.TA = [
            {"kind": 'atr', "length": atrPeriod},
            {"kind": 'rsi', "length": rsiPeriod, "scalar": 10}
        ]
        self.STRATEGY.warm_up = max(atrPeriod, rsiPeriod)
        self.atrColumn = f'ATRr_{atrPeriod}'
        self.rsiColumn = f'RSI_{rsiPeriod}'

        self.local_window = local_window
        self.divergance_window = divergance_window

    def start(self):
        self.STRATEGY.state['local_window'] = self.local_window
        self.STRATEGY.state['divergance_window'] = self.divergance_window

    def init(self, asset):
        pass

    def generateInsights(self, symbol):
        try:
                
            # Compute Local Points of Control
            self.computeLocalPointsOfControl(symbol)
            # Compute RSI Divergance
            self.computeRSIDivergance(symbol)
            latestBar = self.get_latest_bar(symbol)
            previousBar = self.get_previos_bar(symbol)
            latestIATR = latestBar[self.atrColumn]
            baseConfidence = self.STRATEGY.baseConfidence

            # Modify Confidence based on baseConfidenceModifierField
            if (self.baseConfidenceModifierField):
                baseConfidence *= abs(self.get_baseConfidenceModifier(symbol))
            if baseConfidence <= 0:
                return self.returnResults(message="Base Confidence is 0.")

            # RSA Divergance Long
            # and marketState < 0):
            if (not np.isnan(latestBar['RSI_Divergance_Long'])):
                # print(f"Insight - {symbol}: Long Divergance: {latestBar['RSI_Divergance_Long']}")
                TP = self.STRATEGY.tools.dynamic_round(
                    (latestBar.close + (latestIATR*3.5)), symbol)
                SL = self.STRATEGY.tools.dynamic_round(
                    (latestBar.close - (latestIATR*1.5)), symbol)
                ENTRY = previousBar.high if (abs(
                    previousBar.high - latestBar.close) < latestIATR) else self.STRATEGY.tools.dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
                # time to live unfilled
                TTLUF = self.STRATEGY.tools.calculateTimeToLive(
                    latestBar['close'], ENTRY, latestIATR)
                # time to live till take profit
                TTLF = self.STRATEGY.tools.calculateTimeToLive(
                    TP, ENTRY, latestIATR)

                return self.returnResults(Insight(IOrderSide.BUY, symbol,
                                                self.NAME, self.STRATEGY.resolution, None, ENTRY, [TP], SL, baseConfidence, [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))
            # RSA Divergance Short
            # and marketState > 0):
            if (self.STRATEGY.assets[symbol]['shortable'] and not np.isnan(latestBar['RSI_Divergance_Short'])):
                # print(f"Insight - {symbol}: Short Divergance: {latestBar['RSI_Divergance_Short']}")
                TP = self.STRATEGY.tools.dynamic_round(
                    (latestBar.close - (latestIATR*3.5)), symbol)
                SL = self.STRATEGY.tools.dynamic_round(
                    (latestBar.close + (latestIATR*1.5)), symbol)
                ENTRY = previousBar.low if (abs(
                    previousBar.low - latestBar.close) < latestIATR) else self.STRATEGY.tools.dynamic_round((latestBar.open+(.2*latestIATR)), symbol)
                # time to live unfilled
                TTLUF = self.STRATEGY.tools.calculateTimeToLive(
                    latestBar['close'], ENTRY, latestIATR)
                # time to live till take profit
                TTLF = self.STRATEGY.tools.calculateTimeToLive(
                    TP, ENTRY, latestIATR)

                return self.returnResults(Insight(IOrderSide.SELL, symbol,
                                                self.NAME, self.STRATEGY.resolution, None, ENTRY, [TP], SL, baseConfidence, [StrategyDependantConfirmation.LRVCM], TTLUF, TTLF))
            
            return self.returnResults()
        except Exception as e:
            return self.returnResults(success=False, message=str(e))

    def computeLocalPointsOfControl(self, symbol: str):
        window = self.STRATEGY.state['local_window']
        history = self.get_history(symbol)
        viewColumn = 'close'
        self.STRATEGY.HISTORY[symbol].loc[[symbol], ['local_max_poc']] = history[viewColumn][(
            history[viewColumn].shift(window) < history[viewColumn]) & (history[viewColumn].shift(-window) < history[viewColumn]
                                                                        )]
        self.STRATEGY.HISTORY[symbol].loc[[symbol], ['local_min_poc']] = history[viewColumn][(
            history[viewColumn].shift(window) > history[viewColumn]) & (history[viewColumn].shift(-window) > history[viewColumn]
                                                                        )]
        return history

    def computeRSIDivergance(self, symbol: str):
        window = self.STRATEGY.state['divergance_window']
        # remove first 14 rows for RSI Warmup
        history = self.get_history(symbol)
        IRSI = history[self.rsiColumn]

        # Bullish Divergance - RSI is Increasing while price is Decreasing
        self.STRATEGY.history[symbol].loc[[symbol],
                                          ['RSI_Divergance_Long']] = np.nan

        # only use local lows of point of control for reversal
        longPivot = history['local_min_poc'].dropna()
        lowerLowsPivots = longPivot.loc[longPivot.shift(1) > longPivot]

        for index, price in lowerLowsPivots[-1:-window:-1].items():
            _, *previousLocalPoC = longPivot.loc[index: (
                index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
            if (len(previousLocalPoC) == 0):
                continue
            lastLowIndex, lastPrice = previousLocalPoC[0]
            if (IRSI.loc[lastLowIndex] < IRSI.loc[index]):
                self.STRATEGY.history[symbol].loc[index, [
                    'RSI_Divergance_Long']] = lastPrice-price

        # Bearish divergence - RSI is Decreasing while price is Increasing
        self.STRATEGY.history[symbol].loc[[symbol],
                                          ['RSI_Divergance_Short']] = np.nan

        # only use local maximas of point of control for reversal
        shortPivot = history['local_max_poc'].dropna()
        higherHighsPivots = shortPivot.loc[shortPivot.shift(1) < shortPivot]

        for index, price in higherHighsPivots[-1:-window:-1].items():
            _, *previousLocalPoC = shortPivot.loc[index: (
                index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
            if (len(previousLocalPoC) == 0):
                continue
            lastHighIndex, lastPrice = previousLocalPoC[0]
            if (IRSI.loc[lastHighIndex] > IRSI.loc[index]):
                self.STRATEGY.history[symbol].loc[index, [
                    'RSI_Divergance_Short']] = price-lastPrice

        return history
