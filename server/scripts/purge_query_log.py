"""
Deletes query_log rows older than QUERY_LOG_RETENTION_DAYS (src/core/config.py,
default 30). The retention policy is now also enforced automatically -
src/core/telemetry.py's log_query_event() runs the same purge lazily, gated to
roughly once a day, piggybacked on real request traffic (see #29) - so
this script is no longer the only thing that enforces it. It's still
useful for an immediate/forced run (e.g. right after lowering
QUERY_LOG_RETENTION_DAYS, or to purge without waiting for the next
request to trigger the automatic sweep).

Usage: python scripts/purge_query_log.py [--yes] [--days N]
  --yes      skip the confirmation prompt (for cron/CI use)
  --days N   override QUERY_LOG_RETENTION_DAYS for this run (must be > 0)
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings
from src.core.telemetry import purge_query_log


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"must be a positive number of days, got {parsed} "
            "(a non-positive value would delete either everything or nothing, "
            "depending on the storage backend - see purge_query_log()'s docstring)"
        )
    return parsed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--days", type=_positive_int, default=None, help="override QUERY_LOG_RETENTION_DAYS")
    args = parser.parse_args()

    days = args.days if args.days is not None else settings.query_log_retention_days
    if days <= 0:
        parser.error(
            f"QUERY_LOG_RETENTION_DAYS is set to {days} in config - it must be positive. "
            "Fix the env var/config, or pass --days explicitly."
        )

    print(f"This will permanently delete query_log rows older than {days} days.")
    print(f"storage_mode = {settings.storage_mode}")

    if not args.yes:
        answer = input("Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    try:
        deleted = purge_query_log(days)
    except Exception as e:
        print(f"Purge failed: {e}")
        print(
            "If this is 'no such table: query_log' / 'relation \"query_log\" does not exist', "
            "the app hasn't started up yet (local mode - init_telemetry_table() runs at "
            "startup) or scripts/supabase_schema.sql hasn't been applied yet (supabase mode)."
        )
        sys.exit(1)

    print(f"Done - deleted {deleted} row(s) older than {days} days.")
