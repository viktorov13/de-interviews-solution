import argparse
import json
import logging
from datetime import date

import psycopg

from etl.load import load_core
from mart.refresh import refresh_corridor
from ml.features import AS_OF
from ml.score import score_batch

LOGGER = logging.getLogger(__name__)
# Shared with the psql snapshot bootstrap. A session lock precedes the
# repeatable-read transaction so a queued writer starts with a fresh snapshot.
PIPELINE_LOCK_ID = 20492161026


def log_event(event: str, **fields: object) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))


def run(start_date: date | None, end_date: date | None) -> None:
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (PIPELINE_LOCK_ID,))
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            conn.execute("SET LOCAL TIME ZONE 'UTC'")
            log_event("run_started", start_date=start_date, end_date=end_date, as_of=AS_OF)
            etl_stats = load_core(conn, start_date, end_date)
            log_event("core_prepared", **etl_stats)
            mart_rows = refresh_corridor(conn, AS_OF)
            log_event("corridor_prepared", rows=mart_rows)
            metrics = score_batch(conn)
        log_event("run_committed", corridor_rows=mart_rows, **metrics)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build logistics marts and score rates")
    parser.add_argument("--start-date", type=date.fromisoformat, help="inclusive loading date")
    parser.add_argument("--end-date", type=date.fromisoformat, help="exclusive loading date")
    args = parser.parse_args()
    if args.start_date and args.end_date and args.start_date >= args.end_date:
        parser.error("--start-date must be earlier than --end-date")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.start_date, args.end_date)


if __name__ == "__main__":
    main()
