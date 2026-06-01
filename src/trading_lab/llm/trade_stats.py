"""Per-instrument execution stats for LLM prompt injection."""

from pathlib import Path

import pandas as pd

# Yahoo symbol → IG instrument name keywords for transaction matching.
# IG transaction names (e.g. "Oil - US Crude", "Spot Gold") don't contain
# the Yahoo symbol (e.g. "CL=F", "GC=F"), so we need an explicit mapping.
_SYMBOL_TO_IG_KEYWORDS: dict[str, list[str]] = {
    "GC=F": ["spot gold", "gold"],
    "CL=F": ["oil - us crude", "us crude"],
    "SI=F": ["spot silver", "silver"],
    "HG=F": ["copper"],
    "NG=F": ["natural gas"],
    "^FTSE": ["ftse 100"],
    "^GSPC": ["us 500", "s&p 500"],
    "^NDX": ["us tech 100", "nasdaq"],
    "^GDAXI": ["germany 40", "dax"],
    "^N225": ["japan 225", "nikkei"],
    "^DJI": ["wall street", "dow"],
    "EURUSD=X": ["eur/usd"],
    "USDJPY=X": ["usd/jpy"],
    "GBPUSD=X": ["gbp/usd"],
    "AUDUSD=X": ["aud/usd"],
}


def build_instrument_stats(
    symbol: str,
    execution_log_path: Path,
    transactions: list[dict] | None = None,
    max_trades: int = 20,
) -> str:
    """Build execution stats summary for a symbol.

    Returns a formatted string ready to inject into the LLM prompt,
    or empty string if insufficient data (< 3 trades).
    """
    closed_trades = _get_closed_trades(symbol, transactions)
    if len(closed_trades) < 3:
        return ""

    # Limit to max_trades most recent
    closed_trades = closed_trades[-max_trades:]

    # Read execution log for stop/order info
    log_stats = _get_log_stats(symbol, execution_log_path, max_trades)

    # Compute stats from closed trades
    n_trades = len(closed_trades)
    winners = [t for t in closed_trades if _pnl_value(t) > 0]
    losers = [t for t in closed_trades if _pnl_value(t) <= 0]
    n_winners = len(winners)
    win_rate_pct = round(100 * n_winners / n_trades)

    # Average winner/loser in points
    avg_winner = _avg_points(winners)
    avg_loser = _avg_points(losers)

    # Build output lines
    lines = [f"## Your Execution History on {symbol} (last {n_trades} closed trades)"]

    # Win rate line
    winner_str = f"+{avg_winner:.0f} pts" if avg_winner else "N/A"
    loser_str = f"-{abs(avg_loser):.0f} pts" if avg_loser else "N/A"
    lines.append(
        f"- Win rate: {n_winners}/{n_trades} ({win_rate_pct}%) "
        f"| Avg winner: {winner_str} | Avg loser: {loser_str}"
    )

    # Stop distance from execution log
    if log_stats.get("avg_stop_distance") is not None:
        lines.append(f"- Avg stop distance: {log_stats['avg_stop_distance']:.0f} pts")

    # Stop hit rate: losers assumed to be stop hits
    n_losers = len(losers)
    if n_losers > 0:
        stop_pct = round(100 * n_losers / n_trades)
        comment = ""
        if stop_pct >= 60:
            comment = " — stops may be too tight if adverse excursion is larger"
        lines.append(
            f"- Stop hit rate: {n_losers}/{n_trades} ({stop_pct}%){comment}"
        )

    # Order type effectiveness
    if log_stats.get("order_types"):
        ot = log_stats["order_types"]
        parts = []
        for otype, counts in ot.items():
            total = counts["wins"] + counts["losses"]
            parts.append(
                f"{otype} orders: {total} ({counts['wins']}W {counts['losses']}L)"
            )
        if parts:
            lines.append("- " + " | ".join(parts))

    # Hold time stats
    hold_stats = _compute_hold_times(closed_trades)
    if hold_stats:
        parts = []
        if hold_stats.get("winners_avg") is not None:
            parts.append(f"Winners avg hold: {hold_stats['winners_avg']:.1f} days")
        if hold_stats.get("losers_avg") is not None:
            parts.append(f"Losers avg hold: {hold_stats['losers_avg']:.1f} days")
        if parts:
            lines.append("- " + " | ".join(parts))

    return "\n".join(lines)


