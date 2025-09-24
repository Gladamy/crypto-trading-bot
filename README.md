# Crypto Trading Bot

A production-ready intraday crypto trading bot for Kraken using EMA crossover + pullback strategy.

## Features

- **Exchange Support**: Kraken with demo/live/paper modes
- **Strategy**: EMA crossover trend filter + pullback scalper (1-5m timeframe)
- **Risk Controls**: Max risk per trade, daily drawdown limits, position caps
- **Paper Trading**: Local simulation with historical replay or live websocket feeds
- **Backtesting**: VectorBT for optimization + custom backtester for production parity
- **Observability**: Structured JSON logs, trade blotter CSV, performance metrics
- **Deployment**: Docker containerized with API endpoints

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (optional)
- Kraken API keys (for live/demo)

### Installation

1. Clone repo:
   ```bash
   git clone <repo-url>
   cd crypto-trading-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy config:
   ```bash
   cp config.example.yaml config.yaml
   ```

### Configuration

Edit `config.yaml`:

- Set `mode`: `paper_local`, `demo`, or `live`
- Adjust strategy params, risk limits
- For live/demo: create `.env` with `API_KEY` and `API_SECRET`

### Kraken API Keys

1. Go to [Kraken API Settings](https://www.kraken.com/u/security/api)
2. Create API key with trading permissions
3. For demo: Use Kraken Futures demo (note: spot demo limited)
4. Add to `.env`:
   ```
   API_KEY=your_key
   API_SECRET=your_secret
   ```

## Running

### Local Paper Trading

```bash
python -m src.main run --mode paper_local
```

### Demo Mode (Kraken Futures)

```bash
python -m src.main run --mode demo
```

### Live Mode

```bash
python -m src.main run --mode live
```

### Dry Run (Test live without trading)

```bash
# Set dry_run: true in config.yaml
python -m src.main run --mode live
```

### Backtesting

```bash
python -m src.backtester
```

Output: `backtest_report.csv`, `equity_curve.csv`

### Docker

```bash
docker-compose up -d trading-bot
```

For backtesting:
```bash
docker-compose --profile backtest up backtester
```

### 24/7 Deployment

For continuous operation, deploy to a VPS/cloud instance:

1. **VPS Setup**: Use DigitalOcean/AWS EC2/Linode ($5-10/month)
2. **SSH Setup** (Recommended):
   ```bash
   # Generate SSH key on your local machine
   ssh-keygen

   # Copy public key to VPS
   ssh-copy-id root@YOUR_VPS_IP
   # Or manually add to ~/.ssh/authorized_keys on VPS
   ```
3. **Connect**: `ssh root@YOUR_VPS_IP`
4. **Install Docker**: `sudo apt update && sudo apt install docker.io -y`
5. **Clone & Run**:
   ```bash
   git clone <repo>
   cd crypto-trading-bot
   docker-compose up -d
   ```
6. **Monitor**: Use `docker-compose logs -f` or access API at `http://your-server:8000`

### Discord Alerts

1. Create Discord webhook: Server Settings → Integrations → Webhooks
2. Add URL to `config.yaml`:
   ```yaml
   logging:
     discord_webhook: "https://discord.com/api/webhooks/..."
   ```
3. Alerts for: order fills, risk blocks, circuit breakers

## API Endpoints

- `GET /status`: Current positions, P&L, equity, mode
- `POST /pause`: Pause trading (requires token)
- `POST /resume`: Resume trading (requires token)

Example:
```bash
curl http://localhost:8000/status
```

## Testing

Run unit tests:
```bash
pytest
```

## Architecture

- `src/config.py`: Configuration validation
- `src/exchange.py`: CCXT Kraken client
- `src/data.py`: Market data feeds
- `src/strategy.py`: Trading logic
- `src/execution.py`: Order management
- `src/simulator.py`: Paper trading simulation
- `src/backtester.py`: Backtesting harness
- `src/logging_metrics.py`: Observability

## Sample Backtest Output

```
total_return: 0.15
max_drawdown: 0.08
sharpe_ratio: 1.2
win_rate: 0.65
total_trades: 45
```

## Security

- API secrets not committed to repo
- Use environment variables or OS key vault
- Paper mode for safe testing

## Disclaimer

This is for educational purposes. Trading involves risk. Test thoroughly before live trading.