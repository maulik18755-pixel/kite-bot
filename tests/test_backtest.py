from kitebot.backtest import run_backtest
from kitebot.config import Config
from kitebot.data import synthetic


def test_backtest_runs_and_never_overspends():
    cfg = Config(universe=["AAA", "BBB", "CCC"], start_capital=20000, monthly_contribution=20000)
    for strategy in ("trend", "meanrev"):
        cfg.strategy = strategy
        res = run_backtest(cfg, synthetic(cfg.universe, years=4))
        s = res["summary"]
        assert s["deposited"] == 20000 * len({(d.year, d.month) for d in res["curve"].index})
        assert (res["curve"]["exposure"] <= 1.0001).all()  # never leveraged
        assert all(e["side"] in ("BUY", "SELL") for e in res["journal"] if e["event"] == "fill")


def test_signals_are_not_used_on_the_same_day():
    """A buy must fill at the open of the day after the signal, never the signal day itself."""
    cfg = Config(universe=["AAA"], strategy="trend", start_capital=100000, monthly_contribution=0)
    data = synthetic(cfg.universe, years=4)
    res = run_backtest(cfg, data)
    from kitebot.strategies import trend_following
    raw = trend_following(data["AAA"])
    for e in res["journal"]:
        if e["event"] == "fill" and e["side"] == "BUY":
            day = data["AAA"].index.get_loc(__import__("pandas").Timestamp(e["day"]))
            assert raw["entry"].iloc[day - 1]


def test_split_adjustment():
    import pandas as pd

    from kitebot.data import adjust_splits
    df = pd.DataFrame({"open": [3370.1, 30.2, 33.8], "high": [3370.1, 36.3, 33.9], "low": [3351.1, 30.1, 33.55],
                       "close": [3359.6, 33.55, 33.65], "volume": [4386, 1664422, 483572]},
                      index=pd.to_datetime(["2019-12-18", "2019-12-19", "2019-12-20"]))
    adj = adjust_splits(df)
    assert abs(adj["close"].iloc[0] - 33.596) < 0.01  # 1:100 split, factor from close-to-close
