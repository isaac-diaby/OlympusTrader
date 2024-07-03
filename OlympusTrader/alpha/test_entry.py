from ..broker.interfaces import IOrderSide
from .base_alpha import BaseAlpha
from ..insight.insight import Insight, StrategyDependantConfirmation, StrategyTypes


class TestEntryAlpha(BaseAlpha):
    """
    ### Test Entry Alpha
    This alpha model generates insights if there is no other insight.
    This is intended for testing purposes.

    Parameters:
    - strategy: BaseStrategy - Strategy instance
    - atrPeriod: int - ATR Period
    - baseConfidenceModifierField: str - Field to modify base confidence
    """
    atrColumn: str

    def __init__(self, strategy,  atrPeriod=14,  baseConfidenceModifierField=None):
        super().__init__(strategy, "TEST_ENTRY", "0.1", baseConfidenceModifierField)
        self.TA = [
            {"kind": 'atr', "length": atrPeriod},
        ]
        self.atrColumn = f'ATRr_{atrPeriod}'

        self.STRATEGY.warm_up = atrPeriod

    def start(self):
        pass

    def init(self, asset):
        pass

    def generateInsights(self, symbol):
        try:
            latestBar = self.get_latest_bar(symbol)
            previousBar = self.get_previos_bar(symbol)
            latestIATR = latestBar[self.atrColumn]
            baseConfidence = self.STRATEGY.baseConfidence
            # Modify Confidence based on baseConfidenceModifierField
            # if (self.baseConfidenceModifierField):
            #     baseConfidence *= abs(self.get_baseConfidenceModifier(symbol))

            # if baseConfidence <= 0:
            #     return self.returnResults(message="Base Confidence is 0.")

            if len(self.STRATEGY.insights) > 0:
                return self.returnResults(message="Insight already exists.")

            # Generate Test Entry
            if (latestBar.close > latestBar.open):
                TP = self.STRATEGY.tools.dynamic_round(
                    latestBar.close + (latestIATR*10), symbol)
                SL = self.STRATEGY.tools.dynamic_round(
                    latestBar.close - (latestIATR*1.5), symbol)
                ENTRY = self.STRATEGY.tools.dynamic_round(
                    latestBar['close'], symbol)

                return self.returnResults(insight=Insight(
                    side=IOrderSide.BUY,
                    symbol=symbol,
                    strategyType=StrategyTypes.TEST,
                    tf=self.STRATEGY.resolution,
                    quantity=None,
                    # limit_price=ENTRY,
                    TP=[TP],
                    SL=SL,
                    confidence=baseConfidence,
                    periodUnfilled=5,
                    periodTillTp=10
                ))
            else:
                if self.STRATEGY.assets[symbol]["shortable"]:
                    TP = self.STRATEGY.tools.dynamic_round(
                        latestBar.close - (latestIATR*10), symbol)
                    SL = self.STRATEGY.tools.dynamic_round(
                        latestBar.close + (latestIATR*1.5), symbol)
                    ENTRY = self.STRATEGY.tools.dynamic_round(
                        latestBar['close'], symbol)

                    return self.returnResults(insight=Insight(
                        side=IOrderSide.SELL,
                        symbol=symbol,
                        strategyType=StrategyTypes.TEST,
                        tf=self.STRATEGY.resolution,
                        quantity=None,
                        # limit_price=ENTRY,
                        TP=[TP],
                        SL=SL,
                        confidence=baseConfidence,
                        periodUnfilled=5,
                        periodTillTp=10
                    ))
                else:
                    return self.returnResults(message="Asset is not shortable.")
            #     return self.returnResults(message="Insight already exists.")
        except Exception as e:
            return self.returnResults(success=False, message=str(e))
