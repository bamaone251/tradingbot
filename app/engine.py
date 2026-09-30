"""
The daily job: for every enabled watchlist entry, fetch fresh bars, reconcile
any broker-side stop fill since the last run, evaluate that entry's strategy,
and act (buy / sell / hold). This is what both the scheduler and the
dashboard's "Run Now" button call.
"""
import logging
from datetime import datetime, timezone

from app import broker, db
from app import indicators as ind
from app import sizing
from app.config import Config
from app.strategies import get_strategy

log = logging.getLogger("engine")


def _safe_get_order(order_id):
    if not order_id:
        return None
    try:
        return broker.get_order(order_id)
    except Exception as e:
        log.warning("could not fetch order %s: %s", order_id, e)
        return None


def run_daily_job():
    """Returns a summary dict; also writes everything to the DB as it goes."""
    started_at = datetime.now(timezone.utc).isoformat()
    summary = {"started_at": started_at, "entries": [], "trading_enabled": db.is_trading_enabled()}

    if not Config.credentials_configured():
        summary["error"] = "Alpaca API credentials are not configured."
        return summary

    try:
        account = broker.get_account()
        db.record_account_snapshot(account["equity"], account["cash"], account["buying_power"])
        summary["account"] = account
    except Exception as e:
        summary["error"] = f"Could not reach Alpaca: {e}"
        return summary

    if not db.is_trading_enabled():
        summary["note"] = "Trading is paused (kill switch is off) - signals are not being evaluated."
        return summary

    entries = db.list_watchlist_entries(enabled_only=True)
    for entry in entries:
        try:
            result = process_entry(entry, account)
        except Exception as e:
            log.exception("error processing entry %s", entry["id"])
            db.log_signal(entry["id"], entry["symbol"], entry["strategy_key"],
                           "hold", None, {}, "error", str(e))
            result = {"symbol": entry["symbol"], "strategy": entry["strategy_key"], "error": str(e)}
        summary["entries"].append(result)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def process_entry(entry, account):
    entry_id = entry["id"]
    symbol = entry["symbol"]
    strategy_key = entry["strategy_key"]
    params = entry["params"]
    strategy_cls = get_strategy(strategy_key)

    min_bars = strategy_cls.min_bars_required(params)
    lookback_days = max(400, int(min_bars * 2.2))
    df = broker.fetch_daily_bars(symbol, lookback_days=lookback_days)

    if len(df) < min_bars:
        db.log_signal(entry_id, symbol, strategy_key, "hold", None, {},
                       "skipped_insufficient_data",
                       f"have {len(df)} bars, need {min_bars}")
        return {"symbol": symbol, "strategy": strategy_key, "action": "skipped_insufficient_data"}

    bar_date = df.index[-1].strftime("%Y-%m-%d")
    open_leg = db.get_open_leg(entry_id)
    in_position = open_leg is not None

    # --- Reconcile: did the protective stop already fill since last run? ---
    if in_position and open_leg.get("stop_order_id"):
        stop_info = _safe_get_order(open_leg["stop_order_id"])
        if stop_info and stop_info["status"] == "filled":
            exit_price = stop_info["filled_avg_price"] or open_leg["stop_price"]
            db.close_leg(open_leg["id"], exit_price, bar_date, "stop_hit")
            db.log_signal(entry_id, symbol, strategy_key, "sell", exit_price, {},
                           "stop_filled", "protective stop was hit; position closed")
            in_position = False
            open_leg = None

    result = strategy_cls.evaluate(df, params, in_position)

    if result.signal == "hold":
        db.log_signal(entry_id, symbol, strategy_key, "hold", result.price,
                       result.indicators, "noop", result.reason)
        return {"symbol": symbol, "strategy": strategy_key, "action": "hold", "price": result.price}

    if result.signal == "buy":
        return _handle_buy(entry, account, df, result, bar_date)

    if result.signal == "sell":
        return _handle_sell(entry, open_leg, result, bar_date)

    return {"symbol": symbol, "strategy": strategy_key, "action": "unknown_signal"}


def _handle_buy(entry, account, df, result, bar_date):
    entry_id, symbol, strategy_key = entry["id"], entry["symbol"], entry["strategy_key"]

    atr_window = entry.get("atr_window") or db.get_default_atr_window()
    atr_mult = entry.get("atr_stop_mult") or db.get_default_atr_stop_mult()
    atr_series = ind.atr(df, int(atr_window))
    atr_val = float(atr_series.iloc[-1])

    if atr_val != atr_val or atr_val <= 0:  # NaN or invalid
        db.log_signal(entry_id, symbol, strategy_key, "buy", result.price, result.indicators,
                       "skipped_no_atr", "ATR not available yet")
        return {"symbol": symbol, "strategy": strategy_key, "action": "skipped_no_atr"}

    sz = sizing.size_position(
        equity=account["equity"],
        buying_power=account["buying_power"],
        entry_price=result.price,
        atr_value=atr_val,
        atr_stop_mult=float(atr_mult),
        risk_pct=float(entry["risk_pct"]),
    )

    if sz.qty < 1:
        db.log_signal(entry_id, symbol, strategy_key, "buy", result.price, result.indicators,
                       "skipped_no_size", sz.reason)
        return {"symbol": symbol, "strategy": strategy_key, "action": "skipped_no_size", "reason": sz.reason}

    order_id = broker.submit_bracket_buy(symbol, sz.qty, sz.stop_price)

    stop_order_id = None
    order_info = _safe_get_order(order_id)
    if order_info and order_info.get("legs"):
        stop_order_id = order_info["legs"][0]["id"]

    db.open_leg(
        entry_id=entry_id, symbol=symbol, strategy_key=strategy_key,
        qty=sz.qty, entry_price=result.price, entry_date=bar_date,
        stop_price=sz.stop_price, atr_at_entry=atr_val,
        entry_order_id=order_id, stop_order_id=stop_order_id,
    )
    db.log_signal(entry_id, symbol, strategy_key, "buy", result.price, result.indicators,
                   "order_placed", f"bought {sz.qty} sh, stop {sz.stop_price} ({result.reason})")
    return {"symbol": symbol, "strategy": strategy_key, "action": "bought",
            "qty": sz.qty, "price": result.price, "stop": sz.stop_price}


def _handle_sell(entry, open_leg, result, bar_date):
    entry_id, symbol, strategy_key = entry["id"], entry["symbol"], entry["strategy_key"]

    if open_leg is None:
        db.log_signal(entry_id, symbol, strategy_key, "sell", result.price, result.indicators,
                       "skipped_flat", "sell signal but no open leg for this entry")
        return {"symbol": symbol, "strategy": strategy_key, "action": "skipped_flat"}

    if open_leg.get("stop_order_id"):
        try:
            broker.cancel_order(open_leg["stop_order_id"])
        except Exception as e:
            log.warning("could not cancel stop order %s: %s", open_leg["stop_order_id"], e)

    broker.submit_market_sell(symbol, open_leg["qty"])
    db.close_leg(open_leg["id"], result.price, bar_date, "strategy_exit")
    db.log_signal(entry_id, symbol, strategy_key, "sell", result.price, result.indicators,
                   "order_placed", f"sold {open_leg['qty']} sh ({result.reason})")
    return {"symbol": symbol, "strategy": strategy_key, "action": "sold",
            "qty": open_leg["qty"], "price": result.price}
