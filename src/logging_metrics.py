"""Logging and metrics system."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

import requests
import structlog

from .config import get_config


class DiscordLogger:
    """Discord webhook logger."""

    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    def send_alert(self, message: str, color: int = 0xff0000):
        """Send Discord alert."""
        if not self.webhook_url:
            return

        embed = {
            "title": "Trading Bot Alert",
            "description": message,
            "color": color,
        }

        data = {"embeds": [embed]}

        try:
            requests.post(self.webhook_url, json=data, timeout=5)
        except Exception as e:
            print(f"Discord alert failed: {e}")


class Logger:
    """Structured logging system."""

    def __init__(self):
        self.config = get_config()
        self.discord = DiscordLogger(self.config.logging.discord_webhook)
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        self.logger = structlog.get_logger()

    def log_event(self, event_type: str, **kwargs):
        """Log structured event."""
        self.logger.info(event_type, **kwargs)

    def log_signal(self, signal: Dict):
        """Log trading signal."""
        self.log_event("signal", **signal)

    def log_order(self, order: Dict):
        """Log order submission."""
        self.log_event("order_submitted", **order)

    def log_fill(self, fill: Dict):
        """Log order fill."""
        self.log_event("fill", **fill)
        # Discord alert for fills
        self.discord.send_alert(f"Order filled: {fill.get('symbol', 'N/A')} {fill.get('side', 'N/A')} {fill.get('amount', 0)} @ {fill.get('price', 0)}", 0x00ff00)

    def log_risk_block(self, reason: str, **kwargs):
        """Log risk control block."""
        self.log_event("risk_blocked", reason=reason, **kwargs)
        self.discord.send_alert(f"Risk block: {reason}", 0xffa500)

    def log_circuit_breaker(self, reason: str):
        """Log circuit breaker trigger."""
        self.log_event("circuit_breaker", reason=reason)
        self.discord.send_alert(f"Circuit breaker: {reason}", 0xff0000)


class TradeBlotter:
    """CSV trade blotter."""

    def __init__(self):
        self.config = get_config()
        self.file_path = Path(self.config.logging.blotter_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize CSV if not exists
        if not self.file_path.exists():
            with open(self.file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'side', 'price', 'size',
                    'order_id', 'filled', 'pnl', 'account_balance'
                ])

    def record_trade(self, trade: Dict):
        """Record trade to CSV."""
        with open(self.file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.get('timestamp', ''),
                trade.get('symbol', ''),
                trade.get('side', ''),
                trade.get('price', 0),
                trade.get('size', 0),
                trade.get('order_id', ''),
                trade.get('filled', 0),
                trade.get('pnl', 0),
                trade.get('account_balance', 0)
            ])


class Analytics:
    """Performance analytics."""

    @staticmethod
    def calculate_metrics(trades: List[Dict], equity_curve: List[float]) -> Dict:
        """Calculate performance metrics."""
        if not trades:
            return {}

        # Basic stats
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]

        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0

        # Returns
        if len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)

            total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]

            # Sharpe ratio (simplified, assuming daily returns)
            if returns:
                avg_return = sum(returns) / len(returns)
                std_return = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5
                sharpe = avg_return / std_return * (252**0.5) if std_return > 0 else 0
            else:
                sharpe = 0

            # Max drawdown
            peak = equity_curve[0]
            max_dd = 0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak
                max_dd = max(max_dd, dd)
        else:
            total_return = 0
            sharpe = 0
            max_dd = 0

        # Exposure and R-multiple
        total_exposure = sum(abs(t.get('size', 0) * t.get('price', 0)) for t in trades)
        net_pnl = sum(t.get('pnl', 0) for t in trades)
        r_multiple = net_pnl / total_exposure if total_exposure > 0 else 0

        return {
            'total_return': total_return,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_trades': total_trades,
            'net_pnl': net_pnl,
            'r_multiple': r_multiple,
            'total_exposure': total_exposure
        }


# Global instances
_logger: Optional[Logger] = None
_blotter: Optional[TradeBlotter] = None


def get_logger() -> Logger:
    """Get the global logger."""
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger


def get_blotter() -> TradeBlotter:
    """Get the global blotter."""
    global _blotter
    if _blotter is None:
        _blotter = TradeBlotter()
    return _blotter