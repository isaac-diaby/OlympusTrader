Getting Started
===============

Installation
------------
To install OlympusTrader, run:

.. code-block:: bash

   pip install olympustrader

Optional extras:

.. code-block:: bash

   pip install olympustrader[talib]       # For TA-Lib indicator support
   pip install olympustrader[metatrader]  # For MetaTrader5 broker support

.. note::
   OlympusTrader requires Python 3.12 or higher. For TA-Lib, see the `TA-Lib website <https://ta-lib.org/install/>`_ for system requirements.

Docker Usage
------------
You can run the framework and UI using Docker:

.. code-block:: bash

   STRATEGY=MyStrategy docker compose up

Set up your `.env` file with broker credentials (e.g. ``ALPACA_API_KEY``, ``ALPACA_SECRET_KEY``).

Project Structure
-----------------
- ``OlympusTrader/`` - Core framework
  - ``alpha/`` - Alpha models (signal generators)
  - ``broker/`` - Broker integrations
  - ``insight/`` - Insights and Executors logic
  - ``strategy/`` - Strategy base classes
  - ``utils/`` - Utilities (timeframes, state, etc.)
- ``strategies/`` - Example/user strategies
- ``backtests/``, ``data/``, ``examples/`` - Supporting files

Core Concepts
-------------
- **Insight:** A trade idea (entry/exit, price, quantity, confidence, expiry, risk, etc.)
- **Alpha:** Model that generates insights (signals). Inherit from ``BaseAlpha``.
- **Executor:** Handles execution and state transitions for insights. Inherit from ``BaseExecutor``.
- **Strategy:** Main user class. Orchestrates data, alphas, executors, and brokers.
- **Broker:** Abstracted trading interface (Alpaca, MT5, etc.)
- **Risk Management:** Built-in at both strategy and insight level.

Alpha Models
============
Alpha models are responsible for generating trade ideas ("insights") based on your strategy's logic, technical indicators, or other signals. Each alpha model should inherit from ``BaseAlpha`` and can use any data or indicators you need (e.g., via pandas-ta or TA-Lib). Alphas are modular and can be reused or contributed by the community.

**Typical Alpha Model responsibilities:**
- Analyze historical and/or live data
- Generate buy/sell/hold signals (insights) with confidence scores, expiry, etc.
- Specify required indicators and their parameters

**Example Alpha Model:**

.. code-block:: python

   from OlympusTrader.alpha.base_alpha import BaseAlpha

   class MyAlpha(BaseAlpha):
       def generate(self, symbol, data):
           # Example: simple moving average crossover
           if data['close'][-1] > data['close'].rolling(20).mean()[-1]:
               return self.create_insight(symbol, direction='long', confidence=0.8)
           return None

**Adding Alpha Models to a Strategy:**

.. code-block:: python

   from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha
   strategy.add_alphas([
       EMAPriceCrossoverAlpha(strategy, emaPeriod=9),
   ])

Executors
=========
Executors are responsible for handling the execution and life cycle of insights. They determine how and when to submit orders, manage open positions, apply risk management, and handle state transitions (e.g., from NEW to FILLED, REJECTED, CLOSED, etc.). Executors inherit from ``BaseExecutor`` and can be customized for different workflows.

**Typical Executor responsibilities:**
- Submit orders to the broker when an insight is generated
- Manage stop-loss, take-profit, and other exit logic
- Handle order fills, rejections, and cancellations
- Apply custom risk or portfolio management logic

**Example Executor:**

.. code-block:: python

   from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
   strategy.add_executors([
       BasicTakeProfitExecutor(strategy, take_profit=0.05),
   ])

You can add multiple executors to your strategy, each handling different insight states or trading scenarios. Executors are run after your ``executeInsight`` function and can be customized or extended as needed.

Usage Example: Your First Strategy
----------------------------------

.. code-block:: python

   from OlympusTrader.utils.insight import Insight, InsightState
   from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
   from OlympusTrader import AlpacaBroker, Strategy

   class MyStrategy(Strategy):
       def start(self):
           # Initialization logic, add Alphas/Executors here
           pass

       def init(self, asset):
           # Per-asset setup
           pass

       def universe(self):
           return {'BTC/USD', 'ETH/USD', 'TSLA'}

       def on_bar(self, symbol, bar):
           # Called on each new bar
           pass

       def generateInsights(self, symbol: str):
           # Generate trade ideas
           pass

       def executeInsight(self, insight: Insight):
           # Handle execution logic for each insight
           pass

       def teardown(self):
           self.BROKER.close_all_positions()

   if __name__ == "__main__":
       broker = AlpacaBroker(paper=True)
       strategy = MyStrategy(broker, {}, resolution=TimeFrame(1, TimeFrameUnit.Minute), ui=True)
       strategy.add_events('bar')
       strategy.run()

Backtesting Example
-------------------

.. code-block:: python

   from datetime import datetime
   from OlympusTrader import PaperBroker, IStrategyMode

   broker = PaperBroker(cash=1_000_000, start_date=datetime(2024, 5, 27), end_date=datetime(2024, 5, 31))
   strategy = MyStrategy(broker, variables={}, resolution=TimeFrame(1, TimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.BACKTEST)
   strategy.add_events('bar', stored=True, stored_path='data', start=broker.START_DATE, end=broker.END_DATE)

For more examples, see the :doc:`insights` and module documentation.


.. code-block:: python

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

