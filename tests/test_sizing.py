import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sizing import size_position


def test_basic_risk_based_sizing():
    # equity 100k, risk 5% -> risk $5000. entry 100, ATR 2, mult 2 -> stop 96,
    # stop distance 4 -> risk-based qty = 5000 / 4 = 1250.
    # buying power 100k / 100 = 1000 shares affordable -> capped at 1000.
    result = size_position(
        equity=100_000, buying_power=100_000, entry_price=100,
        atr_value=2, atr_stop_mult=2, risk_pct=5,
    )
    assert result.stop_price == 96.0
    assert result.qty == 1000  # capped by buying power, not risk
    assert result.risk_amount == 5000


def test_risk_based_qty_is_the_binding_constraint_when_buying_power_is_ample():
    result = size_position(
        equity=10_000, buying_power=1_000_000, entry_price=50,
        atr_value=1, atr_stop_mult=2, risk_pct=1,
    )
    # risk amount = 100, stop distance = 2 -> risk-based qty = 50
    assert result.qty == 50
    assert result.stop_price == 48.0


def test_zero_qty_when_buying_power_cannot_afford_one_share():
    result = size_position(
        equity=100_000, buying_power=10, entry_price=500,
        atr_value=5, atr_stop_mult=2, risk_pct=5,
    )
    assert result.qty == 0
    assert "buying power" in result.reason


def test_zero_qty_on_invalid_atr():
    result = size_position(
        equity=100_000, buying_power=100_000, entry_price=100,
        atr_value=0, atr_stop_mult=2, risk_pct=5,
    )
    assert result.qty == 0


def test_stop_price_scales_with_atr_multiplier():
    r1 = size_position(equity=100_000, buying_power=100_000, entry_price=100,
                        atr_value=3, atr_stop_mult=1, risk_pct=5)
    r2 = size_position(equity=100_000, buying_power=100_000, entry_price=100,
                        atr_value=3, atr_stop_mult=2, risk_pct=5)
    assert r1.stop_price == 97.0
    assert r2.stop_price == 94.0
    # wider stop -> fewer shares for the same risk budget
    assert r2.qty < r1.qty
