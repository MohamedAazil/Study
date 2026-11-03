"""Optional in-process scheduler (ENABLE_SCHEDULER=true). Prefer cron + scripts/run_eod_job.py in production."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.db.supabase import get_service_client
from app.notifications.base import get_notifier
from app.notifications.eod_job import run_end_of_day

logger = logging.getLogger(__name__)


def _job() -> None:
    result = run_end_of_day(get_service_client(), get_notifier())
    logger.info("EOD job finished: %s", result)


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.eod_timezone)
    scheduler.add_job(
        _job,
        CronTrigger(hour=settings.eod_cron_hour, minute=settings.eod_cron_minute, timezone=settings.eod_timezone),
        id="end_of_day_reports",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
