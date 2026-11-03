"""
Deletes query_log rows older than QUERY_LOG_RETENTION_DAYS (src/config.py,
default 30). query_log stores raw query text indefinitely with no
automatic expiry otherwise - this script is the enforcement mechanism for
that retention policy and is meant to be run on a schedule (daily cron,
or a scheduled GitHub Action), not just manually.

Usage: python scripts/purge_query_log.py [--yes] [--days N]
  --yes      skip the confirmation prompt (for cron/CI use)
  --days N   override QUERY_LOG_RETENTION_DAYS for this run
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.storage.database import get_db_connection


def purge_query_log(retention_days: int) -> int:
    """Deletes and returns the count of query_log rows older than
    retention_days. Age is computed in SQL against each backend's own
    clock, not in Python, so this is correct regardless of the host
    machine's timezone."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if settings.storage_mode == "supabase":
        cursor.execute(
            "DELETE FROM query_log WHERE timestamp < now() - (%s || ' days')::interval",
            (retention_days,),
        )
    else:
        cursor.execute(
            "DELETE FROM query_log WHERE timestamp < datetime('now', ?)",
            (f"-{retention_days} days",),
        )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--days", type=int, default=None, help="override QUERY_LOG_RETENTION_DAYS")
    args = parser.parse_args()

    days = args.days if args.days is not None else settings.query_log_retention_days

    print(f"This will permanently delete query_log rows older than {days} days.")
    print(f"storage_mode = {settings.storage_mode}")

    if not args.yes:
        answer = input("Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    deleted = purge_query_log(days)
    print(f"Done - deleted {deleted} row(s) older than {days} days.")
