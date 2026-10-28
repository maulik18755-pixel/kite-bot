"""Command line: python -m kitebot <command>"""

import argparse
import json
from datetime import date
from pathlib import Path

from .config import load_config


def main() -> None:
    p = argparse.ArgumentParser(prog="kitebot", description="Cash-only, paper-first Kite trading bot")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="log in to Kite for today")
    f = sub.add_parser("fetch", help="download daily history for the universe")
    f.add_argument("--years", type=int, default=12)
    b = sub.add_parser("backtest", help="run a backtest")
    b.add_argument("--source", choices=["kite", "eod2", "yahoo", "synthetic"], default="kite")
    b.add_argument("--strategy", help="override the strategy in config")
    b.add_argument("--start", help="first trading day, YYYY-MM-DD")
    b.add_argument("--end")
    b.add_argument("--universe", help="comma-separated symbols, overrides config")
    b.add_argument("--cash-yield", type=float, help="yearly %% earned on idle cash (e.g. 6 for a liquid ETF)")
    pa = sub.add_parser("paper", help="run today's paper-trading step")
    pa.add_argument("--force", action="store_true")
    r = sub.add_parser("review", help="learning-loop review of the paper journal")
    r.add_argument("--days", type=int, default=7)
    sub.add_parser("reset-kill-switch", help="clear the kill switch after a manual review")
    args = p.parse_args()
    cfg = load_config(args.config)

    if args.cmd == "login":
        from .auth import login_interactive
        login_interactive()

    elif args.cmd == "fetch":
        from datetime import timedelta

        from .auth import get_kite
        from .data import fetch_daily, instrument_tokens
        kite = get_kite()
        for sym, tok in instrument_tokens(kite, cfg.universe).items():
            df = fetch_daily(kite, sym, tok, date.today() - timedelta(days=365 * args.years), date.today())
            print(f"{sym}: {len(df)} days, {df.index[0].date()} to {df.index[-1].date()}")

    elif args.cmd == "backtest":
        from .backtest import run_backtest, save_report
        from .data import load_cached, synthetic
        if args.strategy:
            cfg.strategy = args.strategy
        if args.cash_yield is not None:
            cfg.cash_yield_pct = args.cash_yield
        if args.universe:
            cfg.universe = [u.strip().upper() for u in args.universe.split(",")]
        if args.source == "synthetic":
            data = synthetic(cfg.universe)
        elif args.source in ("eod2", "yahoo"):
            from datetime import timedelta
            from . import data as data_mod
            # Two years before the window so the 200-day filter is warmed up on day one.
            first = date.fromisoformat(args.start) if args.start else date.today() - timedelta(days=365 * 12)
            data = getattr(data_mod, args.source)(cfg.universe, (first - timedelta(days=730)).isoformat(), args.end)
        else:
            data = {s: load_cached(s) for s in cfg.universe}
        result = run_backtest(cfg, data, args.start, args.end)
        out = save_report(result)
        print(json.dumps(result["summary"], indent=2))
        if args.source == "synthetic":
            print("\nSynthetic data only tests the plumbing. These numbers say nothing about real markets.")
        print(f"\nReport written to {out}/")

    elif args.cmd == "paper":
        from .paper import run_paper_day
        run_paper_day(cfg, args.force)

    elif args.cmd == "review":
        from .paper import JOURNAL_FILE
        from .review import review
        print(review(JOURNAL_FILE, args.days, Path("reports/backtest_summary.json"), Path("reports")))

    elif args.cmd == "reset-kill-switch":
        from .broker import PaperBroker
        from .paper import ACCOUNT_FILE, RISK_FILE, load_risk
        risk = load_risk(cfg)
        broker = PaperBroker.load(ACCOUNT_FILE, cfg.slippage_pct)
        risk.reset_kill_switch(broker.nav({}))
        RISK_FILE.write_text(json.dumps(risk.to_dict(), indent=2))
        print("Kill switch cleared. Peak reset to current NAV.")


if __name__ == "__main__":
    main()
