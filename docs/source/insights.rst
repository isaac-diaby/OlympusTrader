========================
Insights Documentation
========================

Overview
========

The `Insight` class is a core component of the trading strategy framework. It represents a trading signal or idea that can be executed by the broker. Insights can be used to manage entry and exit orders, and they support hierarchical relationships where child insights become active only when the parent insight has been filled.

Creating an Insight
===================

To create an insight, you need to instantiate the `Insight` class with the required parameters. Here's an example:

.. code-block:: python
    from OlympusTrader.insight.insight import Insight
    from OlympusTrader.insight.insight import Insight
    from OlympusTrader.broker.interfaces import IOrderSide
    from OlympusTrader.utils.timeframe import ITimeFrame, ITimeFrameUnit

    # Create a timeframe object
    timeframe = ITimeFrame(5, ITimeFrameUnit.Minute)

    # Create a parent insight
    parent_insight = Insight(
        side=IOrderSide.BUY,
        symbol="AAPL",
        strategyType="MANUAL",
        tf=timeframe,
        quantity=10,
        limit_price=150.0,
        TP=[155.0],
        SL=145.0,
        confidence=0.8,
        periodUnfilled=5, 
        periodTillTp=10,
    )

.. note::
    The period unfilled (periodUnfilled) and period till TP (periodTillTp) parameters are optional and are used to set the number of periods that the insight remains unfilled and the number of periods until the take profit level is reached, respectively. The order will be canceled if the insight remains unfilled for the specified period. If the position is filled has not reached the take profit level after the specified period, the position will be closed.

Registering the Parent Insight
==============================

To register the parent insight, you must use the `add_insight` function. This function ensures that the parent insight is properly registered and can be executed by the broker.

.. code-block:: python

    from OlympusTrader.strategy import Strategy
    # Assuming you have a broker instance
    broker = Strategy()

    # Register the parent insight
    broker.add_insight(parent_insight)

Adding Child Insights
=====================

Child insights can be added to a parent insight. Child insights become active only when the parent insight has been filled. To add a child insight, use the `addChildInsight` method of the parent insight.

.. code-block:: python

    # Add a child insight to the parent insight
    child_insight = parent_insight.addChildInsight(
        side=IOrderSide.SELL,
        quantity=5,
        limit_price=160.0,
        TP=[165.0],
        SL=155.0
    )

    # Register the child insight (optional, as it will be managed by the parent insight)
    self.add_insight(child_insight)

Executing Insights
==================

Once the parent insight is registered, it can be executed by the strategy. The child insights will automatically become active when the parent insight is filled.

.. code-block:: python

    # Execute the parent insight and send it to the broker
    parent_insight.submit()

    # The child insight will become active when the parent insight is filled

Insight States
==============

Insights have various states that indicate their current status. The states are defined in the `InsightState` enum:

- `NEW`: The insight is newly created and has not been executed.
- `EXECUTED`: The insight has been executed and is waiting to be filled.
- `FILLED`: The insight has been filled.
- `CLOSED`: The insight has been closed.
- `CANCELED`: The insight has been canceled.
- `REJECTED`: The insight has been rejected.

.. code-block:: python
    
    from OlympusTrader.insight.insight import InsightState

    # Check the state of an insight
    if parent_insight.state == InsightState.FILLED:
        print("The parent insight has been filled.")

Conclusion
==========

The `Insight` class provides a powerful way to manage trading signals and their execution. By using parent and child insights, you can create complex trading strategies that depend on the successful execution of initial signals. Remember to always register the parent insight using the `add_insight` function and manage child insights appropriately.

.. toctree::
   :maxdepth: 2
   :caption: Contents: