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

Core Concepts
-------------

- **Insight:** A trade idea (entry/exit, price, quantity, confidence, expiry, risk, etc.)
- **Alpha:** Model that generates insights (signals). Inherit from ``BaseAlpha``.
- **Executor:** Handles execution and state transitions for insights. Inherit from ``BaseExecutor``.
- **Strategy:** Main user class. Orchestrates data, alphas, executors, and brokers.
- **Broker:** Abstracted trading interface (Alpaca, MT5, etc.)
- **Risk Management:** Built-in at both strategy and insight level.

Usage Example
-------------

See :doc:`getting_started` for a full code example and step-by-step walkthrough.

Contributing
------------

- Fork and submit a PR for new Alphas, Executors, or Brokers
- Follow community guidelines: modular, customizable, and well-documented code
- See CONTRIBUTING.md (if available) or open an issue for questions
