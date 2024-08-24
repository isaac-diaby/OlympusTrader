
from typing import Optional
import numpy as np
import pandas as pd

from ..broker.interfaces import IOrderSide
from ..alpha.base_alpha import BaseAlpha
from ..insight.insight import Insight, StrategyDependantConfirmation


class RSIDiverganceAlpha(BaseAlpha):
    """
    ### RSI Divergance Alpha
    This alpha model generates insights based on RSI Divergance.

    :param strategy (BaseStrategy): The strategy instance
    :param local_window (int): The window to consider for local swing points
    :param divergance_window (int): The window to consider for divergance
    :param atrPeriod (int): The period for the ATR indicator
    :param rsiPeriod (int): The period for the RSI indicator
    :param baseConfidenceModifierField (str): The field to use for modifying the base confidence

    Author:
        @isaac-diaby

    """
    local_window: int
    divergance_window: int

    atrColumn: str
    rsiColumn: str

    def __init__(self, strategy, local_window=36, divergance_window=50, atrPeriod=14, rsiPeriod=14, baseConfidenceModifierField=None):
        super().__init__(strategy, "RSI_DIVERGANCE", "0.2", baseConfidenceModifierField)
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
            # v0.1
            # Compute Local Points of Control
            # self.computeLocalPointsOfControl(symbol)

            # Compute Local Swing Points
            self.computeLocalSwingPoints(symbol)

            # Check if we should even consider we have a divergance if we just closed on a pivot point (new high or low)
            if (np.isnan(self.STRATEGY.HISTORY[symbol]['higher_high'].iloc[-1]) and np.isnan(self.STRATEGY.HISTORY[symbol]['lower_low'].iloc[-1])):
                return self.returnResults()
            
            # Debugging
            # print(self.STRATEGY.HISTORY[symbol]
            #       [['higher_high', 'lower_low']].tail(2))

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
        
    # V0.2
    def computeLocalSwingPoints(self, symbol: str):
        window = self.STRATEGY.state['local_window']
        history = self.get_history(symbol)
        high_col = 'high'
        low_col = 'low'
        
        # Focus on the latest window of data
        recent_history = history.iloc[-window:]
        
        # Initialize columns in STRATEGY.HISTORY if they don't exist
        for col in ['higher_high', 'lower_low', 'lower_high', 'higher_low']:
            if col not in self.STRATEGY.HISTORY[symbol].columns:
                self.STRATEGY.HISTORY[symbol][col] = np.nan
        
        # Identify swing points
        higher_high = recent_history[high_col].iloc[-1] > recent_history[high_col].iloc[:-1].max()
        lower_low = recent_history[low_col].iloc[-1] < recent_history[low_col].iloc[:-1].min()
        lower_high = (recent_history[high_col].iloc[-1] < recent_history[high_col].iloc[:-1].max()) and \
                    (recent_history[high_col].iloc[-1] > recent_history[high_col].iloc[-2])
        higher_low = (recent_history[low_col].iloc[-1] > recent_history[low_col].iloc[:-1].min()) and \
                    (recent_history[low_col].iloc[-1] < recent_history[low_col].iloc[-2])
        
        # Update STRATEGY.HISTORY for the latest point
        latest_index = (symbol, recent_history.index[-1])
        
        if higher_high:
            self.STRATEGY.HISTORY[symbol].loc[latest_index, 'higher_high'] = recent_history[high_col].iloc[-1]
        if lower_low:
            self.STRATEGY.HISTORY[symbol].loc[latest_index, 'lower_low'] = recent_history[low_col].iloc[-1]
        if lower_high:
            self.STRATEGY.HISTORY[symbol].loc[latest_index, 'lower_high'] = recent_history[high_col].iloc[-1]
        if higher_low:
            self.STRATEGY.HISTORY[symbol].loc[latest_index, 'higher_low'] = recent_history[low_col].iloc[-1]
        
        return history
    

    def computeRSIDivergance(self, symbol: str):
        window = self.STRATEGY.state['divergance_window']
        # remove first 14 rows for RSI Warmup
        history = self.STRATEGY.HISTORY[symbol]
        # history = self.get_history(symbol)
        IRSI = history[self.rsiColumn]

        if 'RSI_Divergance_Long' not in history.columns:
            # Bullish Divergance - RSI is Increasing while price is Decreasing
            history['RSI_Divergance_Long'] = np.nan
        if 'RSI_Divergance_Short' not in history.columns:
            # Bearish divergence - RSI is Decreasing while price is Increasing
            history['RSI_Divergance_Short'] = np.nan


        if pd.notna(history['lower_low'].iloc[-1]):
            # only use local lows of point of control for reversal
            longPivot = history['lower_low'].dropna()
            # longPivot = history['local_min_poc'].dropna()
            lowerLowsPivots = longPivot.loc[longPivot.shift(1) > longPivot]

            for index, price in lowerLowsPivots[-1:-window:-1].items():
                _, *previousLocalPoC = longPivot.loc[index: (index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
                if (len(previousLocalPoC) == 0):
                    continue
                lastLowIndex, lastPrice = previousLocalPoC[0]
                if (IRSI[lastLowIndex] < IRSI[index]):
                    self.STRATEGY.history[symbol].loc[index, [
                        'RSI_Divergance_Long']] = lastPrice-price

        if pd.notna(history['higher_high'].iloc[-1]):
            # only use local maximas of point of control for reversal
            shortPivot = history['higher_high'].dropna()
            # shortPivot = history['local_max_poc'].dropna()
            higherHighsPivots = shortPivot.loc[shortPivot.shift(1) < shortPivot]

            for index, price in higherHighsPivots[-1:-window:-1].items():
                _, *previousLocalPoC = shortPivot.loc[index: (index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
                if (len(previousLocalPoC) == 0):
                    continue
                lastHighIndex, lastPrice = previousLocalPoC[0]
                if (IRSI[lastHighIndex] > IRSI[index]):
                    self.STRATEGY.history[symbol].loc[index, [
                        'RSI_Divergance_Short']] = price-lastPrice

        return history


    # V0.1
    # def computeLocalSwingPoints(self, symbol: str):
    #     window = self.STRATEGY.state['local_window']
    #     history = self.get_history(symbol)
    #     high_col = 'high'
    #     low_col = 'low'
        
    #     # Create a new DataFrame to store the results
    #     swing_points = pd.DataFrame(index=history.index, columns=['higher_high', 'lower_low', 'lower_high', 'higher_low'])
        
    #     for i in range(window, len(history) - window):
    #         current_index = history.index[i]
            
    #         # Check for higher high
    #         if (history[high_col].iloc[i] > history[high_col].iloc[i-window:i].max() and 
    #             history[high_col].iloc[i] > history[high_col].iloc[i+1:i+window+1].max()):
    #             swing_points.loc[current_index, 'higher_high'] = history[high_col].iloc[i]
            
    #         # Check for lower low
    #         if (history[low_col].iloc[i] < history[low_col].iloc[i-window:i].min() and 
    #             history[low_col].iloc[i] < history[low_col].iloc[i+1:i+window+1].min()):
    #             swing_points.loc[current_index, 'lower_low'] = history[low_col].iloc[i]
            
    #         # Check for lower high
    #         if (history[high_col].iloc[i] < history[high_col].iloc[i-window:i].max() and 
    #             history[high_col].iloc[i] > history[high_col].iloc[i+1:i+window+1].max()):
    #             swing_points.loc[current_index, 'lower_high'] = history[high_col].iloc[i]
            
    #         # Check for higher low
    #         if (history[low_col].iloc[i] > history[low_col].iloc[i-window:i].min() and 
    #             history[low_col].iloc[i] < history[low_col].iloc[i+1:i+window+1].min()):
    #             swing_points.loc[current_index, 'higher_low'] = history[low_col].iloc[i]
        
    #     # Handle the last window of data
    #     last_index = history.index[-1]
    #     last_window = history.iloc[-window:]
        
    #     if last_window[high_col].iloc[-1] == last_window[high_col].max():
    #         swing_points.loc[last_index, 'higher_high'] = last_window[high_col].iloc[-1]
        
    #     if last_window[low_col].iloc[-1] == last_window[low_col].min():
    #         swing_points.loc[last_index, 'lower_low'] = last_window[low_col].iloc[-1]
        
    #     # Update the STRATEGY.HISTORY DataFrame
    #     for col in swing_points.columns:
    #         self.STRATEGY.HISTORY[symbol][col] = swing_points[col]
        
    #     return history

    # def computeLocalPointsOfControl(self, symbol: str):
    #     window = self.STRATEGY.state['local_window']
    #     history = self.get_history(symbol)
    #     viewColumn = 'close'
    #     self.STRATEGY.HISTORY[symbol].loc[[symbol], ['local_max_poc']] = history[viewColumn][(
    #         history[viewColumn].shift(window) < history[viewColumn]) & (history[viewColumn].shift(-window) < history[viewColumn]
    #                                                                     )]
    #     self.STRATEGY.HISTORY[symbol].loc[[symbol], ['local_min_poc']] = history[viewColumn][(
    #         history[viewColumn].shift(window) > history[viewColumn]) & (history[viewColumn].shift(-window) > history[viewColumn]
    #                                                                     )]
    #     return history

    # def computeRSIDivergance(self, symbol: str):
    #     window = self.STRATEGY.state['divergance_window']
    #     # remove first 14 rows for RSI Warmup
    #     history = self.get_history(symbol)
    #     IRSI = history[self.rsiColumn]

    #     # Bullish Divergance - RSI is Increasing while price is Decreasing
    #     self.STRATEGY.history[symbol].loc[[symbol],
    #                                       ['RSI_Divergance_Long']] = np.nan

    #     # only use local lows of point of control for reversal
    #     longPivot = history['lower_low'].dropna()
    #     # longPivot = history['local_min_poc'].dropna()
    #     lowerLowsPivots = longPivot.loc[longPivot.shift(1) > longPivot]

    #     for index, price in lowerLowsPivots[-1:-window:-1].items():
    #         _, *previousLocalPoC = longPivot.loc[index: (
    #             index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
    #         if (len(previousLocalPoC) == 0):
    #             continue
    #         lastLowIndex, lastPrice = previousLocalPoC[0]
    #         if (IRSI.loc[lastLowIndex] < IRSI.loc[index]):
    #             self.STRATEGY.history[symbol].loc[index, [
    #                 'RSI_Divergance_Long']] = lastPrice-price

    #     # Bearish divergence - RSI is Decreasing while price is Increasing
    #     self.STRATEGY.history[symbol].loc[[symbol],
    #                                       ['RSI_Divergance_Short']] = np.nan

    #     # only use local maximas of point of control for reversal
    #     shortPivot = history['higher_high'].dropna()
    #     # shortPivot = history['local_max_poc'].dropna()
    #     higherHighsPivots = shortPivot.loc[shortPivot.shift(1) < shortPivot]

    #     for index, price in higherHighsPivots[-1:-window:-1].items():
    #         _, *previousLocalPoC = shortPivot.loc[index: (
    #             index[0], self.STRATEGY.resolution.add_time_increment(index[1], -2)): -1].items()
    #         if (len(previousLocalPoC) == 0):
    #             continue
    #         lastHighIndex, lastPrice = previousLocalPoC[0]
    #         if (IRSI.loc[lastHighIndex] > IRSI.loc[index]):
    #             self.STRATEGY.history[symbol].loc[index, [
    #                 'RSI_Divergance_Short']] = price-lastPrice

    #     return history
