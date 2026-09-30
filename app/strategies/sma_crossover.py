from app import indicators as ind
from app.strategies.base import ParamField, SignalResult, Strategy


class SmaCrossover(Strategy):
    key = "sma_crossover"
    label = "SMA Crossover"
    description = "Long when the fast SMA is above the slow SMA."
    param_fields = [
        ParamField("fast", "Fast SMA window", "int", 20),
        ParamField("slow", "Slow SMA window", "int", 50),
    ]

    @classmethod
    def min_bars_required(cls, params) -> int:
        return int(params["slow"]) + 5

    @classmethod
    def evaluate(cls, df, params: dict, in_position: bool) -> SignalResult:
        fast_w, slow_w = int(params["fast"]), int(params["slow"])
        fast = ind.sma(df["close"], fast_w)
        slow = ind.sma(df["close"], slow_w)

        price = float(df["close"].iloc[-1])
        fast_last, slow_last = float(fast.iloc[-1]), float(slow.iloc[-1])
        info = {"fast_sma": fast_last, "slow_sma": slow_last}

        if fast_last != fast_last or slow_last != slow_last:  # NaN check
            return SignalResult("hold", price, info, "not enough history yet")

        bullish = fast_last > slow_last

        if not in_position and bullish:
            return SignalResult("buy", price, info, f"fast SMA {fast_last:.2f} > slow SMA {slow_last:.2f}")
        if in_position and not bullish:
            return SignalResult("sell", price, info, f"fast SMA {fast_last:.2f} <= slow SMA {slow_last:.2f}")
        return SignalResult("hold", price, info)
