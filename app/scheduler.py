"""
APScheduler background job that runs the daily strategy check once per day,
shortly after market close. Runs inside the same process as the Flask app
(started once, guarded against the reloader/gunicorn worker duplication).
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Config

log = logging.getLogger("scheduler")
_scheduler = None


def _run_job():
    # imported lazily to avoid circular imports at module load time
    from app import engine
    log.info("daily job firing")
    summary = engine.run_daily_job()
    log.info("daily job finished: %s", summary)


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    hour, minute = Config.DAILY_JOB_TIME.split(":")
    trigger = CronTrigger(
        hour=int(hour), minute=int(minute),
        timezone=Config.DAILY_JOB_TIMEZONE,
        day_of_week="mon-fri",
    )
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_job, trigger, id="daily_strategy_job", replace_existing=True)
    _scheduler.start()
    log.info("scheduler started - daily job at %s %s, Mon-Fri", Config.DAILY_JOB_TIME, Config.DAILY_JOB_TIMEZONE)
    return _scheduler
