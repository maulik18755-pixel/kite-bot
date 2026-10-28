"""Hard risk limits. Every order goes through RiskManager before any broker sees it.

The loss cap is structural: only fully paid NSE delivery (CNC) buys of whitelisted
symbols, and sells only of shares already held. No margin, futures, options,
intraday or short selling, so the account can never lose more than was put in.

Drawdown and daily loss are measured on NAV per unit, so monthly deposits do not
hide losses or trip the limits.
"""

from dataclasses import asdict, dataclass

from .config import RiskConfig

ALLOWED_EXCHANGE = "NSE"
ALLOWED_PRODUCT = "CNC"


@dataclass
class Order:
    symbol: str
    side: str            # BUY or SELL
    qty: int
    reason: str = ""
    exchange: str = ALLOWED_EXCHANGE
    product: str = ALLOWED_PRODUCT
    order_type: str = "MARKET"


@dataclass
class RiskState:
    day: str = ""
    day_start_nav: float = 0.0
    peak_nav: float = 0.0
    orders_today: int = 0
    halted_today: bool = False
    killed: bool = False
    kill_reason: str = ""


class RiskManager:
    def __init__(self, cfg: RiskConfig, universe: list[str], state: RiskState | None = None):
        self.cfg = cfg
        self.universe = set(universe)
        self.state = state or RiskState()

    # --- day and equity tracking -------------------------------------------------
    def start_day(self, day: str, nav: float) -> None:
        if day != self.state.day:
            self.state.day = day
            self.state.day_start_nav = nav
            self.state.orders_today = 0
            self.state.halted_today = False
        self.state.peak_nav = max(self.state.peak_nav, nav)

    def update_nav(self, nav: float) -> list[str]:
        """Check the daily loss limit and the kill switch. Returns any new alerts."""
        s, alerts = self.state, []
        s.peak_nav = max(s.peak_nav, nav)
        if s.day_start_nav and not s.halted_today:
            day_loss = (1 - nav / s.day_start_nav) * 100
            if day_loss >= self.cfg.daily_loss_limit_pct:
                s.halted_today = True
                alerts.append(f"daily loss {day_loss:.2f}% hit the {self.cfg.daily_loss_limit_pct}% limit; no new buys today")
        if s.peak_nav and not s.killed:
            dd = (1 - nav / s.peak_nav) * 100
            if dd >= self.cfg.max_drawdown_pct:
                s.killed = True
                s.kill_reason = f"drawdown {dd:.2f}% from peak on {s.day}"
                alerts.append(f"KILL SWITCH: {s.kill_reason}; no new buys until reset by hand")
        return alerts

    def reset_kill_switch(self, nav: float) -> None:
        self.state.killed = False
        self.state.kill_reason = ""
        self.state.peak_nav = nav

    # --- sizing and checks -------------------------------------------------------
    def size_buy(self, price: float, stop: float, equity: float, cash: float, gross_exposure: float) -> int:
        """Largest quantity that fits every limit, or 0."""
        if not price > 0:
            return 0
        risk_per_share = price - stop if stop and stop < price else price * 0.1
        by_risk = equity * self.cfg.risk_per_trade_pct / 100 / risk_per_share
        by_position = equity * self.cfg.max_position_pct / 100 / price
        by_exposure = (equity * self.cfg.max_gross_exposure_pct / 100 - gross_exposure) / price
        by_cash = cash * 0.995 / price  # leave room for charges; never spend money that isn't there
        return max(0, int(min(by_risk, by_position, by_exposure, by_cash)))

    def check(self, order: Order, held_qty: int, cash: float, est_cost: float) -> str | None:
        """Return a rejection reason, or None if the order may go ahead."""
        if order.exchange != ALLOWED_EXCHANGE or order.product != ALLOWED_PRODUCT:
            return f"only {ALLOWED_EXCHANGE} {ALLOWED_PRODUCT} (delivery) orders are allowed"
        if order.symbol not in self.universe:
            return f"{order.symbol} is not in the whitelist"
        if order.qty <= 0:
            return "quantity must be positive"
        if order.side == "SELL":
            # Exits are always allowed so a halted bot can still get out; short selling is not.
            if order.qty > held_qty:
                return f"cannot sell {order.qty}, only {held_qty} held (no short selling)"
            return None
        if order.side != "BUY":
            return f"unknown side {order.side}"
        if self.state.killed:
            return f"kill switch active ({self.state.kill_reason})"
        if self.state.halted_today:
            return "daily loss limit hit"
        if self.state.orders_today >= self.cfg.max_orders_per_day:
            return "max orders per day reached"
        if est_cost > cash:
            return f"needs Rs {est_cost:,.0f} but only Rs {cash:,.0f} cash (no margin)"
        return None

    def record_order(self) -> None:
        self.state.orders_today += 1

    def to_dict(self) -> dict:
        return asdict(self.state)
