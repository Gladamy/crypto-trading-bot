"""Order execution and management."""

import time
from typing import Dict, List, Optional

from .config import get_config
from .exchange import get_exchange_client


class OrderManager:
    """Manages order execution with idempotency and risk controls."""

    def __init__(self):
        self.config = get_config()
        self.exchange_client = get_exchange_client()

        # Order tracking
        self.open_orders: Dict[str, Dict] = {}
        self.order_history: List[Dict] = []
        self.last_client_order_id = 0

        # Idempotency
        self.submitted_order_ids: set = set()

    def _generate_client_order_id(self) -> str:
        """Generate unique client order ID."""
        self.last_client_order_id += 1
        return f"bot_{int(time.time())}_{self.last_client_order_id}"

    def submit_order(self, symbol: str, type: str, side: str, amount: float,
                    price: Optional[float] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """Submit order with idempotency."""
        client_order_id = self._generate_client_order_id()

        # Check for duplicate (simple check)
        if client_order_id in self.submitted_order_ids:
            print(f"Duplicate order detected: {client_order_id}")
            return None

        self.submitted_order_ids.add(client_order_id)

        try:
            if self.config.mode == "paper_local":
                # Simulate order
                order = self._simulate_order(symbol, type, side, amount, price, client_order_id)
            elif self.config.dry_run:
                # Dry run: log but don't send
                order = {
                    'id': client_order_id,
                    'symbol': symbol,
                    'type': type,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'status': 'dry_run',
                    'info': 'Dry run - not sent'
                }
                print(f"Dry run order: {order}")
            else:
                # Real order
                order = self.exchange_client.create_order(symbol, type, side, amount, price, params or {})

            order['client_order_id'] = client_order_id
            self.open_orders[order['id']] = order
            self.order_history.append(order)

            return order

        except Exception as e:
            print(f"Order submission failed: {e}")
            self.submitted_order_ids.discard(client_order_id)
            return None

    def _simulate_order(self, symbol: str, type: str, side: str, amount: float,
                       price: Optional[float], client_order_id: str) -> Dict:
        """Simulate order for paper trading."""
        # Simple simulation: assume fill at requested price or market
        fill_price = price
        if type == "market" or not price:
            # Use mid price from ticker (simplified)
            fill_price = 50000.0  # Placeholder

        order = {
            'id': client_order_id,
            'clientOrderId': client_order_id,
            'symbol': symbol,
            'type': type,
            'side': side,
            'amount': amount,
            'price': price,
            'filled': amount,
            'remaining': 0,
            'cost': amount * fill_price,
            'fee': {'cost': amount * fill_price * 0.001},  # 0.1% fee
            'status': 'closed',
            'timestamp': int(time.time() * 1000),
            'info': {}
        }
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel order."""
        try:
            if self.config.mode == "paper_local":
                if order_id in self.open_orders:
                    self.open_orders[order_id]['status'] = 'canceled'
                    return True
            else:
                result = self.exchange_client.cancel_order(order_id)
                if order_id in self.open_orders:
                    self.open_orders[order_id]['status'] = 'canceled'
                return True
        except Exception as e:
            print(f"Cancel failed: {e}")
            return False

    def cancel_all_orders(self, symbol: Optional[str] = None):
        """Cancel all open orders."""
        to_cancel = []
        for order_id, order in self.open_orders.items():
            if order['status'] == 'open' and (not symbol or order['symbol'] == symbol):
                to_cancel.append(order_id)

        for order_id in to_cancel:
            self.cancel_order(order_id)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get open orders."""
        orders = [o for o in self.open_orders.values() if o['status'] == 'open']
        if symbol:
            orders = [o for o in orders if o['symbol'] == symbol]
        return orders

    def update_trailing_stop(self, position: Dict, current_price: float):
        """Update trailing stop order."""
        if not position.get('trailing_stop_order_id'):
            return

        # Calculate new stop price
        entry = position['entry_price']
        trail_pct = 0.005  # 0.5% trail
        if position['side'] == 'buy':
            new_stop = max(position.get('trailing_stop', entry), current_price * (1 - trail_pct))
        else:
            new_stop = min(position.get('trailing_stop', entry), current_price * (1 + trail_pct))

        # Update if improved
        if abs(new_stop - position.get('trailing_stop', 0)) > 0.01:  # Min change
            # Cancel old, submit new
            old_id = position['trailing_stop_order_id']
            self.cancel_order(old_id)

            # Submit new trailing stop
            trail_order = self.submit_order(
                position['symbol'], 'stop', 'sell' if position['side'] == 'buy' else 'buy',
                position['size'], price=new_stop
            )
            if trail_order:
                position['trailing_stop_order_id'] = trail_order['id']
                position['trailing_stop'] = new_stop

    def on_reconnect(self):
        """Handle reconnection: dedupe orders."""
        # In a real implementation, query open orders and reconcile
        # For now, assume no duplicates
        pass


# Global instance
_order_manager: Optional[OrderManager] = None


def get_order_manager() -> OrderManager:
    """Get the global order manager."""
    global _order_manager
    if _order_manager is None:
        _order_manager = OrderManager()
    return _order_manager