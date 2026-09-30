"""
Thin wrapper around the alpaca-py SDK. Everything the rest of the app needs
from Alpaca (market data + trading) goes through here, so it's the one place
that has to change if Alpaca's API ever does.

API verified against alpaca-py docs (alpaca.markets/sdks/python) - trading
client, market data client, bracket-order fields (MarketOrderRequest.stop_loss
+ order_class=OrderClass.BRACKET), and order/position/account field names.
"""
import logging

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopLossRequest

from app.config import Config

log = logging.getLogger("broker")

_trading_client = None
_data_client = None


class BrokerError(Exception):
    pass


def trading_client():
    global _trading_client
    if _trading_client is None:
        if not Config.credentials_configured():
            raise BrokerError(
                "Alpaca API credentials are not configured. Fill in ALPACA_API_KEY_ID "
                "and ALPACA_API_SECRET_KEY in your .env file."
            )
        _trading_client = TradingClient(
            Config.ALPACA_API_KEY_ID,
            Config.ALPACA_API_SECRET_KEY,
            paper=Config.ALPACA_PAPER,
        )
    return _trading_client


def data_client():
    global _data_client
    if _data_client is None:
        if not Config.credentials_configured():
            raise BrokerError(
                "Alpaca API credentials are not configured. Fill in ALPACA_API_KEY_ID "
                "and ALPACA_API_SECRET_KEY in your .env file."
            )
        _data_client = StockHistoricalDataClient(
            Config.ALPACA_API_KEY_ID, Config.ALPACA_API_SECRET_KEY
        )
    return _data_client


def fetch_daily_bars(symbol: str, lookback_days: int = 400) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by date with columns:
    open, high, low, close, volume - sorted oldest -> newest.

    lookback_days is calendar days, not trading days, so 400 gives comfortably
    more than 252 trading bars (a year) for slow-window indicators like a
    50-day SMA.
    """
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    bar_set = data_client().get_stock_bars(request)
    df = bar_set.df
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # df is MultiIndex (symbol, timestamp) even for a single symbol request
    if symbol in df.index.get_level_values(0):
        df = df.xs(symbol, level=0)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    df = df.sort_index()
    return df


def get_account():
    acct = trading_client().get_account()
    return {
        "equity": float(acct.equity),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "status": str(acct.status),
    }


def get_position(symbol: str):
    """Returns dict or None if no open Alpaca position in this symbol."""
    try:
        pos = trading_client().get_open_position(symbol)
    except Exception:
        return None
    return {
        "symbol": pos.symbol,
        "qty": float(pos.qty),
        "avg_entry_price": float(pos.avg_entry_price),
        "market_value": float(pos.market_value) if pos.market_value is not None else None,
        "unrealized_pl": float(pos.unrealized_pl) if pos.unrealized_pl is not None else None,
    }


def get_all_positions():
    positions = trading_client().get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "market_value": float(p.market_value) if p.market_value is not None else None,
            "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl is not None else None,
        }
        for p in positions
    ]


def submit_bracket_buy(symbol: str, qty: int, stop_price: float):
    """
    Market buy with an attached protective stop-loss (a 2-leg bracket: entry +
    stop). Submitted as a DAY order - if placed after market close (which is
    when the daily job runs) Alpaca queues it to execute at the next session's
    open.

    Returns (entry_order_id, stop_order_id-or-None). The stop leg's id isn't
    assigned until the entry fills, so stop_order_id is fetched by the caller
    later via get_order once the leg is confirmed open.
    """
    order_req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        stop_loss=StopLossRequest(stop_price=round(stop_price, 2)),
    )
    order = trading_client().submit_order(order_data=order_req)
    return str(order.id)


def submit_market_sell(symbol: str, qty: float):
    order_req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    order = trading_client().submit_order(order_data=order_req)
    return str(order.id)


def get_order(order_id: str):
    order = trading_client().get_order_by_id(order_id)
    return _order_to_dict(order)


def get_open_orders():
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)
    orders = trading_client().get_orders(filter=req)
    return [_order_to_dict(o) for o in orders]


def cancel_order(order_id: str):
    trading_client().cancel_order_by_id(order_id)


def _order_to_dict(order):
    legs = []
    if getattr(order, "legs", None):
        legs = [_order_to_dict(leg) for leg in order.legs]
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": str(order.side),
        "qty": float(order.qty) if order.qty is not None else None,
        "filled_qty": float(order.filled_qty) if order.filled_qty is not None else None,
        "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price is not None else None,
        "status": str(order.status),
        "order_class": str(order.order_class),
        "legs": legs,
    }
