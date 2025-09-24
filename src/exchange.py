"""Exchange client using CCXT with Kraken support."""

import os
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, Tuple

import ccxt
from ccxt import Exchange

from .config import get_config


class KrakenClient:
    """CCXT client for Kraken with demo/live/paper support."""

    def __init__(self):
        config = get_config()
        self.mode = config.mode
        self.symbol = config.exchange.symbol
        self._client: Optional[Exchange] = None
        self._market_info: Optional[Dict] = None

    def _create_client(self) -> Exchange:
        """Create and configure CCXT client."""
        config = get_config()

        if self.mode == "live":
            # Live trading
            client = ccxt.kraken({
                'apiKey': os.getenv('API_KEY'),
                'secret': os.getenv('API_SECRET'),
                'enableRateLimit': True,
            })
        elif self.mode == "demo":
            # Kraken futures demo
            client = ccxt.krakenfutures({
                'apiKey': os.getenv('API_KEY'),
                'secret': os.getenv('API_SECRET'),
                'enableRateLimit': True,
                'test': True,  # Demo mode
            })
            # Adjust symbol for futures if needed
            if not self.symbol.endswith('USD'):
                self.symbol = self.symbol.replace('/', 'USD')
        else:  # paper_local
            # Create client for data fetching only
            client = ccxt.kraken({
                'enableRateLimit': True,
            })

        if client:
            client.load_markets()
        return client

    @property
    def client(self) -> Optional[Exchange]:
        """Get the CCXT client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @property
    def market_info(self) -> Dict:
        """Get market info for current symbol."""
        if self._market_info is None and self.client:
            symbol = self._normalize_symbol(self.symbol)
            self._market_info = self.client.market(symbol)
        return self._market_info or {}

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Kraken format."""
        # Kraken uses specific formats like XXBTZUSD
        base, quote = symbol.split('/')
        if base == 'BTC':
            base = 'XXBT'
        elif base == 'ETH':
            base = 'XETH'
        if quote == 'USD':
            quote = 'ZUSD'
        elif quote == 'EUR':
            quote = 'ZEUR'
        return f'{base}{quote}'

    def validate_order(self, side: str, amount: float, price: Optional[float] = None) -> Tuple[bool, str]:
        """Validate order against exchange rules."""
        if not self.market_info:
            return True, ""  # Allow in paper mode

        market = self.market_info
        min_amount = market.get('minAmount', 0)
        amount_step = market.get('amountStep', 1e-8)
        price_tick = market.get('priceTick', 1e-8)

        # Check min amount
        if amount < min_amount:
            return False, f"Amount {amount} below minimum {min_amount}"

        # Check amount precision
        if amount % amount_step != 0:
            return False, f"Amount {amount} not multiple of step {amount_step}"

        if price is not None:
            # Check price precision
            if price % price_tick != 0:
                return False, f"Price {price} not multiple of tick {price_tick}"

        return True, ""

    def normalize_price(self, price: float) -> float:
        """Round price to exchange precision."""
        if not self.market_info:
            return price

        tick = self.market_info.get('priceTick', 1e-8)
        return float(Decimal(str(price)).quantize(Decimal(str(tick)), rounding=ROUND_DOWN))

    def normalize_amount(self, amount: float) -> float:
        """Round amount to exchange precision."""
        if not self.market_info:
            return amount

        step = self.market_info.get('amountStep', 1e-8)
        return float(Decimal(str(amount)).quantize(Decimal(str(step)), rounding=ROUND_DOWN))

    def fetch_ohlcv(self, timeframe: str, since: Optional[int] = None, limit: Optional[int] = None):
        """Fetch OHLCV data."""
        if not self.client:
            raise RuntimeError("No client available for fetching data")

        symbol = self._normalize_symbol(self.symbol)
        return self.client.fetch_ohlcv(symbol, timeframe, since, limit)

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict] = None):
        """Create order with validation."""
        if not self.client:
            raise RuntimeError("No client available for orders")

        symbol = self._normalize_symbol(symbol)
        amount = self.normalize_amount(amount)
        if price:
            price = self.normalize_price(price)

        valid, error = self.validate_order(side, amount, price)
        if not valid:
            raise ValueError(f"Order validation failed: {error}")

        return self.client.create_order(symbol, type, side, amount, price, params or {})

    def cancel_order(self, order_id: str, symbol: Optional[str] = None):
        """Cancel order."""
        if not self.client:
            raise RuntimeError("No client available for orders")

        symbol = self._normalize_symbol(symbol or self.symbol)
        return self.client.cancel_order(order_id, symbol)

    def fetch_balance(self):
        """Fetch account balance."""
        if not self.client:
            raise RuntimeError("No client available")

        return self.client.fetch_balance()

    def fetch_ticker(self, symbol: Optional[str] = None):
        """Fetch ticker data."""
        if not self.client:
            raise RuntimeError("No client available")

        symbol = self._normalize_symbol(symbol or self.symbol)
        return self.client.fetch_ticker(symbol)

    def fetch_server_time(self) -> int:
        """Fetch server time in milliseconds."""
        if not self.client:
            return int(ccxt.Exchange.milliseconds())  # Fallback

        return self.client.milliseconds()


# Global instance
_client: Optional[KrakenClient] = None


def get_exchange_client() -> KrakenClient:
    """Get the global exchange client."""
    global _client
    if _client is None:
        _client = KrakenClient()
    return _client