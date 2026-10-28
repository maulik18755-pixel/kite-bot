# Backtest review, 28 Oct 2026

Data: eod2_data (NSE bhavcopies) to 23 Oct 2026. Rs 20k start plus Rs 20k a month, Zerodha delivery charges and 0.05% slippage each side, before income tax.

## May to Oct 2026 (Rs 1.2 lakh deposited)

| Version | P&L | Trades |
| --- | --- | --- |
| Trend, large caps, idle cash at 6% | -Rs 529 | 4 |
| Mean reversion, ETFs | -Rs 839 | 13 |
| Mean reversion, large caps | -Rs 1,086 | 12 |
| Trend, ETFs | -Rs 1,509 | 3 |
| Trend, large caps | -Rs 2,156 | 4 |
| NIFTYBEES SIP, no bot | -Rs 6,349 | 6 buys |

## 10 years (return a year, per NAV unit)

| Version | 2016-21 | 2022-26 |
| --- | --- | --- |
| Trend, large caps, idle cash at 6% | 8.1% | 4.4% |
| Trend, large caps | 4.6% | 1.1% |
| Trend, ETFs | 0.8% | 1.9% |
| Mean reversion, large caps | 0.7% | -3.2% (kill switch) |
| Mean reversion, ETFs | -1.0% | -3.4% (kill switch) |
| Hold the large caps, no costs | 19.2% | 7.5% |

## Next changes to test (learning loop)

1. Park idle cash in LIQUIDBEES (tested: +3 to 3.5 points a year).
2. Core and satellite: most of each deposit into a Nifty ETF SIP, bot trades the rest.
3. Retire mean reversion as it stands.
4. Monthly Nifty 100 momentum instead of breakouts.
5. Small-account rules: Rs 5k minimum trade, 4 positions max, skip trades where charges exceed 0.5%.
6. Halve size on gap-prone ETFs such as GOLDBEES.
