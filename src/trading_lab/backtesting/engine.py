import pandas as pd

from trading_lab.backtesting.models import BacktestConfig


def run_long_flat_backtest(signals: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """Run a minimal long/flat backtest off a signal dataframe."""
    required_columns = {"timestamp", "close", "signal"}
    missing = required_columns.difference(signals.columns)
    if missing:
        raise ValueError(f"Signals dataframe is missing columns: {sorted(missing)}")

    frame = signals.copy().sort_values("timestamp").reset_index(drop=True)
    frame["market_return"] = frame["close"].pct_change().fillna(0.0)
    frame["position"] = frame["signal"].clip(lower=0).shift(1).fillna(0.0)
    frame["gross_return"] = frame["position"] * frame["market_return"]

    trade_events = frame["position"].diff().abs().fillna(frame["position"])
    cost_rate = (config.commission_bps + config.slippage_bps) / 10000
    frame["cost_return"] = trade_events * cost_rate
    frame["net_return"] = frame["gross_return"] - frame["cost_return"]
    frame["equity_curve"] = config.initial_cash * (1 + frame["net_return"]).cumprod()

    return frame
