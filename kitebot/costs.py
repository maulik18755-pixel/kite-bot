"""Zerodha equity delivery charges (approximate, check zerodha.com/charges before relying on them)."""

STT_PCT = 0.1               # on buy and sell value
EXCHANGE_TXN_PCT = 0.00297  # NSE
SEBI_FEE_PCT = 0.0001       # Rs 10 per crore
STAMP_DUTY_BUY_PCT = 0.015  # buy side only
GST_PCT = 18.0              # on brokerage + exchange + SEBI fees
DP_CHARGE_PER_SELL = 15.93  # per scrip per day sold, incl. GST
BROKERAGE = 0.0             # delivery is brokerage-free at Zerodha


def delivery_charges(side: str, value: float) -> float:
    """Total statutory and broker charges in rupees for one delivery order."""
    stt = value * STT_PCT / 100
    exch = value * EXCHANGE_TXN_PCT / 100
    sebi = value * SEBI_FEE_PCT / 100
    gst = (BROKERAGE + exch + sebi) * GST_PCT / 100
    total = BROKERAGE + stt + exch + sebi + gst
    if side == "BUY":
        total += value * STAMP_DUTY_BUY_PCT / 100
    else:
        total += DP_CHARGE_PER_SELL
    return round(total, 2)


def apply_slippage(side: str, price: float, slippage_pct: float) -> float:
    """Worse fill price: pay more when buying, get less when selling."""
    adj = price * slippage_pct / 100
    return price + adj if side == "BUY" else price - adj
