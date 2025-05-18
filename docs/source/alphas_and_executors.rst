Alphas and Executors
====================

This page explains Alpha Models and Executors in OlympusTrader, how to implement them, and how to use them in your strategies. Links to the relevant base classes are also included for reference.

Alpha Models
------------
Alpha models are responsible for generating trade ideas ("insights") based on your strategy's logic, technical indicators, or other signals. Each alpha model should inherit from :class:`OlympusTrader.alpha.base_alpha.BaseAlpha`.

**Typical Alpha Model responsibilities:**
- Analyze historical and/or live data
- Generate buy/sell/hold signals (insights) with confidence scores, expiry, etc.
- Specify required indicators and their parameters

**Example Alpha Model:**

.. code-block:: python

   from OlympusTrader.alpha.base_alpha import BaseAlpha

   class MyAlpha(BaseAlpha):
       def generate(self, symbol, data):
           if data['close'][-1] > data['close'].rolling(20).mean()[-1]:
               return self.create_insight(symbol, direction='long', confidence=0.8)
           return None

**Adding Alpha Models to a Strategy:**

.. code-block:: python

   from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha
   strategy.add_alphas([
       EMAPriceCrossoverAlpha(strategy, emaPeriod=9),
   ])

**Base class reference:**
- :class:`OlympusTrader.alpha.base_alpha.BaseAlpha`

Executors
---------
Executors are responsible for handling the execution and life cycle of insights. They determine how and when to submit orders, manage open positions, apply risk management, and handle state transitions (e.g., from NEW to FILLED, REJECTED, CLOSED, etc.). Executors inherit from :class:`OlympusTrader.insight.executors.base_executor.BaseExecutor`.

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

Strategy `start` and `init` Examples
------------------------------------
The `start` method is called once at the beginning of your strategy and is the recommended place to add your alphas and executors. The `init` method is called once per asset in your universe and is useful for per-asset setup (e.g., initializing state or loading data).

.. code-block:: python

   from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha
   from OlympusTrader.insight.executors.filled.basicTakeProfit import BasicTakeProfitExecutor
   from OlympusTrader import Strategy

   class MyStrategy(Strategy):
       def start(self):
           # Add alphas and executors here
           self.add_alphas([
               EMAPriceCrossoverAlpha(self, emaPeriod=9),
           ])
           self.add_executors([
               BasicTakeProfitExecutor(self, take_profit=0.05),
           ])

       def init(self, asset):
           # Per-asset setup, called once for each asset in your universe
           self.state[asset] = {'custom_var': 0}
           # You can also load historical data, set up indicators, etc.

**Base class reference:**
- :class:`OlympusTrader.insight.executors.base_executor.BaseExecutor`
