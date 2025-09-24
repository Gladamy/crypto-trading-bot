"""Main bot runner."""

import asyncio
import signal
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from .api import app as api_app
from .config import load_config, set_config, get_config
from .data import get_market_data
from .execution import get_order_manager
from .logging_metrics import get_logger
from .simulator import get_simulator
from .strategy import get_strategy


class TradingBot:
    """Main trading bot."""

    def __init__(self):
        self.config = get_config()
        self.market_data = get_market_data()
        self.strategy = get_strategy()
        self.order_manager = get_order_manager()
        self.simulator = get_simulator()
        self.logger = get_logger()
        self.running = True

    async def start(self):
        """Start the bot."""
        self.logger.log_event("bot_started", mode=self.config.mode)

        # Start data feeds
        await self.market_data.start()

        # Start API server in background
        api_task = asyncio.create_task(self._run_api())

        # Main trading loop
        try:
            await self._trading_loop()
        except KeyboardInterrupt:
            self.logger.log_event("bot_stopped", reason="keyboard_interrupt")
        finally:
            await self.market_data.stop()
            api_task.cancel()

    async def _run_api(self):
        """Run FastAPI server."""
        config = uvicorn.Config(api_app, host=self.config.api.host, port=self.config.api.port)
        server = uvicorn.Server(config)
        await server.serve()

    async def _trading_loop(self):
        """Main trading loop."""
        while self.running:
            try:
                # Check circuit breakers
                if not self._check_circuit_breakers():
                    self.logger.log_event("circuit_breaker_triggered")
                    await asyncio.sleep(60)  # Wait before retry
                    continue

                # Get latest data
                if self.config.mode == "paper_local":
                    # Simulate data updates
                    await asyncio.sleep(1)
                    continue

                # Check for signals
                df = self.market_data.get_ohlcv("1m", limit=50)
                if df and len(df) >= 50:
                    signal = self.strategy.generate_signal(df)
                    if signal:
                        await self._process_signal(signal)

                await asyncio.sleep(1)  # 1 second loop

            except Exception as e:
                self.logger.log_event("trading_loop_error", error=str(e))
                await asyncio.sleep(5)  # Backoff on error

    async def _process_signal(self, signal):
        """Process trading signal."""
        # Implement order submission
        pass

    def _check_circuit_breakers(self) -> bool:
        """Check all circuit breakers."""
        equity = self.simulator.get_equity()
        return self.strategy.check_hard_stops(equity, self.config.paper.initial_balance)


async def main():
    """Main entry point."""
    config_path = "config.yaml"
    if len(sys.argv) > 2 and sys.argv[1] == "run":
        config_path = sys.argv[2] if len(sys.argv) > 2 else "config.yaml"

    config = load_config(config_path)
    set_config(config)

    bot = TradingBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())