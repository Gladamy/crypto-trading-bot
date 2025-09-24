"""Tests for strategy module."""

import pandas as pd
import pytest

from src.config import Config, StrategyConfig, RiskConfig, PaperConfig, FeesConfig, ExchangeConfig, ApiConfig, LoggingConfig
from src.strategy import EMACrossoverStrategy


@pytest.fixture
def sample_config():
    """Sample config for testing."""
    return Config(
        mode="paper_local",
        exchange=ExchangeConfig(),
        strategy=StrategyConfig(ema_short=9, ema_long=21, pullback_pct=0.5, risk_pct_per_trade=1.0, volatility_threshold=2.0),
        risk=RiskConfig(max_daily_loss_pct=5.0, max_drawdown_pct=10.0, max_positions=1, max_consecutive_losses=3),
        paper=PaperConfig(initial_balance=1500.0, latency_ms=100, slippage_ticks=0),
        fees=FeesConfig(maker_bps=16, taker_bps=26),
        seed=42,
        api=ApiConfig(port=8000, control_token="test"),
        logging=LoggingConfig()
    )


@pytest.fixture
def sample_df():
    """Sample OHLCV DataFrame."""
    data = {
        'timestamp': pd.date_range('2023-01-01', periods=50, freq='1min'),
        'open': [100] * 50,
        'high': [101] * 50,
        'low': [99] * 50,
        'close': list(range(100, 150))  # Increasing trend
    }
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df


def test_position_sizing(sample_config):
    """Test position size calculation."""
    from src.strategy import get_strategy
    from src.config import set_config

    set_config(sample_config)
    strategy = get_strategy()

    equity = 1500.0
    entry_price = 100.0
    stop_price = 98.0  # 2% risk

    size = strategy.calculate_position_size(equity, entry_price, stop_price)
    expected_risk = equity * (sample_config.strategy.risk_pct_per_trade / 100)
    expected_size = expected_risk / (entry_price - stop_price)

    assert abs(size - expected_size) < 0.01


def test_stop_calculation(sample_df, sample_config):
    """Test stop loss calculation."""
    from src.config import set_config

    set_config(sample_config)
    strategy = EMACrossoverStrategy()

    # Set position
    strategy.set_position('buy', 125.0, 10.0, sample_df)

    pos = strategy.get_position()
    assert pos is not None
    assert pos['stop_loss'] == sample_df['low'].iloc[-10:].min()  # Lowest in last 10


def test_pnl_accounting():
    """Test P&L calculation."""
    # This would test the simulator's P&L accounting
    # For now, placeholder
    assert True


def test_fee_slippage_models(sample_config):
    """Test fee and slippage models."""
    from src.simulator import PaperSimulator
    from src.config import set_config

    set_config(sample_config)
    sim = PaperSimulator()

    price = 100.0
    size = 10.0

    fee = sim._calculate_fee(price, size)
    expected_fee = price * size * (sample_config.fees.taker_bps / 10000)
    assert abs(fee - expected_fee) < 0.01

    # Slippage
    fill_price = sim._apply_slippage(price, 'buy')
    assert 99.0 <= fill_price <= 101.0  # Within range