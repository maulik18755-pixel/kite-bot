"""Daily paper-trading run on live Kite data. No real orders are ever sent.

Run once each trading day after 9:20 IST:  python -m kitebot paper
Signals use daily candles up to yesterday's close; fills use the current LTP.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .auth import get_kite
from .broker import PaperBroker
from .config import Config
from .engine import Bar, Engine
from .journal import Journal
from .risk import RiskManager, RiskState
from .strategies import STRATEGIES

STATE_DIR = Path("state")
ACCOUNT_FILE = STATE_DIR / "paper_account.json"
RISK_FILE = STATE_DIR / "paper_risk.json"
JOURNAL_FILE = STATE_DIR / "paper_journal.jsonl"


def load_risk(cfg: Config) -> RiskManager:
    state = RiskState(**json.loads(RISK_FILE.read_text())) if RISK_FILE.exists() else None
    return RiskManager(cfg.risk, cfg.universe, state)


def run_paper_day(cfg: Config, force: bool = False) -> None:
    from .data import instrument_tokens

    today = date.today().isoformat()
    broker = PaperBroker.load(ACCOUNT_FILE, cfg.slippage_pct)
    risk = load_risk(cfg)
    if risk.state.day == today and not force:
        raise SystemExit("Already ran today. Use --force only if the earlier run failed part way.")
    journal = Journal(JOURNAL_FILE)

    kite = get_kite()
    tokens = instrument_tokens(kite, cfg.universe)
    strategy = STRATEGIES[cfg.strategy]
    quotes = kite.ltp([f"NSE:{s}" for s in cfg.universe])
    ltp = {s: quotes[f"NSE:{s}"]["last_price"] for s in cfg.universe}

    signals = {}
    for sym, tok in tokens.items():
        rows = kite.historical_data(tok, date.today() - timedelta(days=450), date.today() - timedelta(days=1), "day")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        sig = strategy(df.set_index("date")).iloc[-1]
        if not sig.isna().any():
            signals[sym] = {"entry": bool(sig.entry), "exit": bool(sig.exit), "stop": float(sig.stop), "max_hold": int(sig.max_hold)}
            journal.log("signal", today, symbol=sym, **signals[sym], ltp=ltp[sym])

    month = today[:7]
    last_deposit_month = next((e["day"][:7] for e in reversed(Journal.read(JOURNAL_FILE)) if e["event"] == "deposit"), None)
    if last_deposit_month != month:
        amount = cfg.start_capital if broker.acct.deposited == 0 else cfg.monthly_contribution
        broker.deposit(amount, ltp)
        journal.log("deposit", today, amount=amount)

    bars = {s: Bar(p, p, p, p) for s, p in ltp.items()}
    Engine(broker, risk, journal).run_day(today, bars, signals)

    broker.save(ACCOUNT_FILE)
    RISK_FILE.write_text(json.dumps(risk.to_dict(), indent=2))
    eq = broker.equity(ltp)
    journal.log("eod", today, equity=round(eq, 2), cash=round(broker.acct.cash, 2), nav=round(broker.nav(ltp), 4),
                deposited=broker.acct.deposited, positions={s: p.qty for s, p in broker.acct.positions.items()})
    print(f"Paper equity Rs {eq:,.0f} (deposited Rs {broker.acct.deposited:,.0f}), cash Rs {broker.acct.cash:,.0f}")
    for s, p in broker.acct.positions.items():
        print(f"  {s}: {p.qty} @ {p.avg_price:.2f}, stop {p.stop:.2f}")
    if risk.state.killed:
        print(f"KILL SWITCH ACTIVE: {risk.state.kill_reason}")
