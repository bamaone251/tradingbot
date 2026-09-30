from app import indicators as ind
from app.strategies.base import ParamField, SignalResult, Strategy


class MacdSignalCross(Strategy):
    key = "macd_signal_cross"
    label = "MACD Signal Cross"
    description = "Long when the MACD line is above its signal line."
    param_fields = [
        ParamField("fast", "Fast EMA", "int", 12),
        ParamField("signal", "Signal EMA", "int", 9),
        ParamField("slow", "Slow EMA", "int", 26),
    ]

    @classmethod
    def min_bars_required(cls, params) -> int:
        return int(params["slow"]) + int(params["signal"]) + 10

    @classmethod
    def evaluate(cls, df, params: dict, in_position: bool) -> SignalResult:
        fast_w, slow_w, signal_w = int(params["fast"]), int(params["slow"]), int(params["signal"])
        macd_line, signal_line, hist = ind.macd(df["close"], fast_w, slow_w, signal_w)

        price = float(df["close"].iloc[-1])
        macd_last, signal_last = float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
        info = {"macd": macd_last, "signal": signal_last, "hist": macd_last - signal_last}

        if macd_last != macd_last or signal_last != signal_last:
            return SignalResult("hold", price, info, "not enough history yet")

        bullish = macd_last > signal_last

        if not in_position and bullish:
            return SignalResult("buy", price, info, f"MACD {macd_last:.3f} > signal {signal_last:.3f}")
        if in_position and not bullish:
            return SignalResult("sell", price, info, f"MACD {macd_last:.3f} <= signal {signal_last:.3f}")
        return SignalResult("hold", price, info)
