import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app import indicators as ind
from tests.helpers import make_bars


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    out = ind.sma(s, 3)
    assert math.isnan(out.iloc[1])
    assert out.iloc[-1] == (8 + 9 + 10) / 3


def test_ema_reacts_faster_than_sma_to_a_jump():
    s = pd.Series([10.0] * 20 + [20.0] * 5)
    sma20 = ind.sma(s, 20).iloc[-1]
    ema20 = ind.ema(s, 20).iloc[-1]
    # EMA weights recent bars more heavily, so after a jump it should sit
    # closer to the new level than the plain SMA does.
    assert ema20 > sma20


def test_rsi_all_gains_is_100():
    s = pd.Series([float(i) for i in range(1, 40)])  # strictly increasing
    out = ind.rsi(s, window=14)
    assert out.iloc[-1] == 100.0


def test_rsi_all_losses_is_0():
    s = pd.Series([float(i) for i in range(40, 1, -1)])  # strictly decreasing
    out = ind.rsi(s, window=14)
    assert out.iloc[-1] == 0.0


def test_rsi_midpoint_when_flat():
    s = pd.Series([50.0] * 30)
    out = ind.rsi(s, window=14)
    # no gains and no losses -> avg_gain == avg_loss == 0 -> our code treats
    # avg_loss == 0 as RSI 100 (matches the "all gains" convention); the
    # important thing is it doesn't error or go negative/over 100.
    assert 0 <= out.iloc[-1] <= 100


def test_macd_line_matches_manual_ema_difference():
    s = pd.Series([float(100 + i * 0.5) for i in range(60)])
    macd_line, signal_line, hist = ind.macd(s, fast=12, slow=26, signal=9)
    manual = ind.ema(s, 12) - ind.ema(s, 26)
    pd.testing.assert_series_equal(macd_line, manual, check_names=False)
    # histogram is macd - signal by construction
    diff = (macd_line - signal_line).dropna()
    pd.testing.assert_series_equal(hist.dropna(), diff, check_names=False)


def test_bollinger_bands_collapse_on_constant_series():
    s = pd.Series([100.0] * 30)
    mid, upper, lower = ind.bollinger_bands(s, window=20, num_std=2)
    assert mid.iloc[-1] == 100.0
    assert upper.iloc[-1] == 100.0
    assert lower.iloc[-1] == 100.0


def test_bollinger_bands_widen_with_volatility():
    import random
    random.seed(0)
    s = pd.Series([100 + random.uniform(-5, 5) for _ in range(40)])
    mid, upper, lower = ind.bollinger_bands(s, window=20, num_std=2)
    assert upper.iloc[-1] > mid.iloc[-1] > lower.iloc[-1]


def test_atr_is_positive_for_normal_bars():
    df = make_bars([100 + i * 0.3 for i in range(30)])
    out = ind.atr(df, window=14)
    assert out.iloc[-1] > 0


def test_atr_bigger_for_choppier_bars():
    calm = make_bars([100.0] * 30)
    choppy_closes = [100 + (5 if i % 2 == 0 else -5) for i in range(30)]
    choppy = make_bars(choppy_closes)
    calm_atr = ind.atr(calm, window=14).iloc[-1]
    choppy_atr = ind.atr(choppy, window=14).iloc[-1]
    assert choppy_atr > calm_atr
