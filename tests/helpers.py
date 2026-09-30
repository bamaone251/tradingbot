import pandas as pd


def make_bars(closes, start="2024-01-01"):
    """Build a minimal OHLCV DataFrame from a list of closes for testing."""
    idx = pd.bdate_range(start=start, periods=len(closes))
    df = pd.DataFrame(index=idx)
    df.index.name = "date"
    df["close"] = closes
    df["open"] = df["close"]
    df["high"] = df["close"] * 1.001
    df["low"] = df["close"] * 0.999
    df["volume"] = 1_000_000
    return df
