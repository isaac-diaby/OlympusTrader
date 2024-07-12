# Welcome to OlympusTrader!

This is my implementation of a quant trading framework inspired by frameworks such as QuantConnect and Blankly. The main idea is to create a workflow that allows users to create their own trading strategy and execute complex trades with dependancies and a Risk first approach.

Feel free to fork the project if you want to add a new broker or anything you want - right now i just make it to use alpaca-py.

### TODO:

- [ ] Add more brokers

  - [ ] CCXT - hyperliquid
  - [ ] MT5 - MetaTrader5

- [x] Feature - Add Alpha models for users to use in their strategies
- [x] Feature - Add Executor models for users manage their insights
- [x] Add support for managing open orders - mainly for strategies with continuation trades and not a simple TP/SL strategy.
- [x] Fix - Threaded WebSocket Streams close bugs - where it sometimes doesn't run the teardown command
- [x] Make a dashboard for ease of use to monitor the bots performance and open positions with streamlit

# OlympusTrader

To get started you can take a look at the main.py file for my own strategy for the general work flow.

**Requirement** are: `pip install -r requirement.txt` - to install dependencies.
and create a .env file for your environment variables as of now the only broker thats available is alpaca so you will need to set ALPACA_API_KEY and ALPACA_SECRET_KEY in the .env file.

```py
from OlympusTrader.utils.insight import Insight, StrategyTypes, InsightState
from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
from OlympusTrader import AlpacaBroker, Strategy

class  QbitTB(Strategy):
	def start(self):
		# Your strategy starting point first thing that runs and only runs once so you can use it to load models or set base variables
		pass
	def  init(self,  asset):
		# Your strategy init point for each asset in the universe
		state =  self.state
		pass

	def  universe(self):
		# The universe of assets that you want to trade
		universe = {'BTC/USD', 'ETH/USD', 'TSLA'}
		return universe

	def  on_bar(self,  symbol,  bar):
		# Your strategy, self.insights[symbol].append(Insight(YOUR INSIGHT DATA))
		pass

	def generateInsights(self, symbol: str):
		# Generate insights for your strategy. this is ran after the on_bar function
		pass

	def  executeInsight(self,  insight: Insight):

		for i, insight in  enumerate(self.insights[symbol]):
			match insight.state:
				case InsightState.NEW:
					# how to execution new insights that are generated
					pass
				case InsightState.FILLED:
					# how to manage open insights
					pass
				# ... other cases
				case _:
					pass

	def  teardown(self):
		# Close all open positions and pending orders om tear down
		self.BROKER.close_all_positions()

if __name__ ==  "__main__":
	broker = AlpacaBroker(paper=True) # Set your broker  and paper to True for a demo account

	strategy = QbitTB(broker,  {},  resolution=TimeFrame(1, TimeFrameUnit.Minute),  ui=True) # Set your strategy resolution and ui to True to use the streamlit dashboard
	strategy.add_events('bar') # Add events to your strategy
	strategy.run() # To run your live/ demo account trade
```

That easy to get started!
The strategy.add_events('bar') function is used to add events to your strategy. we have plans to more events such as quote in the future but for now we only have bar events for your current strategy resolution.

