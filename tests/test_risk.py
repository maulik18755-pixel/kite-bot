import pytest

from kitebot.broker import PaperBroker
from kitebot.config import RiskConfig, load_config
from kitebot.costs import delivery_charges
from kitebot.engine import Bar, Engine
from kitebot.journal import Journal
from kitebot.risk import Order, RiskManager


def rm(**kw):
    return RiskManager(RiskConfig(**kw), ["NIFTYBEES"])


def test_refuses_anything_but_nse_delivery():
    r = rm()
    assert "delivery" in r.check(Order("NIFTYBEES", "BUY", 1, product="MIS"), 0, 1e6, 100)
    assert "delivery" in r.check(Order("NIFTY25NOVFUT", "BUY", 1, exchange="NFO", product="NRML"), 0, 1e6, 100)
    assert "whitelist" in r.check(Order("RELIANCE", "BUY", 1), 0, 1e6, 100)


def test_no_short_selling():
    assert "short" in rm().check(Order("NIFTYBEES", "SELL", 5), 2, 0, 0)
    assert rm().check(Order("NIFTYBEES", "SELL", 2), 2, 0, 0) is None


def test_no_margin():
    assert "no margin" in rm().check(Order("NIFTYBEES", "BUY", 100), 0, cash=1000, est_cost=28000)


def test_leverage_in_config_is_rejected(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("universe: [NIFTYBEES]\nrisk:\n  max_gross_exposure_pct: 200\n")
    with pytest.raises(ValueError):
        load_config(cfg)


def test_sizing_respects_every_limit():
    r = rm(risk_per_trade_pct=1, max_position_pct=20)
    # risk: 1% of 20k = 200 / (100-90) = 20 shares; position: 20% of 20k / 100 = 40; cash: ~49
    assert r.size_buy(100, 90, equity=20000, cash=5000, gross_exposure=0) == 20
    assert r.size_buy(100, 99, equity=20000, cash=20000, gross_exposure=0) == 40
    assert r.size_buy(100, 90, equity=20000, cash=500, gross_exposure=0) == 4
    assert r.size_buy(100, 90, equity=20000, cash=20000, gross_exposure=20000) == 0


def test_kill_switch_blocks_buys_but_allows_exits():
    r = rm(max_drawdown_pct=15)
    r.start_day("2026-01-01", 100)
    alerts = r.update_nav(84)
    assert any("KILL" in a for a in alerts)
    assert "kill switch" in r.check(Order("NIFTYBEES", "BUY", 1), 0, 1e6, 100)
    assert r.check(Order("NIFTYBEES", "SELL", 1), 1, 0, 0) is None


def test_daily_loss_limit_resets_next_day():
    r = rm(daily_loss_limit_pct=2, max_drawdown_pct=50)
    r.start_day("2026-01-01", 100)
    r.update_nav(97.5)
    assert r.check(Order("NIFTYBEES", "BUY", 1), 0, 1e6, 100) == "daily loss limit hit"
    r.start_day("2026-01-02", 97.5)
    assert r.check(Order("NIFTYBEES", "BUY", 1), 0, 1e6, 100) is None


def test_account_can_never_go_below_zero_cash():
    broker = PaperBroker(0.05)
    broker.deposit(20000, {})
    engine = Engine(broker, rm(risk_per_trade_pct=100, max_position_pct=100), Journal(None))
    engine.run_day("2026-01-01", {"NIFTYBEES": Bar(280, 281, 279, 280)},
                   {"NIFTYBEES": {"entry": True, "exit": False, "stop": 1.0, "max_hold": 0}})
    assert broker.acct.cash >= 0
    assert broker.held("NIFTYBEES") > 0


def test_charges_are_charged():
    assert delivery_charges("BUY", 100000) > 100  # STT alone is Rs 100
    assert delivery_charges("SELL", 100000) > delivery_charges("BUY", 100000) - 15  # DP charge on sells
