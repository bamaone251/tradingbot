"""
Central config, loaded from environment variables (.env in local/dev,
real environment variables in production / systemd).
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    ALPACA_API_KEY_ID = os.getenv("ALPACA_API_KEY_ID", "")
    ALPACA_API_SECRET_KEY = os.getenv("ALPACA_API_SECRET_KEY", "")
    ALPACA_PAPER = _get_bool("ALPACA_PAPER", True)

    DATABASE_PATH = os.getenv("DATABASE_PATH", "trading_bot.db")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    DAILY_JOB_TIME = os.getenv("DAILY_JOB_TIME", "16:15")
    DAILY_JOB_TIMEZONE = os.getenv("DAILY_JOB_TIMEZONE", "America/New_York")

    DEFAULT_ATR_WINDOW = int(os.getenv("DEFAULT_ATR_WINDOW", "14"))
    DEFAULT_ATR_STOP_MULT = float(os.getenv("DEFAULT_ATR_STOP_MULT", "2.0"))

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8420"))

    @classmethod
    def credentials_configured(cls):
        return bool(cls.ALPACA_API_KEY_ID) and bool(cls.ALPACA_API_SECRET_KEY) \
            and cls.ALPACA_API_KEY_ID != "your_key_id_here"
