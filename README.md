# Welcome to OlympusTrader

  [![Documentation Status](https://readthedocs.org/projects/olympustrader/badge/?version=latest)](https://olympustrader.readthedocs.io/en/latest/?badge=latest)
  [![PyPI version](https://badge.fury.io/py/olympustrader.svg)](https://badge.fury.io/py/olympustrader)
  [![Downloads](https://pepy.tech/badge/olympustrader)](https://pepy.tech/project/olympustrader)

This is my implementation of a quant trading framework inspired by frameworks such as QuantConnect and Blankly. The main idea is to create a workflow that allows users to create their trading strategy and execute complex trades with dependencies and a Risk-first approach. The core components are Insights(potential trade idea) which can have dynamic components such as:

- How to enter
- What price to enter
- Quantity
- How long should it be kept alive (expires) filled or unfilled
- Its confidence score
- Multiple take profit level (with adjustable risk)
- and much more

The base strategy class manages everything else:

- Getting the latest bar price for your timeframe and featured timeframes (multi-timeframe support)
- Manages and tracking open and closed positions
- Execution of Alpha models, Executors, your Strategy core functions such as start(), init(), generateInsight(),

Feel free to fork the project if you want to add a new broker or anything you want and submit a PR - right now I just made it to use alpaca-py.

## In Progress

- [ ] Add more brokers support
  - [ ] Binance
  - [ ] Trade Locker
  - [ ] Interactive Brokers
  - [ ] Hyper Liquid
  - [x] MT5 - MetaTrader5

- [x] Dashboard
- [x] Multiple timeframe support
- [x] Backtesting

## OlympusTrader

To get started you can look at the main.py file for my strategy for the general workflow.

**Requirement** are: `pip install olympustrader`. Or run `docker compose up` to get both the UI and main.py script to run in a container (for deploy).

Create a .env file for your environment variables as of now the only available broker is alpaca so you will need to set ALPACA_API_KEY and ALPACA_SECRET_KEY in the .env file.

```py

from OlympusTrader.utils.insight import Insight, StrategyTypes, InsightState
from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
from OlympusTrader import AlpacaBroker, Strategy

class  QbitTB(Strategy):

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
  # Your strategy, TA's and other functions should be called here
  pass



 def  generateInsights(self,  symbol:  str):
  # Generate insights for your strategy. This is run after the on_bar function
  #  self.add_insight(...
  pass



 def  executeInsight(self,  insight: Insight):



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

self.BROKER.close_all_positions()



if __name__ ==  "__main__":
 broker = AlpacaBroker(paper=True)  # Set your broker and paper to True for a demo account
 strategy = QbitTB(broker,  {},  resolution=TimeFrame(1, TimeFrameUnit.Minute),  ui=True)  # Set your strategy resolution and ui to True to use the Streamlit dashboard
 strategy.add_events('bar')  # Add events to your strategy
 strategy.run()  # To run your live/ demo account trade

```

## That easy to get started

The `strategy.add_events('bar')` function is used to add events to your strategy. We have plans for more events such as quotes, multi-timeframe and news evntsin the future but for now, we only have bar events for your current strategy resolution.

If you want to get started with backtesting your strategy you can use the backtest flag and the PaperBroker - with the same code!

```py

broker = PaperBroker(cash=1_000_000,  start_date=datetime(2024,  5,  27),  end_date=datetime(2024,  5,  31))
strategy = QbitTB(broker,  variables={},  resolution=TimeFrame(1, TimeFrameUnit.Minute),  verbose=0,  ui=True,  mode=IStrategyMode.BACKTEST)
strategy.add_events('bar',  stored=True,  stored_path='data', start=broker.START_DATE,  end=broker.END_DATE)

```

## Alpha Models

The framework is designed to be flexible and allow you to build simple to complex strategies with dependencies and a risk-first approach. You could use the generateInsights(self, symbol: str) function to generate your models or use our community models that we will be adding over time to the framework. Feel free to make a PR if you have a model you want to add just make sure that it inherits the BaseAlpha in `OlympusTrader.alpha.base_alpha.py`.

Another added benefit of using Alpha models is that it each alpha model should include the right indicators that it requirers via Pandas_Ta in order to be able to function correctly. This would also include the default params of the indicators and set the `strategy.warm_up(int)` value accordingly. Each indicator that a Alpha model uses should be customisable and its part of the community guidelines for it to do so.

### Example of using an Alpha Model

```py

from OlympusTrader.alpha.test_entry import TestEntryAlpha
from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha


strategy.add_alphas([
 TestEntryAlpha(strategy),
 EMAPriceCrossoverAlpha(strategy,  atrPeriod=14,  emaPeriod=9,  baseConfidenceModifierField='market_state'),
])
```

Using the add_alphas function, you can add multiple alpha models from the community (or your own) to your strategy and they will be run before your own generateInsights function. You can read about what each alpha does in the `OlympusTrader.alpha` folder.

**Recommended**: You should add the alpha models in the `start()` function.

#### Alpha Results

Each alpha returns an AlphaResults object that tells you if the alpha was successful or not and the reason why it failed. You can use this to log the results of the alpha and make decisions based on the results. But by default, the framework will log the results of failed alphas for you and will always run your generateInsights function after the alphas are run.

## Executors Models

You can manually manage and execute your insights with the `executeInsight(self, insight: Insight)` function or use a set of executor models that the community add over time to the framework. Feel free to make a PR if you have a model you want to add just make sure that it inherits the BaseExecutor in `OlympusTrader.insight.executors.base_executor.py`.

### Example of using an Executor Model

```py

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

# New Executors

strategy.add_executors([
RejectExpiredInsightExecutor(strategy),
MarketOrderEntryPriceExecutor(strategy),
MinimumRiskToRewardExecutor(strategy),
DynamicQuantityToRiskExecutor(strategy),
CancelAllOppositeSidetExecutor(strategy)
])

# Executed Executors
RejectExpiredExecutedExecutor = RejectExpiredInsightExecutor(strategy)
RejectExpiredExecutedExecutor._override_state(InsightState.EXECUTED)
strategy.add_executors([
RejectExpiredExecutedExecutor,
])

# Cancelled Executors
strategy.add_executors([
DefaultOnCancelledExecutor(strategy),
])

# Filled Executors
strategy.add_executors([
CloseExhaustedInsightExecutor(strategy),
CloseMarketChangedExecutor(strategy),
BasicStopLossExecutor(strategy),
BasicTakeProfitExecutor(strategy)
])

# Closed Executors
strategy.add_executors([
DefaultOnClosedExecutor(strategy),
])

# Rejected Executors
strategy.add_executors([
DefaultOnRejectExecutor(strategy)
])

```

**Recommended**: You should add the executors models in the `start()` function.

You can add multiple executors to your strategy and they will be run after your executeInsight function. We do not execute or submit any insights as that should be done by the users for insights in the NEW state. As you can see you can add executors for different states of the insight such as filled, rejected, cancelled, executed and closed. This can all be done with the same add_executors function but we just added the different states for clarity. In some cases, you may want to override the state of the default state that the executor runs on - you can do this with the `_override_state` function. 

You can read about what each executor does in the `OlympusTrader.insight.executors` folder.

#### Executor Results

Each executor returns an ExecutorResults object that tells you if the executor was successful or not and the reason why it failed. You can use this to log the results of the executor and make decisions based on the results. But by default the framework will log the results of failed executors for you and skip the insight if it fails (eg if the insight is in the NEW state - based on the executor it may reject the insight).

## Documentation

The documentation is still in progress but you can find the documentation for the framework at [OlympusTrader](https://olympustrader.readthedocs.io/en/latest/)


## Collaborations

If you're interested in helping out just make a PR and ill happy to merge! I just to build a framework that is easy enough for people to build a live trading bot but flexible for users to to build complex strategies. Thanks

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=isaac-diaby/OlympusTrader&type=Timeline)](https://star-history.com/#isaac-diaby/OlympusTrader&Timeline)
