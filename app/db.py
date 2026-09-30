"""
Lightweight SQLite persistence layer. No ORM - just sqlite3 + small helper
functions, since the schema here is small and stable. Keeps the deployable
footprint tiny (no extra DB server to run on the VPS).
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    params_json TEXT NOT NULL,
    risk_pct REAL NOT NULL DEFAULT 5.0,
    atr_window INTEGER,
    atr_stop_mult REAL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES watchlist_entries(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL,
    stop_price REAL,
    atr_at_entry REAL,
    entry_order_id TEXT,
    stop_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    exit_price REAL,
    exit_date TEXT,
    exit_reason TEXT,                       -- 'strategy_exit' | 'stop_hit' | 'manual'
    realized_pl REAL
);

CREATE TABLE IF NOT EXISTS signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES watchlist_entries(id) ON DELETE SET NULL,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    signal TEXT NOT NULL,          -- 'buy' | 'sell' | 'hold'
    price REAL,
    indicators_json TEXT,
    action_taken TEXT,             -- 'order_placed' | 'skipped_flat' | 'skipped_open' | 'error' | 'noop'
    notes TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    equity REAL,
    cash REAL,
    buying_power REAL
);
"""

DEFAULT_SETTINGS = {
    "trading_enabled": "true",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- settings ----------

def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def is_trading_enabled():
    return get_setting("trading_enabled", "true") == "true"


def get_default_atr_window():
    from app.config import Config
    val = get_setting("default_atr_window")
    return int(val) if val else Config.DEFAULT_ATR_WINDOW


def get_default_atr_stop_mult():
    from app.config import Config
    val = get_setting("default_atr_stop_mult")
    return float(val) if val else Config.DEFAULT_ATR_STOP_MULT


# ---------- watchlist entries ----------

def list_watchlist_entries(enabled_only=False):
    with get_conn() as conn:
        q = "SELECT * FROM watchlist_entries"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY symbol, strategy_key"
        rows = conn.execute(q).fetchall()
        return [_entry_to_dict(r) for r in rows]


def get_watchlist_entry(entry_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM watchlist_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _entry_to_dict(row) if row else None


def create_watchlist_entry(symbol, strategy_key, params, risk_pct,
                            atr_window=None, atr_stop_mult=None, enabled=True):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO watchlist_entries "
            "(symbol, strategy_key, params_json, risk_pct, atr_window, atr_stop_mult, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol.upper(), strategy_key, json.dumps(params), risk_pct,
             atr_window, atr_stop_mult, 1 if enabled else 0, now_iso()),
        )
        return cur.lastrowid


def update_watchlist_entry(entry_id, **fields):
    if not fields:
        return
    if "params" in fields:
        fields["params_json"] = json.dumps(fields.pop("params"))
    if "enabled" in fields:
        fields["enabled"] = 1 if fields["enabled"] else 0
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [entry_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE watchlist_entries SET {cols} WHERE id = ?", vals)


def delete_watchlist_entry(entry_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist_entries WHERE id = ?", (entry_id,))


def _entry_to_dict(row):
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json"))
    d["enabled"] = bool(d["enabled"])
    return d


# ---------- legs ----------

def get_open_leg(entry_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM legs WHERE entry_id = ? AND status = 'open' "
            "ORDER BY id DESC LIMIT 1",
            (entry_id,),
        ).fetchone()
        return dict(row) if row else None


def list_open_legs():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT legs.*, watchlist_entries.risk_pct as entry_risk_pct "
            "FROM legs JOIN watchlist_entries ON legs.entry_id = watchlist_entries.id "
            "WHERE legs.status = 'open' ORDER BY legs.entry_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def list_closed_legs(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM legs WHERE status = 'closed' "
            "ORDER BY exit_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def open_leg(entry_id, symbol, strategy_key, qty, entry_price, entry_date,
             stop_price=None, atr_at_entry=None, entry_order_id=None, stop_order_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO legs (entry_id, symbol, strategy_key, qty, entry_price, entry_date, "
            "stop_price, atr_at_entry, entry_order_id, stop_order_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
            (entry_id, symbol, strategy_key, qty, entry_price, entry_date,
             stop_price, atr_at_entry, entry_order_id, stop_order_id),
        )
        return cur.lastrowid


def close_leg(leg_id, exit_price, exit_date, exit_reason):
    with get_conn() as conn:
        leg = conn.execute("SELECT * FROM legs WHERE id = ?", (leg_id,)).fetchone()
        if not leg:
            return
        realized_pl = (exit_price - leg["entry_price"]) * leg["qty"]
        conn.execute(
            "UPDATE legs SET status = 'closed', exit_price = ?, exit_date = ?, "
            "exit_reason = ?, realized_pl = ? WHERE id = ?",
            (exit_price, exit_date, exit_reason, realized_pl, leg_id),
        )


# ---------- signal log ----------

def log_signal(entry_id, symbol, strategy_key, signal, price, indicators,
                action_taken, notes=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO signal_log "
            "(entry_id, ts, symbol, strategy_key, signal, price, indicators_json, action_taken, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, now_iso(), symbol, strategy_key, signal, price,
             json.dumps(indicators or {}), action_taken, notes),
        )


def recent_signals(limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signal_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- account snapshots ----------

def record_account_snapshot(equity, cash, buying_power):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO account_snapshots (ts, equity, cash, buying_power) VALUES (?, ?, ?, ?)",
            (now_iso(), equity, cash, buying_power),
        )


def recent_account_snapshots(limit=90):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM account_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows][::-1]
