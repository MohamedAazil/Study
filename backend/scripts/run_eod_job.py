"""Run the end-of-day report job once.

Usage (from backend/):
    python -m scripts.run_eod_job              # today
    python -m scripts.run_eod_job --date 2026-11-03

Example crontab (20:00 every day):
    0 20 * * * cd /path/to/Study/backend && .venv/bin/python -m scripts.run_eod_job >> eod.log 2>&1
"""

import argparse
import json
import logging
import sys
from datetime import date

from app.db.supabase import get_service_client
from app.notifications.base import get_notifier
from app.notifications.eod_job import run_end_of_day


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Report date (YYYY-MM-DD)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_end_of_day(get_service_client(), get_notifier(), args.date)
    print(json.dumps(result.__dict__, indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
