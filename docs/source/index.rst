.. OlympusTrader documentation master file, created by
   sphinx-quickstart on Thu Aug 29 23:17:00 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

OlympusTrader Documentation
===========================

OlympusTrader is a flexible, modular, and risk-first quantitative trading framework for Python, inspired by QuantConnect and Blankly. It lets you build, test, and execute simple or complex trading strategies with powerful abstractions for signals (Alphas), trade ideas (Insights), execution logic (Executors), and broker integration.

.. note::
   This documentation is a work in progress. For questions or suggestions, email: olympustrader@isaacdiaby.tech

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting_started
   alphas_and_executors
   insights
   modules

Quick Start
-----------

**Install via pip:**

.. code-block:: bash

   pip install olympustrader

**Or use Docker:**

.. code-block:: bash

   STRATEGY=MyStrategy docker compose up

**Set up your environment:**

- Create a `.env` file with your broker credentials (e.g. `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`).
- Supported brokers: Alpaca (live/paper), MetaTrader5, more coming soon.

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

Key Components
--------------

1. Insights (``Insight``)
^^^^^^^^^^^^^^^^^^^^^^^^^

An **Insight** represents a trade idea or a signal. It is the core unit of information that moves through the system.

- **Purpose**: To define *what* to trade, *how* (buy/sell), *when* (now/limit), and *parameters* (TP/SL, quantity, confidence).
- **Key Attributes**:
    - ``symbol``: The asset to trade.
    - ``side``: ``BUY`` or ``SELL``.
    - ``state``: The current status (``NEW``, ``FILLED``, ``EXECUTED``, ``CANCELED``, ``REJECTED``, ``CLOSED``).
    - ``limit_price``, ``stop_price``: For entry orders.
    - ``TP`` (Take Profit), ``SL`` (Stop Loss): Risk management parameters.
    - ``confidence``: A score (0-1) indicating the strength of the signal.
    - ``periodUnfilled``: Time-to-live for the order before it expires.
- **Lifecycle**: An Insight starts as ``NEW``, moves to ``EXECUTED`` (when submitted to broker), then ``FILLED`` (when trade happens), and finally ``CLOSED`` (when position is exited).

2. Alpha Models (``BaseAlpha``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An **Alpha Model** is responsible for generating **Insights**.

- **Purpose**: To analyze market data (price, volume, indicators) and produce trade signals.
- **Key Methods**:
    - ``generateInsights(symbol)``: The main method where your logic lives. It returns an ``AlphaResults`` object containing an ``Insight`` if a signal is found.
    - ``start()``: Run once at the beginning to initialize models or load data.
    - ``init(asset)``: Run for each asset to set up asset-specific variables.
- **Usage**: You can have multiple Alpha models in a strategy, and they can be specific to certain assets.

3. Executors (``BaseExecutor``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An **Executor** is responsible for **managing** the execution of Insights.

- **Purpose**: To decide *how* and *when* to act on an Insight based on its state. It handles the logistics of placing orders, managing stops/limits, and handling cancellations.
- **Key Methods**:
    - ``run(insight)``: Evaluates an Insight and performs actions (like submitting an order to the broker).
- **Types**:
    - **New Executors**: Handle ``NEW`` insights (e.g., ``MarketOrderEntryPriceExecutor``).
    - **Filled Executors**: Handle ``FILLED`` insights (e.g., ``BasicStopLossExecutor``, ``BasicTakeProfitExecutor``).
    - **Cancelled/Rejected Executors**: Handle cleanup or retry logic.
- **Philosophy**: Separates the *signal* (Alpha) from the *execution* (Executor), allowing you to swap execution logic (e.g., market vs. limit orders) without changing the strategy logic.

How they work together
^^^^^^^^^^^^^^^^^^^^^^

1.  **Strategy**: The orchestrator. It defines the universe of assets and runs the loop.
2.  **Alpha**: Analyzes data and emits an **Insight** (State: ``NEW``).
3.  **Executor**: Picks up the ``NEW`` Insight and submits it to the **Broker** (State becomes ``EXECUTED``).
4.  **Broker**: Fills the order (State becomes ``FILLED``).
5.  **Executor**: Monitors the ``FILLED`` Insight and manages exit logic (TP/SL) to eventually close it (State becomes ``CLOSED``).

Usage Example
-------------

See :doc:`getting_started` for a full code example and step-by-step walkthrough.

Contributing
------------

- Fork and submit a PR for new Alphas, Executors, or Brokers
- Follow community guidelines: modular, customizable, and well-documented code
- See CONTRIBUTING.md (if available) or open an issue for questions
