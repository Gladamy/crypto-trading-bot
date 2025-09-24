"""Tests for execution module."""

import pytest
from unittest.mock import Mock, patch

from src.config import Config, ExchangeConfig, StrategyConfig, RiskConfig, PaperConfig, FeesConfig, ApiConfig, LoggingConfig
from src.execution import OrderManager


@pytest.fixture
def sample_config():
    """Sample config."""
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


def test_order_simulation(sample_config):
    """Test order simulation in paper mode."""
    from src.config import set_config

    set_config(sample_config)
    manager = OrderManager()

    order = manager.submit_order("BTC/USD", "market", "buy", 0.01, 50000)
    assert order is not None
    assert order['status'] == 'closed'
    assert order['filled'] == 0.01


@patch('src.execution.get_exchange_client')
def test_demo_order_submission(mock_client, sample_config):
    """Test order submission in demo mode (mocked)."""
    from src.config import set_config

    set_config(sample_config)
    mock_client.return_value.create_order = Mock(return_value={'id': 'test_order'})

    # Temporarily set mode to demo
    sample_config.mode = "demo"
    set_config(sample_config)

    manager = OrderManager()
    order = manager.submit_order("BTC/USD", "limit", "buy", 0.01, 50000)

    # Should call real client
    mock_client.return_value.create_order.assert_called_once()
    assert order['id'] == 'test_order'