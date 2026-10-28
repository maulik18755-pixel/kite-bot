"""Daily OHLCV data: from Kite Connect (cached to CSV) or synthetic for offline testing."""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path("data")
MAX_DAYS_PER_REQUEST = 1900  # Kite allows about 2000 days of daily candles per call


def instrument_tokens(kite, symbols: list[str]) -> dict[str, int]:
    instruments = kite.instruments("NSE")
    lookup = {i["tradingsymbol"]: i["instrument_token"] for i in instruments}
    missing = [s for s in symbols if s not in lookup]
    if missing:
        raise ValueError(f"Not found on NSE: {missing}")
    return {s: lookup[s] for s in symbols}


def fetch_daily(kite, symbol: str, token: int, start: date, end: date) -> pd.DataFrame:
    """Download daily candles in chunks and cache them to data/<symbol>.csv."""
    frames = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_PER_REQUEST), end)
        rows = kite.historical_data(token, chunk_start, chunk_end, "day")
        if rows:
            frames.append(pd.DataFrame(rows))
        chunk_start = chunk_end + timedelta(days=1)
    if not frames:
        raise ValueError(f"No data returned for {symbol}")
    df = pd.concat(frames)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df.drop_duplicates("date").set_index("date").sort_index()[["open", "high", "low", "close", "volume"]]
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_DIR / f"{symbol}.csv")
    return df


def load_cached(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing. Run: python -m kitebot fetch")
    return pd.read_csv(path, index_col="date", parse_dates=True)


def synthetic(symbols: list[str], years: int = 12, seed: int = 7) -> dict[str, pd.DataFrame]:
    """Random-walk prices with trending and choppy regimes. For testing the plumbing only;
    results on synthetic data say nothing about real-market performance."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=years * 250)
    out = {}
    for sym in symbols:
        regime_drift = np.repeat(rng.normal(0.0004, 0.0012, len(days) // 60 + 1), 60)[: len(days)]
        rets = regime_drift + rng.normal(0, 0.012, len(days))
        close = 100 * np.exp(np.cumsum(rets))
        open_ = close * np.exp(rng.normal(0, 0.004, len(days)))
        spread = np.abs(rng.normal(0, 0.008, len(days)))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        vol = rng.integers(100_000, 1_000_000, len(days))
        out[sym] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=days
        ).rename_axis("date")
    return out


def yahoo(symbols: list[str], start: str, end: str | None = None) -> dict[str, pd.DataFrame]:
    """Free daily NSE data from Yahoo Finance (SYMBOL.NS), for backtests before Kite Connect.
    Prices are split- and dividend-adjusted, so they can differ slightly from what traded on the day."""
    import yfinance as yf

    out = {}
    for sym in symbols:
        df = yf.download(f"{sym}.NS", start=start, end=end, auto_adjust=True, progress=False, multi_level_index=False)
        if df.empty:
            raise ValueError(f"No Yahoo data for {sym}.NS")
        df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        out[sym] = df.rename_axis("date").dropna()
        DATA_DIR.mkdir(exist_ok=True)
        out[sym].to_csv(DATA_DIR / f"{sym}.csv")
    return out


EOD2_URL = "https://raw.githubusercontent.com/BennyThadikaran/eod2_data/main/daily/{}.csv"


def eod2(symbols: list[str], start: str, end: str | None = None) -> dict[str, pd.DataFrame]:
    """Free NSE end-of-day data from the open eod2_data project on GitHub (from NSE bhavcopies,
    adjusted for splits and bonuses, updated each trading day). Not survivorship-bias free."""
    out = {}
    for sym in symbols:
        df = pd.read_csv(EOD2_URL.format(sym.lower()), index_col="Date", parse_dates=True)
        df = adjust_splits(df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].rename_axis("date"))
        df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        out[sym] = df.dropna()
        DATA_DIR.mkdir(exist_ok=True)
        out[sym].to_csv(DATA_DIR / f"{sym}.csv")
    return out


def adjust_splits(df: pd.DataFrame, threshold: float = 2.5) -> pd.DataFrame:
    """Back-adjust unadjusted splits (eod2 adjusts stocks but not every ETF, e.g. GOLDBEES).
    A one-day price ratio beyond 2.5x is treated as a split and rounded to a whole factor."""
    df = df.copy()
    ratio = df["close"].shift() / df["close"]
    for day, r in ratio[(ratio > threshold) | (ratio < 1 / threshold)].items():
        factor = round(r) if r > 1 else 1 / round(1 / r)
        earlier = df.index < day
        df.loc[earlier, ["open", "high", "low", "close"]] /= factor
        df.loc[earlier, "volume"] *= factor
    return df
