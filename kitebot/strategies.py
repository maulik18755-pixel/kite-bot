"""Strategies turn daily bars into entry/exit signals and a protective stop.

Signals on day t are computed with data up to the close of t, and the backtester
fills them at the open of t+1, so nothing peeks at the future.

Each strategy returns a DataFrame indexed like the input with columns:
  entry (bool), exit (bool), stop (float: stop price for a new entry), max_hold (int or 0)
"""

import pandas as pd


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(n).mean()


def rsi(close: pd.Series, n: int = 2) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, 1e-12))


def trend_following(df: pd.DataFrame, entry_n: int = 55, exit_n: int = 20, filter_n: int = 200) -> pd.DataFrame:
    """Donchian breakout with a long-term trend filter. Long only."""
    prior_high = df["high"].rolling(entry_n).max().shift()
    prior_low = df["low"].rolling(exit_n).min().shift()
    sma = df["close"].rolling(filter_n).mean()
    entry = (df["close"] > prior_high) & (df["close"] > sma)
    exit_ = df["close"] < prior_low
    stop = df["close"] - 3 * atr(df)
    return pd.DataFrame({"entry": entry, "exit": exit_, "stop": stop, "max_hold": 0}, index=df.index)


def mean_reversion(df: pd.DataFrame, filter_n: int = 200, rsi_buy: float = 10, hold_days: int = 5) -> pd.DataFrame:
    """Buy short, sharp dips in a long-term uptrend; sell on the bounce or after hold_days."""
    sma = df["close"].rolling(filter_n).mean()
    r = rsi(df["close"], 2)
    entry = (df["close"] > sma) & (r < rsi_buy)
    exit_ = df["close"] > df["close"].rolling(5).mean()
    stop = df["close"] - 3 * atr(df)
    return pd.DataFrame({"entry": entry, "exit": exit_, "stop": stop, "max_hold": hold_days}, index=df.index)


STRATEGIES = {"trend": trend_following, "meanrev": mean_reversion}

# Bump this whenever a rule or parameter above changes, so the journal records which rules made each trade.
RULES_VERSION = "2026-10-28.1"
