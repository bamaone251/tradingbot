import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategies.bollinger_band_bounce import BollingerBandBounce
from app.strategies.macd_signal_cross import MacdSignalCross
from app.strategies.rsi_mean_reversion import RsiMeanReversion
from app.strategies.sma_crossover import SmaCrossover
from tests.helpers import make_bars


def test_sma_crossover_min_bars():
    assert SmaCrossover.min_bars_required({"fast": 20, "slow": 50}) == 55


def test_sma_crossover_holds_with_insufficient_history():
    df = make_bars([100.0] * 10)
    r = SmaCrossover.evaluate(df, SmaCrossover.default_params(), in_position=False)
    assert r.signal == "hold"
    assert "history" in r.reason


def test_sma_crossover_buys_when_fast_climbs_above_slow_and_flat():
    closes = list(range(200, 120, -1)) + [x / 10 for x in range(1200, 2600, 30)]
    df = make_bars(closes)
    r = SmaCrossover.evaluate(df, SmaCrossover.default_params(), in_position=False)
    assert r.signal == "buy"
    assert r.indicators["fast_sma"] > r.indicators["slow_sma"]


def test_sma_crossover_sells_when_bearish_and_holding():
    closes = list(range(120, 260, 3)) + list(range(260, 150, -3))
    df = make_bars(closes)
    r = SmaCrossover.evaluate(df, SmaCrossover.default_params(), in_position=True)
    assert r.signal == "sell"
    assert r.indicators["fast_sma"] <= r.indicators["slow_sma"]


def test_macd_buys_on_sustained_uptrend_when_flat():
    closes = [100 + i * 1.2 for i in range(60)]
    df = make_bars(closes)
    r = MacdSignalCross.evaluate(df, MacdSignalCross.default_params(), in_position=False)
    assert r.signal == "buy"
    assert r.indicators["macd"] > r.indicators["signal"]


def test_macd_sells_on_sustained_downtrend_when_holding():
    closes = [100 + i * 1.2 for i in range(40)] + [148 - i * 1.5 for i in range(20)]
    df = make_bars(closes)
    r = MacdSignalCross.evaluate(df, MacdSignalCross.default_params(), in_position=True)
    assert r.signal == "sell"
    assert r.indicators["macd"] <= r.indicators["signal"]


def test_bollinger_buys_on_sharp_drop_below_lower_band():
    closes = [100.0] * 25 + [80.0]
    df = make_bars(closes)
    r = BollingerBandBounce.evaluate(df, BollingerBandBounce.default_params(), in_position=False)
    assert r.signal == "buy"
    assert r.price < r.indicators["lower_band"]


def test_bollinger_sells_at_mid_band_when_holding():
    closes = [100.0] * 25
    df = make_bars(closes)
    r = BollingerBandBounce.evaluate(df, BollingerBandBounce.default_params(), in_position=True)
    assert r.signal == "sell"
    assert r.price >= r.indicators["mid_band"]


def test_bollinger_holds_when_between_bands():
    import random
    random.seed(1)
    closes = [100 + random.uniform(-1, 1) for _ in range(25)]
    df = make_bars(closes)
    r = BollingerBandBounce.evaluate(df, BollingerBandBounce.default_params(), in_position=False)
    assert r.signal == "hold"


def test_rsi_buys_when_oversold_and_flat():
    closes = [float(i) for i in range(60, 10, -1)]  # strong decline
    df = make_bars(closes)
    r = RsiMeanReversion.evaluate(df, RsiMeanReversion.default_params(), in_position=False)
    assert r.signal == "buy"
    assert r.indicators["rsi"] < 30


def test_rsi_sells_when_overbought_and_holding():
    closes = [float(i) for i in range(10, 60)]  # strong rally
    df = make_bars(closes)
    r = RsiMeanReversion.evaluate(df, RsiMeanReversion.default_params(), in_position=True)
    assert r.signal == "sell"
    assert r.indicators["rsi"] > 70


def test_rsi_does_not_rebuy_while_already_in_position_and_still_oversold():
    closes = [float(i) for i in range(60, 10, -1)]
    df = make_bars(closes)
    r = RsiMeanReversion.evaluate(df, RsiMeanReversion.default_params(), in_position=True)
    # already holding - oversold alone shouldn't fire another buy
    assert r.signal != "buy"
