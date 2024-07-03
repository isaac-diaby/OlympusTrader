import numpy as np

from ..broker.interfaces import IOrderSide
from .base_alpha import BaseAlpha
from ..insight.insight import Insight, StrategyDependantConfirmation


class EMAPriceCrossoverAlpha(BaseAlpha):
    """
    ### EMA Crossover Alpha
    This alpha model generates insights based on EMA Crossover.

    Parameters:
    - strategy: BaseStrategy - Strategy instance
    - atrPeriod: int - ATR Period
    - emaPeriod: int - EMA Period
    - baseConfidenceModifierField: str - Field to modify base confidence

    """
    atrColumn: str
    emaColumn: str

    def __init__(self, strategy, atrPeriod=14, emaPeriod=14, baseConfidenceModifierField=None):
        super().__init__(strategy, "EMA_PRICE_CROSSOVER", "0.1", baseConfidenceModifierField)
        self.TA = [
            {"kind": 'atr', "length": atrPeriod},
            {"kind": 'ema', "length": emaPeriod}
        ]
        self.STRATEGY.warm_up = max(atrPeriod, emaPeriod)
        self.atrColumn = f'ATRr_{atrPeriod}'
        self.emaColumn = f'EMA_{emaPeriod}'

    def start(self):
        pass

    def init(self, asset):
        pass

    def generateInsights(self, symbol):
        try:
            latestBar = self.get_latest_bar(symbol)
            previousBar = self.get_previos_bar(symbol)
            latestIATR = latestBar[self.atrColumn]
            latestBarIEMA = latestBar[self.emaColumn]
            previousBarIATR = previousBar[self.atrColumn]
            previousBarIEMA = previousBar[self.emaColumn]

            baseConfidence = self.STRATEGY.baseConfidence
            # Modify Confidence based on baseConfidenceModifierField
            if (self.baseConfidenceModifierField):
                baseConfidence *= abs(self.get_baseConfidenceModifier(symbol))

            if baseConfidence <= 0:
                return self.returnResults(message="Base Confidence is 0.")

            # Generate EMA Crossover Long
            # and marketState > 3):
            if ((latestBarIEMA < latestBar['close']) and (previousBarIEMA > previousBar['high']) and (np.abs(previousBar['open'] - previousBar['close']) > previousBarIATR) and (np.abs(latestBar['close'] - latestBarIEMA) < latestIATR)):
                TP = self.STRATEGY.tools.dynamic_round(
                    latestBar['high']+(latestIATR*3.5), symbol)
                SL = self.STRATEGY.tools.dynamic_round(
                    max(previousBar['low']-(.5*latestIATR), latestBarIEMA-latestIATR*1.5), symbol)
                ENTRY = self.STRATEGY.tools.dynamic_round(
                    latestBarIEMA, symbol)  # pullback
                # time to live unfilled
                TTLUF = self.STRATEGY.tools.calculateTimeToLive(
                    latestBar['close'], ENTRY, latestIATR)
                # time to live till take profit
                TTLF = self.STRATEGY.tools.calculateTimeToLive(
                    TP, ENTRY, latestIATR)

                return self.returnResults(Insight(IOrderSide.BUY, symbol, self.NAME, self.STRATEGY.resolution, None, ENTRY, [TP], SL, baseConfidence, [StrategyDependantConfirmation.HRVCM], TTLUF, TTLF))

            # Generate EMA Crossover Short
            # and marketState < -3):
            if (self.STRATEGY.assets[symbol]['shortable'] and (latestBarIEMA > latestBar['close']) and (previousBarIEMA < previousBar['low']) and (np.abs(previousBar['open'] - previousBar['close']) > previousBarIATR) and (np.abs(latestBarIEMA - latestBar['close']) < latestIATR)):
                TP = self.STRATEGY.tools.dynamic_round(
                    latestBar['low']-(latestIATR*3.5), symbol)
                SL = self.STRATEGY.tools.dynamic_round(
                    min(previousBar['high']+(.5*latestIATR), latestBarIEMA+latestIATR*1.5), symbol)
                ENTRY = self.STRATEGY.tools.dynamic_round(
                    latestBarIEMA, symbol)
                # time to live unfilled
                TTLUF = self.STRATEGY.tools.calculateTimeToLive(
                    latestBar['close'], ENTRY, latestIATR)
                # time to live till take profit
                TTLF = self.STRATEGY.tools.calculateTimeToLive(TP, ENTRY, latestIATR)

                return self.returnResults(Insight(IOrderSide.SELL, symbol, self.NAME, self.STRATEGY.resolution, None, ENTRY, [TP], SL, baseConfidence, [StrategyDependantConfirmation.HRVCM], TTLUF, TTLF))
            return self.returnResults()
        except Exception as e:
            return self.returnResults(success=False, message=str(e))
