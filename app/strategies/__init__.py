from app.strategies.bollinger_band_bounce import BollingerBandBounce
from app.strategies.macd_signal_cross import MacdSignalCross
from app.strategies.rsi_mean_reversion import RsiMeanReversion
from app.strategies.sma_crossover import SmaCrossover

REGISTRY = {
    SmaCrossover.key: SmaCrossover,
    MacdSignalCross.key: MacdSignalCross,
    BollingerBandBounce.key: BollingerBandBounce,
    RsiMeanReversion.key: RsiMeanReversion,
}


def get_strategy(key):
    if key not in REGISTRY:
        raise KeyError(f"Unknown strategy '{key}'")
    return REGISTRY[key]


def all_strategies():
    return list(REGISTRY.values())
