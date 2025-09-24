"""Configuration management with validation."""

import os
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator


class ExchangeConfig(BaseModel):
    """Exchange configuration."""

    name: Literal["kraken"] = "kraken"
    credentials_env_file: Optional[str] = None
    symbol: str = "BTC/USD"
    timeframes: List[str] = Field(default_factory=lambda: ["1m", "5m"])

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, v):
        allowed = ["1m", "5m", "15m", "1h"]
        for tf in v:
            if tf not in allowed:
                raise ValueError(f"Unsupported timeframe: {tf}")
        return v


class StrategyConfig(BaseModel):
    """Strategy parameters."""

    ema_short: int = Field(ge=1, le=50)
    ema_long: int = Field(ge=5, le=200)
    pullback_pct: float = Field(ge=0.1, le=5.0)
    risk_pct_per_trade: float = Field(ge=0.1, le=5.0)
    volatility_threshold: float = Field(ge=0.5, le=10.0)


class RiskConfig(BaseModel):
    """Risk management settings."""

    max_daily_loss_pct: float = Field(ge=0.1, le=20.0)
    max_drawdown_pct: float = Field(ge=1.0, le=50.0)
    max_positions: int = Field(ge=1, le=10)
    max_consecutive_losses: int = Field(ge=1, le=10)


class PaperConfig(BaseModel):
    """Paper trading settings."""

    initial_balance: float = Field(ge=100.0)
    latency_ms: int = Field(ge=0, le=1000)
    slippage_ticks: int = Field(ge=0, le=10)


class FeesConfig(BaseModel):
    """Fee structure."""

    maker_bps: int = Field(ge=0, le=100)
    taker_bps: int = Field(ge=0, le=100)


class ApiConfig(BaseModel):
    """API server settings."""

    host: str = "0.0.0.0"
    port: int = Field(ge=1024, le=65535)
    control_token: str


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    blotter_path: str = "data/trade_blotter.csv"
    discord_webhook: Optional[str] = None


class Config(BaseModel):
    """Main configuration."""

    mode: Literal["demo", "paper_local", "live"]
    dry_run: bool = False
    exchange: ExchangeConfig
    strategy: StrategyConfig
    risk: RiskConfig
    paper: PaperConfig
    fees: FeesConfig
    seed: int = Field(ge=0)
    backtest_start: Optional[str] = None
    backtest_end: Optional[str] = None
    api: ApiConfig
    logging: LoggingConfig

    @field_validator("backtest_start", "backtest_end")
    @classmethod
    def validate_iso_datetime(cls, v):
        if v is not None:
            from datetime import datetime
            try:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid ISO datetime: {v}")
        return v


def load_config(config_path: str = "config.yaml") -> Config:
    """Load and validate configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Load environment variables if specified and not paper mode
    if "exchange" in data and data["exchange"].get("credentials_env_file") and data.get("mode") not in ["paper_local"]:
        env_file = data["exchange"]["credentials_env_file"]
        if os.path.exists(env_file):
            load_dotenv(env_file)
        else:
            raise FileNotFoundError(f"Credentials env file not found: {env_file}")

    try:
        config = Config(**data)
    except ValidationError as e:
        raise ValueError(f"Configuration validation error: {e}")

    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    if _config is None:
        raise RuntimeError("Config not loaded. Call load_config() first.")
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config