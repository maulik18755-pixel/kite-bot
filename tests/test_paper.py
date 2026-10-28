"""Paper run against a fake Kite client, so it can be tested without logging in."""

from datetime import date

import pytest

from kitebot import paper
from kitebot.config import Config
from kitebot.data import synthetic
from kitebot.review import review


class FakeKite:
    def __init__(self, data):
        self.data = data

    def instruments(self, exchange):
        return [{"tradingsymbol": s, "instrument_token": i} for i, s in enumerate(self.data)]

    def ltp(self, keys):
        return {k: {"last_price": float(self.data[k.split(":")[1]]["close"].iloc[-1])} for k in keys}

    def historical_data(self, token, start, end, interval):
        sym = list(self.data)[token]
        df = self.data[sym].iloc[:-1].reset_index()
        return df.to_dict("records")


def test_paper_day_and_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = synthetic(["AAA", "BBB"], years=2)
    monkeypatch.setattr(paper, "get_kite", lambda: FakeKite(data))
    cfg = Config(universe=["AAA", "BBB"], start_capital=20000, monthly_contribution=20000)

    paper.run_paper_day(cfg)
    assert paper.ACCOUNT_FILE.exists() and paper.RISK_FILE.exists()
    with pytest.raises(SystemExit):
        paper.run_paper_day(cfg)  # second run on the same day is refused
    paper.run_paper_day(cfg, force=True)

    text = review(paper.JOURNAL_FILE, 7, tmp_path / "none.json", tmp_path / "reports")
    assert "Review" in text and (tmp_path / "reports" / f"review-{date.today()}.md").exists()
