from app import indicators as ind
from app.strategies.base import ParamField, SignalResult, Strategy


class BollingerBandBounce(Strategy):
    key = "bollinger_band_bounce"
    label = "Bollinger Band Bounce"
    description = "Buy when price closes below the lower band, exit at the mid band."
    param_fields = [
        ParamField("window", "Window", "int", 20),
        ParamField("num_std", "Num. std deviations", "float", 2.0),
    ]

    @classmethod
    def min_bars_required(cls, params) -> int:
        return int(params["window"]) + 5

    @classmethod
    def evaluate(cls, df, params: dict, in_position: bool) -> SignalResult:
        window = int(params["window"])
        num_std = float(params["num_std"])
        mid, upper, lower = ind.bollinger_bands(df["close"], window, num_std)

        price = float(df["close"].iloc[-1])
        mid_last, lower_last = float(mid.iloc[-1]), float(lower.iloc[-1])
        info = {"mid_band": mid_last, "lower_band": lower_last, "upper_band": float(upper.iloc[-1])}

        if mid_last != mid_last or lower_last != lower_last:
            return SignalResult("hold", price, info, "not enough history yet")

        if not in_position and price < lower_last:
            return SignalResult("buy", price, info, f"close {price:.2f} < lower band {lower_last:.2f}")
        if in_position and price >= mid_last:
            return SignalResult("sell", price, info, f"close {price:.2f} >= mid band {mid_last:.2f}")
        return SignalResult("hold", price, info)
