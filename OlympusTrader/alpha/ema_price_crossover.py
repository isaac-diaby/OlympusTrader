import numpy as np

from ..broker.interfaces import IOrderSide
from .base_alpha import BaseAlpha
from ..insight.insight import Insight, StrategyDependantConfirmation


class EMAPriceCrossoverAlpha(BaseAlpha):
    """
    ### EMA Crossover Alpha
    This alpha model generates insights based on EMA Crossover.

    :param strategy (BaseStrategy): The strategy instance
    :param atrPeriod (int): The period for the ATR indicator
    :param emaPeriod (int): The period for the EMA indicator
    :param baseConfidenceModifierField (str): The field to use for modifying the base confidence

    Author:
        @isaac-diaby
    """
    atrColumn: str
    emaColumn: str

    def __init__(self, strategy, atrPeriod: int = 14, emaPeriod: int = 14, baseConfidenceModifierField = None):
        super().__init__(strategy, "EMA_PRICE_CROSSOVER", "0.1", baseConfidenceModifierField)
        # Check if atrPeriod and emaPeriod are above 0
        if atrPeriod <= 0 or emaPeriod <= 0:
            raise ValueError("ATR Period and EMA Period must be positive integers")

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

            if self.is_long_signal(latestBar, previousBar, latestIATR, latestBarIEMA, previousBarIATR, previousBarIEMA):
                return self.create_insight(IOrderSide.BUY, symbol, latestBar, previousBar, latestIATR, latestBarIEMA, baseConfidence)

            if self.is_short_signal(latestBar, previousBar, latestIATR, latestBarIEMA, previousBarIATR, previousBarIEMA, symbol):
                return self.create_insight(IOrderSide.SELL, symbol, latestBar, previousBar, latestIATR, latestBarIEMA, baseConfidence)

            return self.returnResults()
        except Exception as e:
            return self.returnResults(success=False, message=str(e))

    def is_long_signal(self, latestBar, previousBar, latestIATR, latestBarIEMA, previousBarIATR, previousBarIEMA):
        return (latestBarIEMA < latestBar['close'] and previousBarIEMA > previousBar['high'] and
                # np.abs(previousBar['open'] - previousBar['close']) > previousBarIATR and
                np.abs(latestBar['close'] - latestBarIEMA) < latestIATR)

    def is_short_signal(self, latestBar, previousBar, latestIATR, latestBarIEMA, previousBarIATR, previousBarIEMA, symbol):
        return (self.STRATEGY.assets[symbol]['shortable'] and latestBarIEMA > latestBar['close'] and
                previousBarIEMA < previousBar['low'] and
                # np.abs(previousBar['open'] - previousBar['close']) > previousBarIATR and
                np.abs(latestBarIEMA - latestBar['close']) < latestIATR)

    def create_insight(self, order_side: IOrderSide, symbol: str, latestBar, previousBar, latestIATR, latestBarIEMA, baseConfidence: float):
        if order_side == IOrderSide.BUY:
            TP = self.STRATEGY.tools.dynamic_round(latestBar['high']+(latestIATR*3.5), symbol)
            SL = self.STRATEGY.tools.dynamic_round(max(previousBar['low']-(.5*latestIATR), latestBarIEMA-latestIATR*1.5), symbol)
        else:
            TP = self.STRATEGY.tools.dynamic_round(latestBar['low']-(latestIATR*3.5), symbol)
            SL = self.STRATEGY.tools.dynamic_round(min(previousBar['high']+(.5*latestIATR), latestBarIEMA+latestIATR*1.5), symbol)

        ENTRY = self.STRATEGY.tools.dynamic_round(latestBarIEMA, symbol)
        TTLUF = self.STRATEGY.tools.calculateTimeToLive(latestBar['close'], ENTRY, latestIATR)
        TTLF = self.STRATEGY.tools.calculateTimeToLive(TP, ENTRY, latestIATR)

        return self.returnResults(Insight(order_side, symbol, self.NAME, self.STRATEGY.resolution, None, ENTRY, [TP], SL, baseConfidence, [StrategyDependantConfirmation.NONE], TTLUF, TTLF))
