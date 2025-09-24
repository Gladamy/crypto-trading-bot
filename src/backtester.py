"""Backtesting harness using vectorbt and custom simulator."""

import json
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import vectorbt as vbt

from .config import get_config, load_config, set_config
from .simulator import get_simulator
from .strategy import get_strategy


class VectorBTBacktester:
    """VectorBT-based backtester for parameter optimization."""

    def __init__(self):
        self.config = get_config()
        self.simulator = get_simulator()

    def load_data(self) -> pd.DataFrame:
        """Load historical data for backtesting."""
        start = self.config.backtest_start
        end = self.config.backtest_end
        df = self.simulator.load_historical_data(
            self.config.exchange.symbol, "1m", start, end
        )
        return df

    def run_optimization(self, param_ranges: Dict) -> Dict:
        """Optimize strategy parameters using VectorBT."""
        df = self.load_data()

        # Define strategy function for vectorbt
        def strategy_func(ema_short, ema_long, pullback_pct):
            # Calculate indicators
            ema_s = vbt.talib("EMA").run(df['close'], timeperiod=ema_short).real
            ema_l = vbt.talib("EMA").run(df['close'], timeperiod=ema_long).real

            # Trend filter
            trend = (ema_s > ema_l).astype(int)

            # Pullback levels
            pullback_level = ema_s * (1 - pullback_pct)

            # Entries: close < pullback_level and trend == 1
            entries = (df['close'] < pullback_level) & (trend == 1)

            # Exits: EMA cross or stop (simplified)
            exits = (ema_s < ema_l)

            return entries, exits

        # Run optimization
        param_product = vbt.ParamProduct(
            ema_short=param_ranges.get('ema_short', [9, 12, 15]),
            ema_long=param_ranges.get('ema_long', [21, 26, 30]),
            pullback_pct=param_ranges.get('pullback_pct', [0.005, 0.01, 0.015])
        )

        pf = vbt.Portfolio.from_signals(
            close=df['close'],
            entries=param_product.run(strategy_func)['entries'],
            exits=param_product.run(strategy_func)['exits'],
            init_cash=1500,
            fees=0.001  # 0.1%
        )

        # Get best parameters
        best_idx = pf.total_return.idxmax()
        best_params = param_product.index[best_idx]

        return {
            'best_params': best_params,
            'total_return': pf.total_return[best_idx],
            'max_drawdown': pf.max_drawdown[best_idx],
            'sharpe_ratio': pf.sharpe_ratio[best_idx]
        }


class CustomBacktester:
    """Custom backtester for production-parity."""

    def __init__(self):
        self.config = get_config()
        self.simulator = get_simulator()
        self.strategy = get_strategy()

    def run_backtest(self) -> Dict:
        """Run backtest using custom simulator."""
        def strategy_func(df):
            return self.strategy.generate_signal(df)

        results = self.simulator.run_backtest(strategy_func)
        return results

    def save_report(self, results: Dict, output_path: str = "backtest_report.csv"):
        """Save backtest results to CSV."""
        # Save metrics
        metrics_df = pd.DataFrame([results])
        metrics_df.to_csv(output_path, index=False)

        # Save equity curve if available
        if 'equity_curve' in results:
            equity_df = pd.DataFrame({
                'timestamp': range(len(results['equity_curve'])),
                'equity': results['equity_curve']
            })
            equity_df.to_csv("equity_curve.csv", index=False)


def run_backtest(config_path: str = "config.yaml", use_vectorbt: bool = False) -> Dict:
    """Run backtest with given config."""
    config = load_config(config_path)
    set_config(config)

    if use_vectorbt:
        backtester = VectorBTBacktester()
        # Example param ranges
        param_ranges = {
            'ema_short': [8, 9, 10],
            'ema_long': [20, 21, 22],
            'pullback_pct': [0.004, 0.005, 0.006]
        }
        results = backtester.run_optimization(param_ranges)
    else:
        backtester = CustomBacktester()
        results = backtester.run_backtest()
        backtester.save_report(results)

    return results


if __name__ == "__main__":
    # CLI entry point
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    use_vbt = "--vectorbt" in sys.argv

    results = run_backtest(config_path, use_vbt)
    print(json.dumps(results, indent=2))