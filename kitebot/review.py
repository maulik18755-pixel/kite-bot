"""Learning-loop review: compare journaled results with the backtest and write a review note."""

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from .journal import Journal

TEMPLATE = """
## Lessons (fill in by hand)

- What went differently from the backtest, and why?
- Hypothesis to test (one rule change, stated so it can be backtested):
- Result of backtest / out-of-sample / 4-week paper test:
- Decision: promote, drop, or keep testing. If promoted, bump RULES_VERSION in strategies.py.

Guardrails: no rule changes in a week with a loss over 1% of the account; at most one promoted change a month.
"""


def review(journal_path: Path, days: int, backtest_summary: Path, out_dir: Path) -> str:
    since = (date.today() - timedelta(days=days)).isoformat()
    entries = [e for e in Journal.read(journal_path) if e["day"] >= since]
    fills = [e for e in entries if e["event"] == "fill"]
    closed = [e for e in fills if e["side"] == "SELL"]
    pnls = [e["pnl"] for e in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    slip = [abs(e["fill_price"] / e["ref_price"] - 1) * 100 for e in fills if e.get("ref_price")]

    lines = [f"# Review {date.today()} (last {days} days)", ""]
    lines.append(f"- Orders filled: {len(fills)}, closed trades: {len(closed)}")
    if pnls:
        lines.append(f"- Win rate {len(wins) / len(pnls) * 100:.0f}%, net P&L Rs {sum(pnls):,.0f}, "
                     f"avg win Rs {sum(wins) / max(len(wins), 1):,.0f}, avg loss Rs {sum(losses) / max(len(losses), 1):,.0f}")
    lines.append(f"- Charges paid: Rs {sum(e['charges'] for e in fills):,.0f}; avg slippage {sum(slip) / max(len(slip), 1):.3f}%")
    rules = sorted({e["rules"] for e in entries})
    lines.append(f"- Rule versions in force: {', '.join(rules) or 'none'}")
    for why, n in Counter(e["why"] for e in entries if e["event"] in ("reject", "skip")).most_common():
        lines.append(f"- Blocked {n}x: {why}")
    for e in entries:
        if e["event"] == "alert":
            lines.append(f"- ALERT {e['day']}: {e['message']}")
    eods = [e for e in entries if e["event"] == "eod"]
    if eods:
        lines.append(f"- Equity Rs {eods[-1]['equity']:,.0f} vs Rs {eods[-1]['deposited']:,.0f} deposited")
    if backtest_summary.exists() and pnls:
        bt = json.loads(backtest_summary.read_text())
        live_wr = len(wins) / len(pnls) * 100
        lines += ["", "## Against the backtest",
                  f"- Win rate: {live_wr:.0f}% now vs {bt['win_rate_pct']}% in backtest",
                  f"- Avg loss: Rs {sum(losses) / max(len(losses), 1):,.0f} now vs Rs {bt['avg_loss']:,} in backtest"]
        if live_wr < bt["win_rate_pct"] - 15:
            lines.append("- Win rate is well below the backtest. Check fills and data before touching the rules.")
    text = "\n".join(lines) + "\n" + TEMPLATE
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"review-{date.today()}.md").write_text(text)
    return text
