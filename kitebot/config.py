"""Load and validate config.yaml."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 20.0
    max_gross_exposure_pct: float = 100.0
    daily_loss_limit_pct: float = 2.0
    max_drawdown_pct: float = 15.0
    max_orders_per_day: int = 20


@dataclass
class Config:
    universe: list[str]
    strategy: str = "trend"
    start_capital: float = 20000.0
    monthly_contribution: float = 20000.0
    slippage_pct: float = 0.05
    cash_yield_pct: float = 0.0  # yearly return on idle cash parked in a liquid ETF; 0 = idle cash earns nothing
    risk: RiskConfig = field(default_factory=RiskConfig)
    live_enabled: bool = False


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        path = Path(__file__).resolve().parent.parent / "config.example.yaml"
    raw = yaml.safe_load(path.read_text())
    risk = RiskConfig(**(raw.get("risk") or {}))
    if risk.max_gross_exposure_pct > 100:
        raise ValueError("max_gross_exposure_pct above 100 means leverage, which this bot does not allow")
    return Config(
        universe=[s.upper() for s in raw["universe"]],
        strategy=raw.get("strategy", "trend"),
        start_capital=float(raw.get("start_capital", 20000)),
        monthly_contribution=float(raw.get("monthly_contribution", 0)),
        slippage_pct=float((raw.get("costs") or {}).get("slippage_pct", 0.05)),
        cash_yield_pct=float(raw.get("cash_yield_pct", 0.0)),
        risk=risk,
        live_enabled=bool((raw.get("live") or {}).get("enabled", False)),
    )
