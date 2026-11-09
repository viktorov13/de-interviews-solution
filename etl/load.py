from datetime import date
from pathlib import Path

from psycopg import Connection

SQL = Path(__file__).resolve().parent


def load_core(
    conn: Connection, start_date: date | None, end_date: date | None
) -> dict:
    """Replace the requested Core slice inside the caller's transaction."""
    conn.execute(
        (SQL / "stage.sql").read_text(encoding="utf-8"),
        {"start_date": start_date, "end_date": end_date},
    )
    conn.execute("ANALYZE etl_candidates")
    conn.execute((SQL / "classify.sql").read_text(encoding="utf-8"))
    conn.execute("ANALYZE etl_prices")
    conn.execute((SQL / "load.sql").read_text(encoding="utf-8"))

    removed, = conn.execute("""
        SELECT COUNT(*)
        FROM etl_candidates LEFT JOIN etl_prices USING (price_id)
        WHERE etl_prices.price_id IS NULL
    """).fetchone()
    counts = dict(conn.execute("""
        SELECT reason, COUNT(*) FROM etl_prices GROUP BY reason
    """).fetchall())
    conn.execute("DROP TABLE etl_prices, etl_candidates")
    loaded = counts.pop(None, 0)
    rejected = sum(counts.values())
    return {
        "source_rows": loaded + rejected,
        "loaded_rows": loaded,
        "quarantined_rows": rejected,
        "quarantine_reasons": counts,
        "deleted_source_rows": removed,
    }
