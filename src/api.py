"""REST API for bot control and monitoring."""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import get_config
from .simulator import get_simulator
from .strategy import get_strategy
from .logging_metrics import get_logger


app = FastAPI(title="Trading Bot API")
security = HTTPBearer()

# Global bot state
bot_state = {"running": True}


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify control token."""
    config = get_config()
    if credentials.credentials != config.api.control_token:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/status")
async def get_status():
    """Get current bot status."""
    config = get_config()
    simulator = get_simulator()
    strategy = get_strategy()
    logger = get_logger()

    positions = strategy.get_position()
    equity = simulator.get_equity() if hasattr(simulator, 'get_equity') else config.paper.initial_balance

    # Calculate daily P&L (simplified)
    daily_pnl = equity - config.paper.initial_balance

    return {
        "mode": config.mode,
        "running": bot_state["running"],
        "positions": positions,
        "equity": equity,
        "daily_pnl": daily_pnl,
        "health": "ok" if bot_state["running"] else "paused"
    }


@app.post("/pause")
async def pause_bot(credentials: HTTPAuthorizationCredentials = Depends(verify_token)):
    """Pause trading."""
    bot_state["running"] = False
    logger = get_logger()
    logger.log_event("bot_paused")
    return {"status": "paused"}


@app.post("/resume")
async def resume_bot(credentials: HTTPAuthorizationCredentials = Depends(verify_token)):
    """Resume trading."""
    bot_state["running"] = True
    logger = get_logger()
    logger.log_event("bot_resumed")
    return {"status": "running"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}