"""
Flask dashboard: view account/positions/history, manage the watchlist
(symbol + strategy + params + risk %), flip the trading kill switch, and
trigger the daily job on demand ("Run Now").
"""
import logging

from flask import Flask, flash, redirect, render_template, request, url_for

from app import broker, db, engine
from app.config import Config
from app.scheduler import start_scheduler
from app.strategies import REGISTRY, get_strategy

log = logging.getLogger("web")


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.FLASK_SECRET_KEY

    db.init_db()
    start_scheduler()

    @app.context_processor
    def inject_globals():
        return {
            "paper_mode": Config.ALPACA_PAPER,
            "credentials_configured": Config.credentials_configured(),
            "trading_enabled": db.is_trading_enabled(),
        }

    @app.route("/")
    def home():
        account = None
        account_error = None
        if Config.credentials_configured():
            try:
                account = broker.get_account()
            except Exception as e:
                account_error = str(e)
        open_legs = db.list_open_legs()
        recent = db.recent_signals(limit=25)
        snapshots = db.recent_account_snapshots(limit=60)
        return render_template(
            "index.html", account=account, account_error=account_error,
            open_legs=open_legs, recent=recent, snapshots=snapshots,
        )

    @app.route("/run-now", methods=["POST"])
    def run_now():
        try:
            summary = engine.run_daily_job()
            if summary.get("error"):
                flash(f"Run failed: {summary['error']}", "error")
            else:
                n = len(summary.get("entries", []))
                acted = [e for e in summary.get("entries", []) if e.get("action") in ("bought", "sold")]
                flash(f"Run complete - checked {n} entries, {len(acted)} order(s) placed.", "success")
        except Exception as e:
            log.exception("manual run failed")
            flash(f"Run failed: {e}", "error")
        return redirect(url_for("home"))

    @app.route("/settings/toggle-trading", methods=["POST"])
    def toggle_trading():
        enabled = db.is_trading_enabled()
        db.set_setting("trading_enabled", "false" if enabled else "true")
        flash("Trading paused." if enabled else "Trading resumed.", "success")
        return redirect(request.referrer or url_for("home"))

    @app.route("/watchlist")
    def watchlist():
        entries = db.list_watchlist_entries()
        strategies = list(REGISTRY.values())
        return render_template("watchlist.html", entries=entries, strategies=strategies)

    @app.route("/watchlist/add", methods=["POST"])
    def watchlist_add():
        symbol = request.form.get("symbol", "").strip().upper()
        strategy_key = request.form.get("strategy_key", "")
        risk_pct = request.form.get("risk_pct", "5.0")

        if not symbol:
            flash("Symbol is required.", "error")
            return redirect(url_for("watchlist"))
        try:
            strategy_cls = get_strategy(strategy_key)
        except KeyError:
            flash("Unknown strategy.", "error")
            return redirect(url_for("watchlist"))

        params = {}
        for field in strategy_cls.param_fields:
            raw = request.form.get(f"param_{field.name}")
            if raw is None or raw == "":
                params[field.name] = field.default
            else:
                params[field.name] = int(raw) if field.type == "int" else float(raw)

        try:
            risk_pct = float(risk_pct)
        except ValueError:
            risk_pct = 5.0

        atr_window = request.form.get("atr_window") or None
        atr_stop_mult = request.form.get("atr_stop_mult") or None

        db.create_watchlist_entry(
            symbol=symbol, strategy_key=strategy_key, params=params, risk_pct=risk_pct,
            atr_window=int(atr_window) if atr_window else None,
            atr_stop_mult=float(atr_stop_mult) if atr_stop_mult else None,
        )
        flash(f"Added {symbol} / {strategy_cls.label}.", "success")
        return redirect(url_for("watchlist"))

    @app.route("/watchlist/<int:entry_id>/toggle", methods=["POST"])
    def watchlist_toggle(entry_id):
        entry = db.get_watchlist_entry(entry_id)
        if entry:
            db.update_watchlist_entry(entry_id, enabled=not entry["enabled"])
        return redirect(url_for("watchlist"))

    @app.route("/watchlist/<int:entry_id>/delete", methods=["POST"])
    def watchlist_delete(entry_id):
        open_leg = db.get_open_leg(entry_id)
        if open_leg:
            flash("Can't delete an entry with an open position - close it first.", "error")
            return redirect(url_for("watchlist"))
        db.delete_watchlist_entry(entry_id)
        flash("Entry deleted.", "success")
        return redirect(url_for("watchlist"))

    @app.route("/positions")
    def positions():
        open_legs = db.list_open_legs()
        broker_positions = []
        broker_error = None
        if Config.credentials_configured():
            try:
                broker_positions = broker.get_all_positions()
            except Exception as e:
                broker_error = str(e)
        return render_template(
            "positions.html", open_legs=open_legs,
            broker_positions=broker_positions, broker_error=broker_error,
        )

    @app.route("/history")
    def history():
        closed_legs = db.list_closed_legs(limit=300)
        signals = db.recent_signals(limit=300)
        total_realized = sum(l["realized_pl"] or 0 for l in closed_legs)
        return render_template(
            "history.html", closed_legs=closed_legs, signals=signals,
            total_realized=total_realized,
        )

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            db.set_setting("default_atr_window", request.form.get("default_atr_window", Config.DEFAULT_ATR_WINDOW))
            db.set_setting("default_atr_stop_mult", request.form.get("default_atr_stop_mult", Config.DEFAULT_ATR_STOP_MULT))
            flash("Settings saved.", "success")
            return redirect(url_for("settings"))
        return render_template(
            "settings.html",
            default_atr_window=db.get_default_atr_window(),
            default_atr_stop_mult=db.get_default_atr_stop_mult(),
            daily_job_time=Config.DAILY_JOB_TIME,
            daily_job_timezone=Config.DAILY_JOB_TIMEZONE,
            masked_key=(Config.ALPACA_API_KEY_ID[:4] + "..." + Config.ALPACA_API_KEY_ID[-4:])
            if len(Config.ALPACA_API_KEY_ID) > 8 else ("not set" if not Config.ALPACA_API_KEY_ID else "***"),
        )

    return app
