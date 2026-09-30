from app import indicators as ind
from app.strategies.base import ParamField, SignalResult, Strategy


class RsiMeanReversion(Strategy):
    key = "rsi_mean_reversion"
    label = "RSI Mean Reversion"
    description = "Buy when RSI drops below the oversold level, exit above overbought."
    param_fields = [
        ParamField("window", "RSI window", "int", 14),
        ParamField("oversold", "Oversold level", "float", 30),
        ParamField("overbought", "Overbought level", "float", 70),
    ]

    @classmethod
    def min_bars_required(cls, params) -> int:
        return int(params["window"]) + 10

    @classmethod
    def evaluate(cls, df, params: dict, in_position: bool) -> SignalResult:
        window = int(params["window"])
        oversold = float(params["oversold"])
        overbought = float(params["overbought"])
        rsi = ind.rsi(df["close"], window)

        price = float(df["close"].iloc[-1])
        rsi_last = float(rsi.iloc[-1])
        info = {"rsi": rsi_last}

        if rsi_last != rsi_last:
            return SignalResult("hold", price, info, "not enough history yet")

        if not in_position and rsi_last < oversold:
            return SignalResult("buy", price, info, f"RSI {rsi_last:.1f} < oversold {oversold}")
        if in_position and rsi_last > overbought:
            return SignalResult("sell", price, info, f"RSI {rsi_last:.1f} > overbought {overbought}")
        return SignalResult("hold", price, info)
