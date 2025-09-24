"""Trading strategy implementation."""

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta

from .config import get_config


class EMACrossoverStrategy:
    """EMA crossover + pullback scalping strategy."""

    def __init__(self):
        self.config = get_config()
        self.symbol = self.config.exchange.symbol

        # Strategy params
        self.ema_short = self.config.strategy.ema_short
        self.ema_long = self.config.strategy.ema_long
        self.pullback_pct = self.config.strategy.pullback_pct / 100  # Convert to decimal
        self.volatility_threshold = self.config.strategy.volatility_threshold

        # State
        self.position: Optional[Dict] = None
        self.last_signal = None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        df = df.copy()

        # EMAs
        df['ema_short'] = ta.ema(df['close'], length=self.ema_short)
        df['ema_long'] = ta.ema(df['close'], length=self.ema_long)

        # ATR for volatility
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

        # Trend direction
        df['trend'] = np.where(df['ema_short'] > df['ema_long'], 1, -1)

        # Pullback levels
        df['pullback_level'] = df['ema_short'] * (1 - self.pullback_pct)

        return df

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict]:
        """Generate trading signal."""
        if len(df) < max(self.ema_short, self.ema_long, 14):
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Check volatility guard
        if latest['atr'] / latest['close'] > self.volatility_threshold / 100:
            return None

        # Trend filter
        if latest['trend'] != 1:  # Only long for now
            return None

        # Pullback entry
        if prev['close'] > latest['ema_short'] and latest['close'] <= latest['pullback_level']:
            # Price pulled back to level
            return {
                'type': 'entry',
                'side': 'buy',
                'price': latest['pullback_level'],  # Limit at pullback level
                'reason': 'pullback_entry'
            }

        # Exit signals
        if self.position:
            if self.position['side'] == 'buy':
                # Stop loss
                if latest['close'] <= self.position['stop_loss']:
                    return {
                        'type': 'exit',
                        'reason': 'stop_loss'
                    }

                # Take profit
                if latest['close'] >= self.position['take_profit']:
                    return {
                        'type': 'exit',
                        'reason': 'take_profit'
                    }

                # EMA crossover against
                if latest['trend'] != 1:
                    return {
                        'type': 'exit',
                        'reason': 'trend_reversal'
                    }

        return None

    def calculate_position_size(self, equity: float, entry_price: float, stop_price: float) -> float:
        """Calculate position size based on risk."""
        risk_amount = equity * (self.config.strategy.risk_pct_per_trade / 100)
        risk_per_unit = abs(entry_price - stop_price)
        if risk_per_unit == 0:
            return 0

        size = risk_amount / risk_per_unit
        return size

    def set_position(self, side: str, entry_price: float, size: float, df: pd.DataFrame):
        """Set position with stops."""
        # Stop loss: recent swing low (simplified: lowest low in last 10 bars)
        lookback = min(10, len(df))
        stop_loss = df['low'].iloc[-lookback:].min()

        # Take profit: 1.5x risk
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * 1.5)

        self.position = {
            'side': side,
            'entry_price': entry_price,
            'size': size,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'entry_time': df.index[-1]
        }

    def update_trailing_stop(self, current_price: float):
        """Update trailing stop if applicable."""
        if not self.position or self.position.get('trailing', False):
            return

        # Simple trailing: move stop to breakeven + some buffer after 1:1 reward
        risk = self.position['entry_price'] - self.position['stop_loss']
        if current_price >= self.position['entry_price'] + risk:
            self.position['stop_loss'] = self.position['entry_price']
            self.position['trailing'] = True

    def get_position(self) -> Optional[Dict]:
        """Get current position."""
        return self.position

    def close_position(self):
        """Close position."""
        self.position = None

    def is_long_allowed(self, df: pd.DataFrame) -> bool:
        """Check if long entries are allowed."""
        if len(df) < 2:
            return False

        latest = df.iloc[-1]

        # Soft guards
        if self._check_consecutive_losses():
            return False

        return latest['trend'] == 1

    def is_short_allowed(self, df: pd.DataFrame) -> bool:
        """Check if short entries are allowed."""
        if len(df) < 2:
            return False

        latest = df.iloc[-1]

        # Soft guards
        if self._check_consecutive_losses():
            return False

        return latest['trend'] == -1

    def _check_consecutive_losses(self) -> bool:
        """Check for consecutive losses guard."""
        # Simplified: assume no losses tracked yet
        return False  # Implement based on trade history

    def check_hard_stops(self, equity: float, initial_balance: float) -> bool:
        """Check hard circuit breakers."""
        config = self.config

        # Daily loss
        daily_loss = (initial_balance - equity) / initial_balance
        if daily_loss >= config.risk.max_daily_loss_pct / 100:
            return False

        # Drawdown
        if equity < initial_balance * (1 - config.risk.max_drawdown_pct / 100):
            return False

        return True


# Global instance
_strategy: Optional[EMACrossoverStrategy] = None


def get_strategy() -> EMACrossoverStrategy:
    """Get the global strategy instance."""
    global _strategy
    if _strategy is None:
        _strategy = EMACrossoverStrategy()
    return _strategy