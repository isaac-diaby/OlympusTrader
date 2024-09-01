Getting Started
===============

Installation
------------
To install OlympusTrader, run the following command:

.. code-block:: bash

   pip install olympustrader

.. note::
   OlympusTrader requires Python 3.12 or higher and TA-Lib. You can install TA-Lib using the following instrustions on the `TA-Lib website <https://ta-lib.org/install/>`_.

Usage
-----
To use OlympusTrader, you need to have the following configured:

-  Create a strategy class that inherits from the `OlympusTrader.strategy.strategy` class.
- Implement the following methods in your strategy class:
   -  start: This is the first method that runs when your strategy starts. You can use it to load models or set base variables for your strategy.
   -  init: This is the method that runs for each asset in the universe. You can use it to set asset-specific variables and load historical data for each asset.
   -  universe: This is the method that returns the universe of assets that you want to trade. You can use it scan for assets or set a static Set list of assets that you want to trade.
   -  on_bar: This is the method that runs for each incoming bar in the universe.
   -  generateInsights: This is the method that generates insights for your strategy.
   -  executeInsight: This is the method that executes and manages insights that are generated.
   -  teardown: This is the method that runs when your strategy is done. (optional)
- Instantiate a broker class that will be used to execute trades. OlympusTrader comes with a AlpacaBroker class that you can use to trade on Alpaca. 

.. note::
    If you want to use a different broker that is not yet supported, you can create your own broker class that inherits from the OlympusTrader.Broker class. But we will be rolloing out support for more brokers in the future.

- Add events to your strategy using the add_events method. strategy.add_events('bar') will add the bar event to your strategy for all loaded assets in your universe with your timeframe resolution.

.. note::
    If your looking to add bar events on a different timeframe, you can use the add_events method with the timeframe resolution you want. strategy.add_events('bar', time_frame = TimeFrame(1, TimeFrameUnit.Minute)) will add the featured bar event to your strategy for all loaded assets in your universe with a 1 minute timeframe resolution as "<symbol>.1Min". however, the `on_bar` method will still be called for all assets in your universe with the default strategy timeframe resolution.

- Run your strategy using the run method.

Here is an example of a simple strategy:

.. code-block:: python

   import OlympusTrader
   from OlympusTrader import TimeFrame, TimeFrameUnit, InsightState, IOrderSide

   class  MyStrategy(OlympusTrader.Strategy):

      def  start(self):
         # Your strategy starting point is the first thing that runs and only runs once so you can use it to load models or set base variables
         # Executos, Alphas, and other models should be added here
         pass

      def  init(self,  asset):
         # Your strategy init point for each asset in the universe
         state = self.state
         pass



      def  universe(self):
         # The universe of assets that you want to trade
         universe =  {'BTC/USD',  'ETH/USD',  'TSLA'}
         return universe



      def  on_bar(self,  symbol,  bar):
         pass



      def  generateInsights(self,  symbol:  str):
         # Generate insights for your strategy. This is run after the on_bar function
         myInsight = OlympusTrader.Insight(IOrderSide.BUY,  symbol, "ExampleStrategyType",  self.resolution, 1.0)
         self.add_insight(myInsight)
         pass



      def  executeInsight(self,  insight):
         for i, insight in  enumerate(self.insights[symbol]):
            match insight.state:
               case InsightState.NEW:
                  # How to execution new insights that are generated
                  pass

               case InsightState.FILLED:
                  # How to manage open insights
                  pass

               # ... other cases
               case _:
                  pass



      def  teardown(self):
         pass
         # Close all open positions and pending orders om tear down
         self.broker.close_all_positions()



   if __name__ ==  "__main__":
      broker = OlympusTrader.AlpacaBroker(paper=True)  # Set your broker and paper to True for a demo account
      strategy = MyStrategy(broker,  {},  resolution=TimeFrame(1, TimeFrameUnit.Minute),  ui=True)  # Set your strategy resolution and ui to True to use the Streamlit dashboard
      strategy.add_events('bar')  # Add events to your strategy
      strategy.run()  # To run your live/ demo account trade


Where are my bar data stored?
-----------------------------

Historical and received bar data for each asset will be stored in the strategy.history dictionary and can be accessed using the symbol as the key. For example, strategy.history['BTC/USD'] will return the historical data for the BTC/USD asset as a multi-index pandas DataFrame with the following columns: 'open', 'high', 'low', 'close', 'volume'.



.. toctree::
   :maxdepth: 2
   :caption: Contents:

