"""Paper trading simulator with backtest and live simulation support."""

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import get_config
from .data import get_market_data
from .exchange import get_exchange_client


class PaperSimulator:
    """Simulates trading for paper modes."""

    def __init__(self):
        self.config = get_config()
        self.market_data = get_market_data()
        self.exchange_client = get_exchange_client()

        # Account state
        self.balance = self.config.paper.initial_balance
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []

        # Determinism
        self.rng = np.random.RandomState(self.config.seed)

        # Cache
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Simulation state
        self.current_time = None
        self.is_backtest = False

    def reset(self):
        """Reset simulator state."""
        self.balance = self.config.paper.initial_balance
        self.positions = {}
        self.trade_history = []
        self.rng = np.random.RandomState(self.config.seed)

    def load_historical_data(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
        """Load or fetch historical OHLCV data."""
        safe_symbol = symbol.replace('/', '_')
        safe_start = start.replace(':', '').replace('-', '')
        safe_end = end.replace(':', '').replace('-', '')
        cache_file = self.cache_dir / f"{safe_symbol}_{timeframe}_{safe_start}_{safe_end}.csv"

        if cache_file.exists():
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        else:
            # Fetch from exchange
            since = int(pd.Timestamp(start).timestamp() * 1000)
            until = int(pd.Timestamp(end).timestamp() * 1000)

            data = []
            while since < until:
                chunk = self.exchange_client.fetch_ohlcv(timeframe, since, 1000)
                if not chunk:
                    break
                data.extend(chunk)
                since = chunk[-1][0] + 1  # Next timestamp

            if data:
                df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                df.set_index('timestamp', inplace=True)
                df.to_csv(cache_file)

        return df

    def run_backtest(self, strategy_func) -> Dict:
        """Run backtest with historical data."""
        self.is_backtest = True
        self.reset()

        # Load data
        start = self.config.backtest_start
        end = self.config.backtest_end
        if not start or not end:
            raise ValueError("Backtest start/end required")

        df = self.load_historical_data(self.config.exchange.symbol, "1m", start, end)

        # Simulate
        results = []
        for idx, row in df.iterrows():
            self.current_time = idx

            # Update prices
            self._update_prices(row)

            # Run strategy
            signal = strategy_func(df.loc[:idx])
            if signal:
                self._process_signal(signal, row['close'])

            # Record equity
            results.append({
                'timestamp': idx,
                'equity': self.get_equity(),
                'balance': self.balance
            })

        # Calculate metrics
        metrics = self._calculate_metrics(results)
        return metrics

    def _update_prices(self, row):
        """Update current prices from data."""
        # Simulate ticker
        mid = (row['high'] + row['low']) / 2
        spread = row['high'] - row['low']
        self.current_bid = mid - spread * 0.1
        self.current_ask = mid + spread * 0.1
        self.current_last = row['close']

    def _process_signal(self, signal: Dict, current_price: float):
        """Process trading signal."""
        if signal['type'] == 'entry':
            self._enter_position(signal, current_price)
        elif signal['type'] == 'exit':
            self._exit_position(signal)

    def _enter_position(self, signal: Dict, price: float):
        """Enter new position."""
        # Calculate size
        equity = self.get_equity()
        stop_distance = 0.02  # 2% stop, simplified
        stop_price = price * (1 - stop_distance)
        size = self._calculate_position_size(equity, price, stop_price)

        if size <= 0:
            return

        # Apply slippage and fees
        fill_price = self._apply_slippage(price, signal['side'])
        fee = self._calculate_fee(fill_price, size)

        # Update balance
        cost = fill_price * size + fee
        if cost > self.balance:
            return  # Insufficient funds

        self.balance -= cost

        # Record position
        self.positions[self.config.exchange.symbol] = {
            'side': signal['side'],
            'size': size,
            'entry_price': fill_price,
            'stop_loss': stop_price,
            'timestamp': self.current_time
        }

        # Record trade
        self.trade_history.append({
            'timestamp': self.current_time,
            'symbol': self.config.exchange.symbol,
            'side': signal['side'],
            'price': fill_price,
            'size': size,
            'fee': fee,
            'type': 'entry'
        })

    def _exit_position(self, signal: Dict):
        """Exit position."""
        symbol = self.config.exchange.symbol
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        exit_price = self._apply_slippage(pos['entry_price'] * 1.01, 'sell' if pos['side'] == 'buy' else 'buy')  # Simplified
        fee = self._calculate_fee(exit_price, pos['size'])

        # P&L
        if pos['side'] == 'buy':
            pnl = (exit_price - pos['entry_price']) * pos['size'] - fee
        else:
            pnl = (pos['entry_price'] - exit_price) * pos['size'] - fee

        self.balance += exit_price * pos['size'] + pnl

        # Record trade
        self.trade_history.append({
            'timestamp': self.current_time,
            'symbol': symbol,
            'side': 'sell' if pos['side'] == 'buy' else 'buy',
            'price': exit_price,
            'size': pos['size'],
            'fee': fee,
            'pnl': pnl,
            'type': 'exit'
        })

        del self.positions[symbol]

    def _calculate_position_size(self, equity: float, entry: float, stop: float) -> float:
        """Calculate position size."""
        risk_amount = equity * (self.config.strategy.risk_pct_per_trade / 100)
        risk_per_unit = abs(entry - stop)
        return risk_amount / risk_per_unit if risk_per_unit > 0 else 0

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage."""
        slippage_ticks = self.config.paper.slippage_ticks
        if slippage_ticks == 0:
            return price

        # Deterministic slippage
        slip = self.rng.uniform(-slippage_ticks, slippage_ticks) * 0.01  # 1% per tick
        return price * (1 + slip)

    def _calculate_fee(self, price: float, size: float) -> float:
        """Calculate trading fee."""
        cost = price * size
        maker_fee = cost * (self.config.fees.maker_bps / 10000)
        taker_fee = cost * (self.config.fees.taker_bps / 10000)
        return taker_fee  # Assume taker for sim

    def get_equity(self) -> float:
        """Get current equity."""
        equity = self.balance
        for pos in self.positions.values():
            # Mark to market
            current_price = getattr(self, 'current_last', pos['entry_price'])
            if pos['side'] == 'buy':
                equity += (current_price - pos['entry_price']) * pos['size']
            else:
                equity += (pos['entry_price'] - current_price) * pos['size']
        return equity

    def _calculate_metrics(self, results: List[Dict]) -> Dict:
        """Calculate backtest metrics."""
        if not results:
            return {}

        equities = [r['equity'] for r in results]
        returns = np.diff(equities) / equities[:-1]

        total_return = (equities[-1] - equities[0]) / equities[0]
        max_drawdown = self._calculate_max_drawdown(equities)
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24 * 60) if returns.size > 0 else 0  # Annualized

        winning_trades = [t for t in self.trade_history if t.get('pnl', 0) > 0]
        win_rate = len(winning_trades) / len(self.trade_history) if self.trade_history else 0

        return {
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'total_trades': len(self.trade_history),
            'equity_curve': equities
        }

    def _calculate_max_drawdown(self, equities: List[float]) -> float:
        """Calculate maximum drawdown."""
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)
        return max_dd

    def simulate_live_order(self, order: Dict) -> Dict:
        """Simulate order fill for live paper trading."""
        # Use current market prices
        if order['type'] == 'market':
            if order['side'] == 'buy':
                fill_price = self.current_ask
            else:
                fill_price = self.current_bid
        else:
            fill_price = order['price']

        # Apply slippage
        fill_price = self._apply_slippage(fill_price, order['side'])

        # Simulate fill
        filled = order['amount']  # Assume full fill
        cost = fill_price * filled
        fee = self._calculate_fee(fill_price, filled)

        return {
            'id': order.get('id', 'simulated'),
            'filled': filled,
            'cost': cost,
            'fee': fee,
            'price': fill_price,
            'status': 'closed'
        }


# Global instance
_simulator: Optional[PaperSimulator] = None


def get_simulator() -> PaperSimulator:
    """Get the global simulator."""
    global _simulator
    if _simulator is None:
        _simulator = PaperSimulator()
    return _simulator