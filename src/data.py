"""Data layer for market data handling."""

import asyncio
import json
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException

from .config import get_config
from .exchange import get_exchange_client


class DataStaleError(Exception):
    """Raised when market data is stale."""
    pass


class MarketData:
    """Market data manager with REST and WebSocket support."""

    def __init__(self):
        self.config = get_config()
        self.exchange_client = get_exchange_client()
        self.symbol = self.config.exchange.symbol

        # Data storage
        self.ohlcv_data: Dict[str, List] = defaultdict(list)
        self.ticker_data: Dict[str, Dict] = {}
        self.last_update: Dict[str, float] = {}

        # WS connection
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self.ws_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.base_backoff = 1.0
        self.max_backoff = 60.0

        # Callbacks
        self.on_ticker_update: Optional[Callable] = None
        self.on_candle_update: Optional[Callable] = None

        # Data stale threshold (seconds)
        self.stale_threshold = 30.0

    async def fetch_historical_ohlcv(self, timeframe: str, since: Optional[int] = None, limit: Optional[int] = None) -> List:
        """Fetch historical OHLCV data via REST."""
        if self.config.mode == "paper_local":
            # For paper mode, we might load from cache or fetch once
            pass

        try:
            data = self.exchange_client.fetch_ohlcv(timeframe, since, limit)
            self.ohlcv_data[timeframe].extend(data)
            return data
        except Exception as e:
            print(f"Error fetching OHLCV: {e}")
            return []

    def get_ohlcv(self, timeframe: str, limit: Optional[int] = None) -> List:
        """Get cached OHLCV data."""
        data = self.ohlcv_data[timeframe]
        if limit:
            data = data[-limit:]
        return data

    def check_data_stale(self) -> bool:
        """Check if data is stale."""
        now = time.time()
        for key, last in self.last_update.items():
            if now - last > self.stale_threshold:
                return True
        return False

    def update_last_update(self, key: str):
        """Update last update timestamp."""
        self.last_update[key] = time.time()

    async def connect_ws(self):
        """Connect to Kraken WebSocket."""
        if self.config.mode == "paper_local":
            return  # No WS for paper local

        url = "wss://ws.kraken.com"
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                async with websockets.connect(url) as ws:
                    self.ws = ws
                    self.ws_connected = True
                    self.reconnect_attempts = 0
                    print("WebSocket connected")

                    # Subscribe to ticker and candles
                    await self._subscribe()

                    # Listen for messages
                    async for message in ws:
                        await self._handle_message(message)

            except (ConnectionClosedError, WebSocketException, OSError) as e:
                print(f"WebSocket error: {e}")
                self.ws_connected = False
                await self._reconnect_backoff()

        print("Max reconnect attempts reached")

    async def _reconnect_backoff(self):
        """Exponential backoff with jitter for reconnection."""
        self.reconnect_attempts += 1
        delay = min(self.base_backoff * (2 ** self.reconnect_attempts) + random.uniform(0, 1), self.max_backoff)
        print(f"Reconnecting in {delay:.2f} seconds...")
        await asyncio.sleep(delay)

    async def _subscribe(self):
        """Subscribe to feeds."""
        if not self.ws:
            return

        # Ticker subscription
        ticker_msg = {
            "event": "subscribe",
            "pair": [self.symbol.replace('/', '')],  # e.g., XBTUSD
            "subscription": {"name": "ticker"}
        }
        await self.ws.send(json.dumps(ticker_msg))

        # Candle subscription for each timeframe
        for tf in self.config.exchange.timeframes:
            candle_msg = {
                "event": "subscribe",
                "pair": [self.symbol.replace('/', '')],
                "subscription": {"name": "ohlc", "interval": self._timeframe_to_interval(tf)}
            }
            await self.ws.send(json.dumps(candle_msg))

    def _timeframe_to_interval(self, tf: str) -> int:
        """Convert timeframe to Kraken interval."""
        mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
        return mapping.get(tf, 1)

    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            if isinstance(data, list) and len(data) > 2:
                channel = data[2]
                payload = data[1]

                if "ticker" in channel:
                    self._handle_ticker(payload)
                elif "ohlc" in channel:
                    self._handle_candle(payload)

        except json.JSONDecodeError:
            pass  # Heartbeat or other

    def _handle_ticker(self, payload):
        """Handle ticker update."""
        if isinstance(payload, list):
            symbol = payload[0]
            ticker = {
                "bid": float(payload[1]["b"][0]),
                "ask": float(payload[1]["a"][0]),
                "last": float(payload[1]["c"][0]),
                "volume": float(payload[1]["v"][0]),
            }
            self.ticker_data[symbol] = ticker
            self.update_last_update(f"ticker_{symbol}")

            if self.on_ticker_update:
                self.on_ticker_update(ticker)

    def _handle_candle(self, payload):
        """Handle candle update."""
        if isinstance(payload, list):
            symbol = payload[0]
            candle = payload[1]
            if len(candle) >= 6:
                ohlc = {
                    "timestamp": int(candle[1]) * 1000,  # Kraken sends seconds
                    "open": float(candle[2]),
                    "high": float(candle[3]),
                    "low": float(candle[4]),
                    "close": float(candle[5]),
                    "volume": float(candle[6]),
                }
                # Add to OHLCV data (assuming 1m for now)
                self.ohlcv_data["1m"].append([
                    ohlc["timestamp"], ohlc["open"], ohlc["high"],
                    ohlc["low"], ohlc["close"], ohlc["volume"]
                ])
                self.update_last_update(f"candle_{symbol}")

                if self.on_candle_update:
                    self.on_candle_update(ohlc)

    def get_server_time(self) -> datetime:
        """Get server time in UTC."""
        if self.exchange_client.client:
            ms = self.exchange_client.fetch_server_time()
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return datetime.now(timezone.utc)

    async def start(self):
        """Start data feeds."""
        if self.config.mode in ["demo", "live"]:
            asyncio.create_task(self.connect_ws())

    async def stop(self):
        """Stop data feeds."""
        if self.ws:
            await self.ws.close()
            self.ws_connected = False


# Global instance
_data: Optional[MarketData] = None


def get_market_data() -> MarketData:
    """Get the global market data instance."""
    global _data
    if _data is None:
        _data = MarketData()
    return _data