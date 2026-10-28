# Kite trading bot

A cash-only, paper-first trading bot for Zerodha Kite Connect. It is built around one rule:
**you can never lose more than the money you put in.**

The full plan, including realistic return ranges, regulation, strategies and tax, is in the
"Kite trading bot: realistic plan" doc.

## What it does

| Part | File | Notes |
| --- | --- | --- |
| Login | `kitebot/auth.py` | Kite tokens expire daily, so you log in each morning |
| Data | `kitebot/data.py` | Kite candles; free NSE data from [eod2_data](https://github.com/BennyThadikaran/eod2_data) or Yahoo; split fixes; synthetic data for offline tests |
| Strategies | `kitebot/strategies.py` | `trend` (55-day breakout + 200-day filter) and `meanrev` (RSI(2) dips in an uptrend) |
| Risk | `kitebot/risk.py` | Hard limits checked before every order (below) |
| Engine | `kitebot/engine.py` | One trading day; shared by backtest and paper so both follow the same rules |
| Backtest | `kitebot/backtest.py` | Signals at close, fills next open, Zerodha charges and slippage, monthly deposits |
| Paper | `kitebot/paper.py` | Daily run on live Kite prices; no real orders |
| Journal + review | `kitebot/journal.py`, `kitebot/review.py` | Every signal, fill, reject and alert logged; weekly/monthly review notes |

## The loss cap, in code

- Only **NSE delivery (CNC)** orders of **whitelisted** symbols. Futures, options, intraday (MIS) and margin are refused.
- Buys must be **fully paid from cash**. Sells can't exceed shares held, so **no short selling**.
- `max_gross_exposure_pct` above 100 (leverage) is refused when the config loads.
- 1% of equity risked per trade, 20% max per position, 2% daily loss limit, 20 orders a day.
- **Kill switch** at 15% drawdown from peak NAV: no new buys until you review and run `reset-kill-switch`. Exits still work.
- **No live trading.** `LiveBroker` refuses every order. Add live order placement yourself only after passing the gates in the plan.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml          # edit the universe and limits
export KITE_API_KEY=...  KITE_API_SECRET=...  # from developers.kite.trade
```

Kite Connect costs about Rs 500 a month for historical and live data. That is about 2.5% of a
Rs 20k monthly deposit, so it is a real cost on a small account. SEBI's 2025 retail algo rules
also require API orders to come from a static IP registered with Zerodha (a small cloud VM works).

## Commands

```bash
python -m kitebot backtest --source synthetic        # test the plumbing offline (numbers are meaningless)
python -m kitebot backtest --source eod2 --start 2026-05-01   # free NSE data, no Kite login needed
python -m kitebot backtest --source eod2 --start 2016-01-01 --end 2021-12-31 --cash-yield 6  # idle cash in a liquid ETF
python -m kitebot login                              # each morning
python -m kitebot fetch --years 12                   # download history
python -m kitebot backtest --strategy trend --end 2019-12-31    # in-sample: tune here only
python -m kitebot backtest --strategy trend --start 2020-01-01  # out-of-sample: test once, don't tune
python -m kitebot paper                              # once a day after 9:20 IST
python -m kitebot review --days 7                    # weekly; --days 30 monthly
python -m kitebot reset-kill-switch                  # only after a written review
python -m pytest                                     # run the tests
```

Reports go to `reports/`, paper state and the journal to `state/`.

## The learning loop

1. The journal records every signal, fill, reject and alert with the rule version (`RULES_VERSION`).
2. Weekly: `review --days 7`. Fix operational problems only (missed runs, bad fills, data gaps).
3. Monthly: `review --days 30`. Write each lesson as one testable rule change in the review note.
4. Test it: in-sample backtest, then one out-of-sample run, then 4 weeks on paper beside the current rules.
5. Promote only if it wins out of sample and on paper. Bump `RULES_VERSION`. One change a month at most,
   and none in a week with a loss over 1% of the account.

## Default universe

NIFTYBEES, BANKBEES, JUNIORBEES, GOLDBEES, ITBEES (liquid NSE ETFs). For `meanrev`, use liquid large caps
(for example Nifty 50 stocks) instead; check symbols on Kite before adding them.
