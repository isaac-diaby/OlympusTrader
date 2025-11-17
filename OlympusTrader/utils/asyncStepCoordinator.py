import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class AsyncStepCoordinator:
    """
    Coordinates a fixed pipeline of phases per timestep:
      - 'market'  -> all asset producers call report('market')
      - 'insight' -> insight listener reports once
      - 'trade'   -> trade stream reports once

    Usage:
      coord = AsyncStepCoordinator(market_parties=N)
      # market producers call await coord.report_and_wait_next('market') OR
      #    await coord.report('market') then await coord.wait_for_phase('trade')
      # insight listener: await coord.wait_for_phase('market'); process; await coord.report('insight')
      # trade stream: await coord.wait_for_phase('insight'); process; await coord.report('trade')
    """
    def __init__(self, market_parties: int, timeout: float | None = None):
        self.market_parties = max(0, int(market_parties))
        self.timeout = timeout

        self._lock = asyncio.Lock()
        self._reset_for_step()

        self._closed = False
    
    def _reset_for_step(self):
        # counters for a new timestep
        self._market_count = 0
        self._market_event = asyncio.Event()
        self._insight_event = asyncio.Event()
        self._trade_event = asyncio.Event()
        self._step_id = 0  # helpful for debugging
        
    async def update_market_parties(self, market_parties: int):
        """Update the number of parties"""
        self.market_parties = max(0, int(market_parties))

    async def report_market(self):
        """Called by each market producer when it has finished producing bars for current step."""
        async with self._lock:
            if self._closed:
                return
            self._market_count += 1
            if self._market_count >= self.market_parties:
                self._market_event.set()

    async def wait_for_market(self):
        """Await until all market producers have reported for current step."""
        if self._closed:
            return
        if self.timeout is None:
            await self._market_event.wait()
            return
        await asyncio.wait_for(self._market_event.wait(), timeout=self.timeout)

    async def report_insight(self):
        """Called by the insight listener to indicate insight processing done for this step."""
        if self._closed:
            return
        self._insight_event.set()

    async def wait_for_insight(self):
        """Trade stream waits for insight processing to finish (i.e. insight_event)."""
        if self._closed:
            return
        if self.timeout is None:
            await self._insight_event.wait()
            return
        await asyncio.wait_for(self._insight_event.wait(), timeout=self.timeout)

    async def report_trade(self):
        """Called by trade stream when it is done processing this step."""
        if self._closed:
            return
        self._trade_event.set()

    async def wait_for_trade(self):
        """Market producers wait for trade to finish before advancing to next step."""
        if self._closed:
            return
        if self.timeout is None:
            await self._trade_event.wait()
            return
        await asyncio.wait_for(self._trade_event.wait(), timeout=self.timeout)

    async def step_complete(self):
        """Reset everything for the next step. Call after trade_event was set and acknowledged by waiters."""
        async with self._lock:
            # increment step id for debugging/tracing
            self._step_id += 1
            # reset events for next step
            self._market_count = 0
            self._market_event = asyncio.Event()
            self._insight_event = asyncio.Event()
            self._trade_event = asyncio.Event()

    def close(self):
        """Abort and wake all waiters."""
        self._closed = True
        # set all events so waiters return quickly
        try:
            self._market_event.set()
            self._insight_event.set()
            self._trade_event.set()
        except Exception:
            pass
