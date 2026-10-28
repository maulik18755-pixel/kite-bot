"""Daily-bar backtester. Signals at day t's close are filled at day t+1's open."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .broker import PaperBroker
from .config import Config
from .engine import Bar, Engine
from .journal import Journal
from .risk import RiskManager
from .strategies import RULES_VERSION, STRATEGIES


def run_backtest(cfg: Config, data: dict[str, pd.DataFrame], start: str | None = None, end: str | None = None,
                 journal_path: str | Path | None = None) -> dict:
    strategy = STRATEGIES[cfg.strategy]
    # Signals use the full history (warm-up included), then shift one day so day t sees only t-1's signal.
    signals = {s: strategy(df).shift(1) for s, df in data.items()}
    calendar = sorted(set().union(*[df.index for df in data.values()]))
    calendar = [d for d in calendar if (start is None or d >= pd.Timestamp(start)) and (end is None or d <= pd.Timestamp(end))]
    if not calendar:
        raise ValueError("no trading days in the chosen window")

    broker = PaperBroker(cfg.slippage_pct)
    risk = RiskManager(cfg.risk, list(data))
    journal = Journal(journal_path)
    engine = Engine(broker, risk, journal)

    nav_rows, last_month = [], None
    for day in calendar:
        bars, sigs, opens = {}, {}, {}
        for sym, df in data.items():
            if day not in df.index:
                continue
            row = df.loc[day]
            bars[sym] = Bar(row.open, row.high, row.low, row.close)
            opens[sym] = row.open
            sig = signals[sym].loc[day]
            if not sig.isna().any():
                sigs[sym] = {"entry": bool(sig.entry), "exit": bool(sig.exit), "stop": float(sig.stop), "max_hold": int(sig.max_hold)}
        month = (day.year, day.month)
        if month != last_month:
            amount = cfg.start_capital if last_month is None else cfg.monthly_contribution
            if amount:
                broker.deposit(amount, opens)
                journal.log("deposit", day.date().isoformat(), amount=amount)
            last_month = month
        if cfg.cash_yield_pct and broker.acct.cash > 0:
            broker.acct.cash *= (1 + cfg.cash_yield_pct / 100) ** (1 / 252)
        engine.run_day(day.date().isoformat(), bars, sigs)
        closes = {s: b.close for s, b in bars.items()}
        nav_rows.append({"date": day, "nav": broker.nav(closes), "equity": broker.equity(closes),
                         "deposited": broker.acct.deposited, "exposure": broker.gross_exposure(closes) / max(broker.equity(closes), 1e-9)})

    curve = pd.DataFrame(nav_rows).set_index("date")
    bench = _benchmark(data, curve.index)
    return {"summary": _summary(cfg, curve, journal.entries, broker, risk, bench), "curve": curve, "journal": journal.entries}


def _benchmark(data: dict[str, pd.DataFrame], index: pd.Index) -> pd.Series:
    """Equal-weight buy-and-hold of the universe, no costs: the bar the strategy has to beat."""
    closes = pd.DataFrame({s: df["close"] for s, df in data.items()}).reindex(index).ffill()
    rets = closes.pct_change().mean(axis=1).fillna(0)
    return 100 * (1 + rets).cumprod()


def _stats(nav: pd.Series) -> dict:
    years = max(len(nav) / 252, 1e-9)
    rets = nav.pct_change().dropna()
    dd = (nav / nav.cummax() - 1).min()
    return {
        "cagr_pct": round(((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1) * 100, 2),
        "max_drawdown_pct": round(dd * 100, 2),
        "sharpe": round(rets.mean() / rets.std() * np.sqrt(252), 2) if rets.std() > 0 else 0.0,
    }


def _summary(cfg, curve, entries, broker, risk, bench) -> dict:
    closed = [e for e in entries if e["event"] == "fill" and e["side"] == "SELL"]
    pnls = [e["pnl"] for e in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "strategy": cfg.strategy,
        "rules_version": RULES_VERSION,
        "period": f"{curve.index[0].date()} to {curve.index[-1].date()}",
        "deposited": round(broker.acct.deposited),
        "final_equity": round(curve["equity"].iloc[-1]),
        **_stats(curve["nav"]),
        "benchmark": _stats(bench),
        "trades": len(closed),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
        "avg_win": round(np.mean(wins)) if wins else 0,
        "avg_loss": round(np.mean(losses)) if losses else 0,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
        "avg_days_held": round(np.mean([e["days_held"] for e in closed]), 1) if closed else 0,
        "charges_paid": round(broker.acct.charges_paid),
        "avg_exposure_pct": round(curve["exposure"].mean() * 100, 1),
        "rejects": sum(1 for e in entries if e["event"] == "reject"),
        "skips_too_small": sum(1 for e in entries if e["event"] == "skip"),
        "kill_switch": risk.state.kill_reason or None,
    }


def save_report(result: dict, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "backtest_summary.json").write_text(json.dumps(result["summary"], indent=2))
    result["curve"].to_csv(out / "backtest_equity.csv")
    with (out / "backtest_journal.jsonl").open("w") as f:
        for e in result["journal"]:
            f.write(json.dumps(e, default=str) + "\n")
    return out
