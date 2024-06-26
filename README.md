# Welcome to OlympusTrader!

This is my implementation of a quant trading framework inspired by frameworks such as QuantConnect and Blankly.  The main idea is to create a workflow that allows users to create their own trading strategy and execute complex trades with dependancies and a Risk first approach. 

Feel free to fork the project if you want to add a new broker or anything you want - right now i just make it to use alpaca-py.

### TODO:

 - [ ] Make a dashboard for ease of use to monitor the bots performance and control the bot - with [dashly](https://plotly.com/) or some other alternative.
 - [ ] Add support for managing open orders - mainly for strategies with continuation trades and not a simple TP/SL strategy.
 - [ ] Fix - Threaded WebSocket Streams close bugs - where it sometimes doesn't run the teardown command  

# OlympusTrader

To get started you can take a look at the main.py file for my own strategy for the general work flow.

**Requirement** are:  ```pip install -r requirement.txt``` - to install dependencies. 
and create a .env file for your environment variables as of now the only broker thats available is alpaca so you will need to set ALPACA_API_KEY and ALPACA_SECRET_KEY in the .env file.

```py
from OlympusTrader.utils.insight import Insight, StrategyTypes, InsightState
from OlympusTrader.utils.timeframe import TimeFrame, TimeFrameUnit
from OlympusTrader import AlpacaBroker, Strategy

class  QbitTB(Strategy):
	def start(self): 
		# Your strategy start point first thing that runs 
		pass
	def  init(self,  asset):
		state =  self.state

		pass
		
	def  universe(self):
		# The universe of assets that you want to trade
		universe = {'BTC/USD', 'ETH/USD', 'TSLA'}
		return universe
		
	def  on_bar(self,  symbol,  bar):
		# Your strategy, self.insights[symbol].append(Insight(YOUR INSIGHT DATA))
		self.executeOrder(symbol)
		pass
		
	def  executeInsight(self,  symbol:  str):

		for i, insight in  enumerate(self.insights[symbol]):
			match insight.state:
				case InsightState.NEW:
					# how to execution new insights that are generated
				case InsightState.FILLED:
					# how to manage open insights
				# ... other cases
				case _:
					pass
					
	def  teardown(self):
		# Close all open positions and pending orders om tear down
		self.BROKER.close_all_positions()

if __name__ ==  "__main__":
	broker = AlpacaBroker(paper=True) # Set your broker  and paper to True for a demo account

	strategy = QbitTB(broker,  {},  resolution=TimeFrame(1, TimeFrameUnit.Minute),  ui=True) 
	strategy.add_events('bar')
	"""Add your broker, variables and resolution  to your strategy """
	strategy.run() # To run your live/ demo account trade 
```
That easy to get started !

if you want to get started with backtesting your  strategy you can use the backtest flcg and the PaperBroker - with the same code!

```py
broker = PaperBroker(cash=1_000_000, start_date=datetime(2024, 5, 27), end_date=datetime(2024, 5, 31))
    strategy = QbitTB(broker, variables={}, resolution=TimeFrame(
        1, TimeFrameUnit.Minute), verbose=0, ui=True, mode=IStrategyMode.BACKTEST)
```

## OlympusTrader.BaseStrategy  => OlympusTrader.Strategy
The BaseStrategy has the for execution flow for a strategy but if you want to use it its recommended to use the Strategy class. 
We will go over some important properties in the BaseStrategy
### Broker 
```self.broker -> BaseBroker type```
This has the core API for the broker that you selected and allows you to get historical data, stream data, account information and execution  trades.

### State 
```self.state -> dict type```
Your variables and state of your strategy as a dict type.

### Account 
```self.account ->  IAccount type ``` 
Your account information such as currency, cash, buying power, allowed to short.

### Assets 
```self.assets ->  dict[str, Asset] type ``` 
Returns the metadata of assets that are in your univsere (stocks in play). includes the ticker, full name, if its tradable or shorting is enabled with your broker, the exchange, fraction shares is allowed.

### Insights 
```self.insights ->  dict[str, Insight] type ``` 
Returns your insights (possible trade entries).

### Positions 
```self.positions ->  dict[str, IPosition] type ``` 
Returns your open positions and includes information such as the average entry price, number of shares, market value, current price and the current profit/loss. 

### Orders
```self.orders ->  List[IOrder] type ``` 
Returns a list of orders placed/canceled/ filled and meta data around it. 

## Start()
This function is called once at the start of the startegy. You can use this function to init your strategy set state via ``` self.state``` and load historiacal data for the secuity asset with ```self.broker.get_history()```

## init()
This function is called for every asset in the universe at the start of the startegy. You can use this function to init your strategy set state via ``` self.state``` and load historiacal data for the secuity asset with ```self.broker.get_history()```

## universe()
universe sets the security in play. Like quantconnect you can call this function to load assets data. it simply requires you to return a set of tickers that you want to load into your strategy. here you can build a stratey that filters the market to inly include specific requirement such as above average relative volume, market cap etc. 

## on_bar()
Here you can build your strategy and call any functions you may need. in the main example i use pandas-ta to load my indicators and numpy to work on discovering RSI divergence in the price action. as mentioned this is my own strategy so ill be developing it further over-time as a starting point for future users of this framework.  

### Insights 
The idea here is to generate insights (potential entry points) in this function and create another function to consume the insights how you want to. Insights include information such as entry price, order type, stop lost, take profit, time to live unfilled / filled, confidence, risk to reward ratio,  market dependencies (such as HRVCM = High relative volume confirmation, LRVCM = Low relative volume confirmation, etc  you can set your own) and others you can take a look at the full list of the Insight class in OlympusTrader/utils/insight.py. 

the framework is designed to be flexible and allow you to build complex strategies with dependencies and a risk first approach. we already track the account information and open positions so you can build a strategy that can manage open positions and pending orders via the state value of the insight.
we 

## teardown()

The teardown function is called when you interrupt the program and can be used to close positions and pending orders when you want to stop the program. 

# Collaborations 
If your interested to help out just make a PR and ill happy to merge! i just to build a framework that is easy enough for people to build a live trading bot but flexile for users to to build complex strategies. Thanks 

