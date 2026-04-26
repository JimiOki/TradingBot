"""Backtest result persistence.

Saves backtest artefacts to data/backtests/ following the project naming conventions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from trading_lab.backtesting.metrics import compute_all
from trading_lab.backtesting.models import BacktestResult
from trading_lab.paths import BACKTEST_DATA_DIR

logger = logging.getLogger(__name__)


def save_result(result: BacktestResult, label: str | None = None) -> tuple[Path, Path]:
    """Save a BacktestResult to disk.

    Artefacts:
    - Summary JSON:  <symbol>_<timeframe>_<strategy>_<timestamp>_<label>_summary.json
    - Trades Parquet: <symbol>_<timeframe>_<strategy>_<timestamp>_<label>_trades.parquet

    Args:
        result: Completed BacktestResult.
        label:  Optional label suffix (e.g. 'in_sample', 'out_of_sample', 'full').
                Defaults to result.config.mode.

    Returns:
        Tuple of (summary_path, trades_path).
    """
    BACKTEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    mode = label or result.config.mode
    cfg = result.config

    stem = f"{cfg.symbol}_{cfg.timeframe}_{cfg.strategy_name}_{ts}_{mode}"
    summary_path = BACKTEST_DATA_DIR / f"{stem}_summary.json"
    trades_path = BACKTEST_DATA_DIR / f"{stem}_trades.parquet"

    # Compute metrics
    metrics = compute_all(result)

    # Save summary
    summary = {
        "config": {
            "symbol": cfg.symbol,
            "strategy_name": cfg.strategy_name,
            "timeframe": cfg.timeframe,
            "initial_cash": cfg.initial_cash,
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
            "strategy_params": cfg.strategy_params,
            "mode": cfg.mode,
            "oos_ratio": cfg.oos_ratio,
            "start_date": str(cfg.start_date) if cfg.start_date else None,
            "end_date": str(cfg.end_date) if cfg.end_date else None,
        },
        "metrics": metrics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    # Save trade-level data
    df = result.signals_df.dropna(subset=["position"])
    trades = df[df["position"] != 0][
        ["close", "signal", "position", "net_return", "equity"]
    ]
    trades.to_parquet(trades_path)

    logger.info("Backtest saved: %s", stem)
    return summary_path, trades_path