def _pnl_value(trade: dict) -> float:
    """Extract numeric P&L from a transaction dict."""
    pnl = trade.get("pnl", 0)
    if pnl is None:
        return 0.0
    if isinstance(pnl, str):
        # Strip currency symbols and parse
        cleaned = pnl.replace(",", "").replace("£", "").replace("$", "").replace("€", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    return float(pnl)


def _points_moved(trade: dict) -> float | None:
    """Compute points between open and close level."""
    open_level = trade.get("open_level")
    close_level = trade.get("close_level")
    if open_level is None or close_level is None:
        return None
    try:
        ol = float(open_level)
        cl = float(close_level)
    except (ValueError, TypeError):
        return None
    direction = trade.get("direction", "").upper()
    if direction == "BUY":
        return cl - ol
    elif direction == "SELL":
        return ol - cl
    # Fallback: use sign of pnl to infer
    return abs(cl - ol) if _pnl_value(trade) >= 0 else -abs(cl - ol)


def _avg_points(trades: list[dict]) -> float | None:
    """Average points moved for a list of trades."""
    if not trades:
        return None
    points = [_points_moved(t) for t in trades]
    valid = [p for p in points if p is not None]
    if not valid:
        # Fall back to raw pnl / size
        results = []
        for t in trades:
            pnl = _pnl_value(t)
            size = t.get("size")
            if size:
                try:
                    results.append(pnl / float(size))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
        return sum(results) / len(results) if results else None
    return sum(valid) / len(valid)


def _get_closed_trades(symbol: str, transactions: list[dict] | None) -> list[dict]:
    """Filter transactions to closed trades for the given symbol.

    Uses _SYMBOL_TO_IG_KEYWORDS to match Yahoo symbols to IG instrument names
    (e.g. "CL=F" → "Oil - US Crude"). Excludes financing/admin fee rows.
    """
    if not transactions:
        return []
    keywords = _SYMBOL_TO_IG_KEYWORDS.get(symbol, [symbol.lower()])
    result = []
    for t in transactions:
        instrument = (t.get("instrument_name") or "").lower()
        # Skip financing and admin fee rows
        if "daily" in instrument and ("financing" in instrument or "admin fee" in instrument):
            continue
        if any(kw in instrument for kw in keywords):
            if t.get("pnl") is not None:
                result.append(t)
    return result


def _get_log_stats(symbol: str, execution_log_path: Path, max_trades: int) -> dict:
    """Read execution log parquet and compute stop/order stats."""
    stats: dict = {}
    try:
        if not execution_log_path.exists():
            return stats
        df = pd.read_parquet(execution_log_path)
    except Exception:
        return stats

    # Filter to symbol
    if "symbol" not in df.columns:
        return stats
    mask = df["symbol"].str.lower() == symbol.lower()
    df = df[mask].tail(max_trades * 3)  # extra rows to capture context

    # Average stop distance
    if "stop_loss" in df.columns and "entry_level" in df.columns:
        placed = df[df["action"].str.upper() == "PLACED"] if "action" in df.columns else df
        stop_distances = []
        for _, row in placed.iterrows():
            sl = row.get("stop_loss")
            entry = row.get("entry_level")
            if pd.notna(sl) and pd.notna(entry):
                try:
                    stop_distances.append(abs(float(entry) - float(sl)))
                except (ValueError, TypeError):
                    pass
        if stop_distances:
            stats["avg_stop_distance"] = sum(stop_distances) / len(stop_distances)

    # Order type counts
    if "order_type" in df.columns and "action" in df.columns:
        placed = df[df["action"].str.upper() == "PLACED"]
        if not placed.empty and "deal_ref" in placed.columns:
            order_types: dict = {}
            for _, row in placed.iterrows():
                otype = (row.get("order_type") or "MARKET").upper()
                if otype not in order_types:
                    order_types[otype] = {"wins": 0, "losses": 0}
                # We can't determine win/loss from log alone without matching transactions
                # Just count for now; win/loss will be filled if we enhance later
                order_types[otype]["wins"] += 0
                order_types[otype]["losses"] += 0
            # Only include if we have meaningful data
            # For now, just track counts
            if order_types:
                # Store raw counts (wins+losses = total placed per type)
                for otype in order_types:
                    total = len(placed[placed["order_type"].str.upper() == otype])
                    order_types[otype] = {"wins": 0, "losses": 0, "total": total}
                stats["order_types_raw"] = order_types

    return stats


def _compute_hold_times(closed_trades: list[dict]) -> dict:
    """Compute average hold time for winners and losers from transaction dates."""
    # This requires open_date and close_date or a single date field with reference matching
    # For simplicity, check if 'date' field has open/close info or duration
    winners_holds = []
    losers_holds = []

    for t in closed_trades:
        # Try to compute hold time from date fields
        open_date = t.get("open_date") or t.get("dateUtc") or t.get("openDateUtc")
        close_date = t.get("close_date") or t.get("date") or t.get("closeDateUtc")
        if not open_date or not close_date:
            continue
        try:
            open_dt = pd.to_datetime(open_date)
            close_dt = pd.to_datetime(close_date)
            hold_days = (close_dt - open_dt).total_seconds() / 86400
            if hold_days < 0:
                continue
        except Exception:
            continue

        if _pnl_value(t) > 0:
            winners_holds.append(hold_days)
        else:
            losers_holds.append(hold_days)

    result = {}
    if winners_holds:
        result["winners_avg"] = sum(winners_holds) / len(winners_holds)
    if losers_holds:
        result["losers_avg"] = sum(losers_holds) / len(losers_holds)
    return result
