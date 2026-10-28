"""One trading day: exits, entries, stops, all through the risk manager and journal.

Shared by the backtester and the daily paper run, so both follow exactly the same rules.
"""

from dataclasses import dataclass

from .broker import PaperBroker
from .journal import Journal
from .risk import Order, RiskManager


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float


class Engine:
    def __init__(self, broker: PaperBroker, risk: RiskManager, journal: Journal):
        self.broker = broker
        self.risk = risk
        self.journal = journal

    def _sell(self, day: str, symbol: str, price: float, reason: str) -> None:
        order = Order(symbol, "SELL", self.broker.held(symbol), reason)
        rejected = self.risk.check(order, self.broker.held(symbol), self.broker.acct.cash, 0)
        if rejected:
            self.journal.log("reject", day, symbol=symbol, side="SELL", why=rejected)
            return
        self.risk.record_order()
        self.journal.log("fill", day, **self.broker.fill(order, price, day))

    def run_day(self, day: str, bars: dict[str, Bar], signals: dict[str, dict]) -> None:
        """bars: today's prices. signals: computed from data up to the previous close."""
        opens = {s: b.open for s, b in bars.items()}
        self.risk.start_day(day, self.broker.nav(opens))

        # 1. Exits at the open: exit signal, time stop, or a gap below the stop.
        for sym, pos in list(self.broker.acct.positions.items()):
            if sym not in bars:
                continue
            pos.days_held += 1
            sig, bar = signals.get(sym, {}), bars[sym]
            if bar.open <= pos.stop:
                self._sell(day, sym, bar.open, "gap below stop")
            elif sig.get("exit"):
                self._sell(day, sym, bar.open, "exit signal")
            elif pos.max_hold and pos.days_held > pos.max_hold:
                self._sell(day, sym, bar.open, f"time stop {pos.max_hold}d")

        # 2. Entries at the open.
        for sym, sig in sorted(signals.items()):
            if not sig.get("entry") or sym not in bars or self.broker.held(sym):
                continue
            price = bars[sym].open
            equity = self.broker.equity(opens)
            qty = self.risk.size_buy(price, sig.get("stop", 0), equity, self.broker.acct.cash,
                                     self.broker.gross_exposure(opens))
            if qty < 1:
                self.journal.log("skip", day, symbol=sym, why="position size rounds to zero", price=round(price, 2))
                continue
            order = Order(sym, "BUY", qty, "entry signal")
            rejected = self.risk.check(order, 0, self.broker.acct.cash, self.broker.estimate_buy_cost(qty, price))
            if rejected:
                self.journal.log("reject", day, symbol=sym, side="BUY", why=rejected)
                continue
            self.risk.record_order()
            self.journal.log("fill", day, stop=round(sig["stop"], 2), **self.broker.fill(order, price, day, sig["stop"], int(sig.get("max_hold", 0))))

        # 3. Intraday stops.
        for sym, pos in list(self.broker.acct.positions.items()):
            if sym in bars and bars[sym].low <= pos.stop:
                self._sell(day, sym, pos.stop, "stop hit")

        # 4. Mark to market and check the daily loss limit and kill switch.
        closes = {s: b.close for s, b in bars.items()}
        for alert in self.risk.update_nav(self.broker.nav(closes)):
            self.journal.log("alert", day, message=alert)