```py

If you want to get started with backtesting your strategy you can use the backtest flcg and the PaperBroker - with the same code!

```py
broker = PaperBroker(cash=1_000_000, start_date=datetime(2024, 5, 27), end_date=datetime(2024, 5, 31))
strategy = QbitTB(broker, variables={}, resolution=TimeFrame(
        1, TimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.BACKTEST)
# 
strategy.add_events('bar', stored=True, stored_path='data',
                        start=broker.START_DATE, end=broker.END_DATE)
```

## Alpha Models

The framework is designed to be flexible and allow you to build simple to complex strategies with dependencies and a risk first approach. You could use the generateInsights(self, symbol: str) function to generate your models or use our comunity models that we will be adding over time to the framework. Feel free to make a PR if you have a model you want to add just make sure that it inherit the BaseAlpha in OlympusTrader.alpha.base_alpha.py.

### Example of using a Aplha Model

```py
from OlympusTrader.alpha.test_entry import TestEntryAlpha
from OlympusTrader.alpha.ema_price_crossover import EMAPriceCrossoverAlpha

strategy.add_alphas([
        TestEntryAlpha(strategy)
        EMAPriceCrossoverAlpha(strategy, atrPeriod=14, emaPeriod=9, baseConfidenceModifierField='market_state'),
    ])
```

using the add_alphas function you can add multiple alpha models to your strategy and they will be ran before your own generateInsights function. you can read about what each alpha does in the OlympusTrader.alpha folder.

#### Alpha Results

Each alpha returns a AlphaResults object that tells you if the alpha was successful or not and the reason why it failed. you can use this to log the results of the alpha and make decisions based on the results. but by default the framework will log the results of failed alphas for you and will always run your generateInsights function after the alphas are ran.

## Executors Models

you can manaully manage and execute your insights with the executeInsight(self, insight: Insight) function or use a set of executor models that we will be adding over time to the framework. Feel free to make a PR if you have a model you want to add just make sure that it inherit the BaseExecutor in OlympusTrader.insight.executors.base_executor.py.

### Example of using a Executor Model

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

you can add multiple executors to your strategy and they will be ran after your own executeInsight function. we do not execute or submit any insights as that should be done by the users for insights in the NEW state. As you can see you can add executors for different states of the insight such as filled, rejected, cancelled, executed and closed. this can all be done with the same add_executors function but we just added the different states for clarity. Is some cases you may want to override the state of the insight to executed or cancelled so you can add the executor with the _override_state function. you can read about what each executor does in the OlympusTrader.insight.executors folder.

#### Executor Results

Each executor returns a ExecutorResults object that tells you if the executor was successful or not and the reason why it failed. you can use this to log the results of the executor and make decisions based on the results. but by default the framework will log the results of failed executors for you and skips the insight if it fails (eg if the insight is in the NEW state - based on the executor it may reject the insight).

## OlympusTrader.BaseStrategy => OlympusTrader.Strategy

The BaseStrategy has the for execution flow for a strategy but if you want to use it its recommended to use the Strategy class.
We will go over some important properties in the BaseStrategy

### Broker

`self.broker -> BaseBroker type`
This has the core API for the broker that you selected and allows you to get historical data, stream data, account information and execution trades.

### State

`self.state -> dict type`
Your variables and state of your strategy as a dict type.

### Account

`self.account ->  IAccount type `
Your account information such as currency, cash, buying power, allowed to short.

### Assets

`self.assets ->  dict[str, Asset] type `
Returns the metadata of assets that are in your univsere (stocks in play). includes the ticker, full name, if its tradable or shorting is enabled with your broker, the exchange, fraction shares is allowed.

### Insights

`self.insights ->  dict[str, Insight] type `
Returns your insights (possible trade entries).

### Positions

`self.positions ->  dict[str, IPosition] type `
Returns your open positions and includes information such as the average entry price, number of shares, market value, current price and the current profit/loss.

### Orders

`self.orders ->  List[IOrder] type `
Returns a list of orders placed/canceled/ filled and meta data around it.

## Start()

This function is called once at the start of the startegy. You can use this function to init your strategy set state via ` self.state` and load historiacal data for the secuity asset with `self.broker.get_history()`

## init()

This function is called for every asset in the universe at the start of the startegy. You can use this function to init your strategy set state via ` self.state` and load historiacal data for the secuity asset with `self.broker.get_history()`

## universe()

universe sets the security in play. Like quantconnect you can call this function to load assets data. it simply requires you to return a set of tickers that you want to load into your strategy. here you can build a stratey that filters the market to inly include specific requirement such as above average relative volume, market cap etc.

## on_bar()

Here you can build your strategy and call any functions you may need. in the main example i use pandas-ta to load my indicators and numpy to work on discovering RSI divergence in the price action. as mentioned this is my own strategy so ill be developing it further over-time as a starting point for future users of this framework.

### Insights

The idea here is to generate insights (potential entry points) in this function and create another function to consume the insights how you want to. Insights include information such as entry price, order type, stop lost, take profit, time to live unfilled / filled, confidence, risk to reward ratio, market dependencies (such as HRVCM = High relative volume confirmation, LRVCM = Low relative volume confirmation, etc you can set your own) and others you can take a look at the full list of the Insight class in OlympusTrader/utils/insight.py.

the framework is designed to be flexible and allow you to build complex strategies with dependencies and a risk first approach. we already track the account information and open positions so you can build a strategy that can manage open positions and pending orders via the state value of the insight.
we

## teardown()

The teardown function is called when you interrupt the program and can be used to close positions and pending orders when you want to stop the program.

# Collaborations

If your interested to help out just make a PR and ill happy to merge! i just to build a framework that is easy enough for people to build a live trading bot but flexile for users to to build complex strategies. Thanks
