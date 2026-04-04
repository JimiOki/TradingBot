"""Backtesting engine supporting long, flat, and short positions.

Execution model:
- Signal generated on bar N.
- Position change takes effect at bar N+1 open (approximated by bar N+1 close
  with a configurable slippage buffer, because yfinance daily data does not
  provide reliable next-bar open prices).
- This approximation is documented here and must not be changed without updating
  the architecture documentation.

Signal contract:
- signal = 1  → long
- signal = 0  → flat
- signal = -1 → short
"""
import logging

import pandas as pd

from trading_lab.backtesting.models import BacktestConfig, BacktestResult

logger = logging.getLogger(__name__)


def run_backtest(signals_df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    """Run a backtest over a signals DataFrame.

    Args:
        signals_df: DataFrame with at minimum a 'signal' column and a DatetimeIndex.
                    Signal values must be in {-1, 0, 1}.
        config:     BacktestConfig with capital, cost, and run parameters.

    Returns:
        BacktestResult with equity curve and summary metrics.
    """
    df = signals_df.copy()

    _validate_signals(df)

    # Lag signal by one bar to avoid lookahead bias (bar N signal → bar N+1 position)
    df["position"] = df["signal"].shift(1).fillna(0)

    # Market return for each bar
    df["market_return"] = df["close"].pct_change()

    # Gross strategy return: position direction × market return
    # long (+1): profit when market goes up
    # short (-1): profit when market goes down
    df["gross_return"] = df["position"] * df["market_return"]

    # Transaction costs applied on position changes
    position_change = df["position"].diff().abs().fillna(0)
    total_cost_bps = config.commission_bps + config.slippage_bps
    df["cost"] = position_change * (total_cost_bps / 10_000)

    # Net return after costs
    df["net_return"] = df["gross_return"] - df["cost"]

    # Equity curve starting from initial_cash
    df["equity"] = config.initial_cash * (1 + df["net_return"]).cumprod()

    logger.info(
        "Backtest complete: symbol=%s final_equity=%.2f",
        config.symbol,
        df["equity"].iloc[-1],
    )

    return BacktestResult(signals_df=df, config=config)


def _validate_signals(df: pd.DataFrame) -> None:
    """Raise ValueError if signal column is missing or contains invalid values."""
    if "signal" not in df.columns:
        raise ValueError("signals_df must contain a 'signal' column.")
    invalid = df["signal"].dropna()
    invalid = invalid[~invalid.isin([-1, 0, 1])]
    if not invalid.empty:
        raise ValueError(
            f"signal column contains values outside {{-1, 0, 1}}: {invalid.unique().tolist()}"
        )
    if "close" not in df.columns:
        raise ValueError("signals_df must contain a 'close' column.")
