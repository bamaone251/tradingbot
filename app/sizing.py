"""
Position sizing: risk a fixed % of account equity per trade, sized off an
ATR-based stop distance - the "Fixed risk % (ATR stop)" method from your
backtest configs.

Assumption (flagged in the README): risk % is computed against the account's
*total* equity for every entry, not a sub-allocation per strategy. Since each
strategy/symbol pairing trades its own independent slice, running many
entries at once will stack risk - lower each entry's risk % if you want to
run a lot of them concurrently.
"""
import math
from dataclasses import dataclass


@dataclass
class SizingResult:
    qty: int
    stop_price: float
    risk_amount: float
    reason: str = ""


def size_position(equity: float, buying_power: float, entry_price: float,
                   atr_value: float, atr_stop_mult: float, risk_pct: float) -> SizingResult:
    """
    stop_price = entry_price - atr_value * atr_stop_mult
    risk_amount = equity * risk_pct / 100
    qty = floor(risk_amount / (entry_price - stop_price))
    capped so qty * entry_price does not exceed buying_power.
    """
    if entry_price <= 0 or atr_value <= 0 or atr_stop_mult <= 0:
        return SizingResult(0, 0.0, 0.0, "invalid price/ATR input")

    stop_price = entry_price - (atr_value * atr_stop_mult)
    if stop_price <= 0:
        return SizingResult(0, 0.0, 0.0, "computed stop price is <= 0")

    stop_distance = entry_price - stop_price
    risk_amount = equity * (risk_pct / 100.0)
    risk_based_qty = math.floor(risk_amount / stop_distance)

    affordable_qty = math.floor(buying_power / entry_price)
    qty = max(0, min(risk_based_qty, affordable_qty))

    reason = ""
    if qty == 0:
        if risk_based_qty == 0:
            reason = "risk amount too small to buy even 1 share at this stop distance"
        elif affordable_qty == 0:
            reason = "insufficient buying power for even 1 share"

    return SizingResult(qty=qty, stop_price=round(stop_price, 2), risk_amount=risk_amount, reason=reason)
