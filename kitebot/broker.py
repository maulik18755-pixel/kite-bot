"""Brokers. PaperBroker simulates fills with Zerodha charges and slippage.

There is deliberately no working live broker. LiveBroker exists so the interface
is clear, but it refuses to place orders. Enable live trading only after the
validation gates in the plan are passed, and only by writing and reviewing that
code yourself.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .costs import apply_slippage, delivery_charges
from .risk import Order


@dataclass
class Position:
    qty: int
    avg_price: float
    stop: float
    entry_day: str
    max_hold: int = 0
    days_held: int = 0


@dataclass
class Account:
    cash: float = 0.0
    units: float = 0.0          # NAV units, so deposits don't distort returns
    deposited: float = 0.0
    charges_paid: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)


class PaperBroker:
    def __init__(self, slippage_pct: float, account: Account | None = None):
        self.slippage_pct = slippage_pct
        self.acct = account or Account()

    # --- valuation ---------------------------------------------------------------
    def equity(self, prices: dict[str, float]) -> float:
        return self.acct.cash + sum(p.qty * prices.get(s, p.avg_price) for s, p in self.acct.positions.items())

    def gross_exposure(self, prices: dict[str, float]) -> float:
        return sum(p.qty * prices.get(s, p.avg_price) for s, p in self.acct.positions.items())

    def nav(self, prices: dict[str, float]) -> float:
        return self.equity(prices) / self.acct.units if self.acct.units else 100.0

    def held(self, symbol: str) -> int:
        p = self.acct.positions.get(symbol)
        return p.qty if p else 0

    def deposit(self, amount: float, prices: dict[str, float]) -> None:
        nav = self.nav(prices)
        self.acct.units += amount / nav
        self.acct.cash += amount
        self.acct.deposited += amount

    # --- fills -------------------------------------------------------------------
    def estimate_buy_cost(self, qty: int, price: float) -> float:
        fill = apply_slippage("BUY", price, self.slippage_pct)
        return qty * fill + delivery_charges("BUY", qty * fill)

    def fill(self, order: Order, price: float, day: str, stop: float = 0.0, max_hold: int = 0) -> dict:
        px = apply_slippage(order.side, price, self.slippage_pct)
        value = order.qty * px
        charges = delivery_charges(order.side, value)
        self.acct.charges_paid += charges
        result = {"symbol": order.symbol, "side": order.side, "qty": order.qty, "ref_price": round(price, 2),
                  "fill_price": round(px, 2), "charges": charges, "reason": order.reason}
        if order.side == "BUY":
            self.acct.cash -= value + charges
            self.acct.positions[order.symbol] = Position(order.qty, px, stop, day, max_hold)
        else:
            pos = self.acct.positions[order.symbol]
            self.acct.cash += value - charges
            pnl = (px - pos.avg_price) * order.qty - charges
            result.update(entry_price=round(pos.avg_price, 2), entry_day=pos.entry_day, pnl=round(pnl, 2),
                          pnl_pct=round((px / pos.avg_price - 1) * 100, 2), days_held=pos.days_held)
            pos.qty -= order.qty
            if pos.qty == 0:
                del self.acct.positions[order.symbol]
        return result

    # --- persistence for daily paper runs -------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self.acct)
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path, slippage_pct: float) -> "PaperBroker":
        if not path.exists():
            return cls(slippage_pct)
        data = json.loads(path.read_text())
        data["positions"] = {s: Position(**p) for s, p in data["positions"].items()}
        return cls(slippage_pct, Account(**data))


class LiveBroker:
    """Placeholder. Refuses every order on purpose."""

    def fill(self, *args, **kwargs):
        raise RuntimeError(
            "Live trading is not implemented. Pass the backtest, out-of-sample and 8-week paper gates first, "
            "then add kite.place_order(variety='regular', exchange='NSE', product='CNC', ...) here yourself."
        )
